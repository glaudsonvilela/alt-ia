import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from knowledge_store import KnowledgeStore
from knowledge_extract import office_text, extract_document
from knowledge_worker import Worker, Superseded


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.key = self.root / 'key'; self.key.write_bytes(os.urandom(32))
        self.store = KnowledgeStore(self.root / 'knowledge.enc', self.key)
        self.record = {'key':'7:message:1:attachment:2','account_id':'7','project_id':'3',
            'project_name':'Research','title':'Explicação','url':'','kind':'attachment',
            'updated_at':'2026-11-28','body':'Conteúdo ainda pendente','parent_key':'7:message:1'}
        self.store.upsert(self.record)
        self.payload = {'record':self.record,'filename':'video.mp4','mime':'video/mp4',
            'download_url':'https://3.basecampapi.com/7/attachments/2/download','byte_size':123}
        self.store.enqueue_content(self.record['key'],'rev1',self.payload)
        self.store.save()
        self.worker = Worker(self.root,self.key,'unused')

    def test_extracted_text_keeps_player_and_job_and_is_encrypted(self):
        self.store.put_video(self.record['key'],'video.mp4',self.payload['download_url'],'video/mp4',123)
        self.store.save()
        identifier = self.store.documents_for([self.record['key']])[0]['id']
        job = self.worker.claim()
        self.worker.update(job,body='Transcrição confidencial sobre rebalanceamento',status='complete')
        current = KnowledgeStore(self.root/'knowledge.enc',self.key)
        self.assertEqual(current.content_status(self.record['key'])['status'],'complete')
        self.assertIsNotNone(current.get_video(identifier))
        self.assertEqual(current.search('rebalanceamento')[0]['key'],self.record['key'])
        self.assertNotIn(b'rebalanceamento',(self.root/'knowledge.enc').read_bytes())
        from knowledge_store import decrypt
        artifact=current.video_text_path(self.record['key'])
        self.assertTrue(artifact.is_file())
        self.assertNotIn(b'rebalanceamento',artifact.read_bytes())
        self.assertIn(b'rebalanceamento',decrypt(current.key,artifact.read_bytes()))
        current.prune_project('7','3',set())
        self.assertFalse(artifact.exists())

    def test_pending_video_exposes_partial_audio_instead_of_missing_transcript(self):
        job=self.worker.claim()
        text='[Vídeo 00:00:00–00:01:00]\n[Transcrição automática; pode conter erros] conteúdo falado'
        self.worker.update(job,body=text,status='pending',progress={'seconds':0,'duration':120,
            'pending_interval':{'offset':0,'text':text}})
        # Fresh snapshots must see the publication, even while the queue is pending.
        self.store._reload(force=True);status=self.store.content_status(self.record['key'])
        self.assertTrue(status['transcript_available'])
        self.assertEqual(status['transcript_status'],'partial')
        self.assertEqual(status['audio_seconds'],60)
        self.assertFalse(status['video_complete'])
        self.worker.update(job,status='pending',progress={'seconds':0,'duration':120,'audio_seconds':120,'audio_complete':True})
        self.store._reload(force=True)
        self.assertEqual(self.store.content_status(self.record['key'])['transcript_status'],'complete')

    def test_backfills_only_real_video_text_and_keeps_existing_exports(self):
        from knowledge_store import decrypt
        self.store.put_video(self.record['key'],'video.mp4',self.payload['download_url'],'video/mp4',123)
        self.store.save()
        self.assertEqual(self.store.reconcile_video_texts(),0)
        job=self.worker.claim()
        text='[Transcrição automática] conteúdo realmente ouvido'
        self.worker.update(job,body=text,status='pending')
        target=self.store.video_text_path(self.record['key']);target.unlink()
        self.assertEqual(self.store.reconcile_video_texts(),1)
        self.assertIn('conteúdo realmente ouvido',decrypt(self.store.key,target.read_bytes()).decode())
        before=target.read_bytes();self.assertEqual(self.store.reconcile_video_texts(),0)
        self.assertEqual(target.read_bytes(),before)

    def test_audit_does_not_call_partial_audio_complete(self):
        from knowledge_status import video_audit
        self.store.put_video(self.record['key'],'video.mp4',self.payload['download_url'],'video/mp4',123)
        self.store.save()
        job=self.worker.claim()
        self.worker.update(job,body='[Transcrição automática] primeiro trecho',status='pending',
            progress={'audio_seconds':60,'duration':120})
        result=video_audit(self.store)
        self.assertEqual(result['audio'],{'partial':1})
        self.assertFalse(result['all_audio_complete'])
        self.assertEqual(result['encrypted_texts'],1)
        self.worker.update(job,status='pending',progress={'audio_seconds':120,'duration':120,'audio_complete':True})
        self.assertTrue(video_audit(self.store)['all_audio_complete'])

    def test_requested_content_gets_priority_without_losing_progress(self):
        second={**self.record,'key':'7:message:9:attachment:10','parent_key':'7:message:9','title':'AAA first alphabetically'}
        self.store.upsert(second)
        self.store.enqueue_content(second['key'],'rev1',{**self.payload,'record':second})
        self.store.save()
        self.store.prioritize_content([self.record['parent_key']])
        self.assertEqual(self.worker.claim()[0],self.record['key'])

    def test_latest_request_precedes_other_urgent_content(self):
        from unittest.mock import patch
        second={**self.record,'key':'7:message:9:attachment:10','parent_key':'7:message:9','title':'AAA earlier request'}
        self.store.upsert(second)
        self.store.enqueue_content(second['key'],'rev1',{**self.payload,'record':second})
        self.store.save()
        import time
        now=time.time()
        with patch('knowledge_store.time.time',return_value=now-100):
            self.store.prioritize_content([second['key']])
        self.store.prioritize_content([self.record['key']])
        self.assertEqual(self.worker.claim()[0],self.record['key'])

    def test_revocation_cannot_be_undone_by_running_extraction(self):
        job = self.worker.claim()
        with self.worker.transaction() as current:
            current.prune_project('7','3',set())
        with self.assertRaises(Superseded):
            self.worker.update(job,body='Revoked text',status='complete')
        current = KnowledgeStore(self.root/'knowledge.enc',self.key)
        self.assertEqual(current.count(),0)

    def test_changed_revision_rejects_old_job_and_keeps_progress(self):
        job = self.worker.claim()
        self.worker.update(job,body='Primeiro minuto',progress={'seconds':60,'sections':['Primeiro minuto']})
        with self.worker.transaction() as current:
            current.enqueue_content(self.record['key'],'rev2',self.payload)
        with self.assertRaises(Superseded):
            self.worker.update(job,body='Old video',status='complete')
        self.assertEqual(self.worker.claim()[1],'rev2')

    def test_transaction_persists_plain_sql_updates(self):
        with self.worker.transaction() as current:
            current.db.execute("UPDATE content_jobs SET detail='saved directly'")
        current = KnowledgeStore(self.root/'knowledge.enc',self.key)
        self.assertEqual(current.content_status(self.record['key'])['detail'],'saved directly')

    def test_remote_pdf_is_searchable_and_removed_with_source(self):
        from basecamp_import import import_file
        record = {**self.record,'body':'Arquivo ainda sem extração de conteúdo: formato ou tamanho não suportado.'}
        self.store.upsert(record)
        item = {'filename':'large.pdf','content_type':'application/pdf','byte_size':100000000,
                'download_url':self.payload['download_url']}
        import_file(None,item,record,self.store,{'updated':0,'skipped':0})
        self.store.save()
        identifier = self.store.documents_for([self.record['parent_key']])[0]['id']
        self.assertEqual(self.store.get_remote_pdf(identifier)['mime'],'application/pdf')
        self.assertEqual(self.store.document_context(identifier)['source_id'],self.record['key'])
        self.assertFalse((self.root/'documents').exists())
        self.assertIn('em segundo plano',self.store.search('extração')[0]['excerpt'])
        self.store.prune_project('7','3',set()); self.store.save()
        self.assertIsNone(self.store.get_remote_pdf(identifier))

    def test_interrupted_last_attempt_can_resume(self):
        with self.worker.transaction() as current:
            current.db.execute("UPDATE content_jobs SET status='processing',attempts=3")
        self.worker.reset_interrupted()
        self.assertIsNotNone(self.worker.claim())

    def test_question_and_answer_are_read_together(self):
        parent = {**self.record,'key':'7:message:1','kind':'message','title':'Pergunta sobre reserva',
                  'parent_key':'','body':'Quando devo recompor a reserva?'}
        answer = {**self.record,'key':'7:comment:8','kind':'comment',
                  'body':'A resposta documenta as condições de rebalanceamento.'}
        self.store.upsert(parent); self.store.upsert(answer); self.store.save()
        self.assertEqual(self.store.discussion_parents([answer['key']]),[parent['key']])
        sources = self.store.read_sources([parent['key']],['reserva'],budget=12000)
        self.assertIn('condições de rebalanceamento',sources[0]['excerpt'])

    def test_presentation_preserves_slide_order_notes_and_visual_text(self):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:
            for number in (10,2,1):
                z.writestr(f'ppt/slides/slide{number}.xml',f'<a:p xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:t>Slide {number}</a:t></a:p>')
            z.writestr('ppt/notesSlides/notesSlide1.xml','<a:p xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:t>Condição da estratégia</a:t></a:p>')
            z.writestr('ppt/media/image1.png',b'fixture')
        class Visual:
            def read(self,body): return 'Tabela: limite de exposição 10%'
        text=extract_document('treino.pptx',buf.getvalue(),Visual())
        self.assertLess(text.index('Slide 2'),text.index('Slide 10'))
        self.assertIn('Condição da estratégia',text)
        self.assertIn('Tabela: limite de exposição 10%',text)


if __name__ == '__main__':
    unittest.main()
