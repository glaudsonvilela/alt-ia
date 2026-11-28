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
