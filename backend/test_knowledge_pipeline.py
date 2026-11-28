import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from knowledge_extract import extract_document
from knowledge_preview import preview_origin, video_preview
from knowledge_research import research
from knowledge_store import KnowledgeStore


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);key=root/'key';key.write_bytes(os.urandom(32))
        self.store=KnowledgeStore(root/'knowledge.enc',key)
        self.key='7:document:1'
        self.store.upsert({'key':self.key,'account_id':'7','project_id':'2','project_name':'Research',
                          'title':'Tutorial','url':'','kind':'document','updated_at':'2026','body':'Explicação interna'})

    def test_browser_intent_cannot_skip_repository(self):
        complete=lambda *_:{'intent':'browser','needs_knowledge':False,'source_ids':['S1'],'question':'Abra outro vídeo da banda indicada'}
        messages=[{'role':'user','content':'agora outro'}]
        result=research(self.store,messages,complete,browser_available=True)
        self.assertEqual(result['intent'],'browser');self.assertEqual(result['sources'][0]['key'],self.key)
        self.assertEqual(result['question'],'Abra outro vídeo da banda indicada')
        self.assertNotEqual(research(self.store,messages,complete)['intent'],'browser')

    def test_web_confirmation_requires_signed_offer_and_immediate_answer(self):
        from chat_context import confirmed_web_task, research_state
        secret=b'x'*32; email='test@altside.com'
        question='Quer que eu abra o agente para procurar na web?'
        token=research_state({'sources':[],'question':'vídeos de Kamino',
            'web_offer':{'question':question,'task':'vídeos de Kamino'}},email,secret)
        history=[{'role':'assistant','content':'Não encontrei.\n\n'+question+'\n[Arquivos mostrados nesta resposta: PDF]'},
                 {'role':'user','content':'sim'}]
        self.assertEqual(confirmed_web_task(token,email,secret,history),'vídeos de Kamino')
        self.assertIsNone(confirmed_web_task(token,'other@altside.com',secret,history))
        self.assertIsNone(confirmed_web_task(token+'x',email,secret,history))
        for text in ['não', 'sim, mas não abra', 'explique lending', 'o documento diz sim']:
            history[-1]['content']=text
            self.assertIsNone(confirmed_web_task(token,email,secret,history))
        history[-1]['content']='sim';history[-2]['content']='Quer aprofundar?'
        self.assertIsNone(confirmed_web_task(token,email,secret,history))

    def test_pdf_resume_reads_only_unfinished_pages_and_checkpoints_content(self):
        pages=[]
        for n in range(3):
            page=Mock();page.extract_text.return_value=f'Conteúdo da página {n+1}. '*12
            page.get.return_value={};pages.append(page)
        saved='[Página 1/3]\nConteúdo já indexado'
        snapshots=[]
        with patch('pypdf.PdfReader',return_value=SimpleNamespace(pages=pages)):
            result=extract_document('doc.pdf',b'fixture',Mock(),lambda *args:snapshots.append(args),{'sections':[saved]})
        pages[0].extract_text.assert_not_called()
        self.assertEqual([s[0] for s in snapshots],[2,3])
        self.assertEqual(len(snapshots[-1][2]),3)
        self.assertIn(saved,result);self.assertIn('página 3',result)

    def test_video_publishes_audio_before_visual_and_resumes_without_retranscribing(self):
        from contextlib import nullcontext
        from knowledge_transcribe import read_video
        import json
        states=[]
        def checkpoint(state,body):
            states.append((json.loads(json.dumps(state)), body))
        def process(args, **kwargs):
            if args[0]=='ffprobe':
                return SimpleNamespace(stdout=b'{"format":{"duration":60},"streams":[{"codec_type":"audio"},{"codec_type":"video"}]}')
            return SimpleNamespace(stdout=b'fixture')
        visual=Mock();visual.read.side_effect=['Primeiro slide',ValueError('interrupted')]
        with patch('knowledge_transcribe.media_bridge',return_value=nullcontext('http://local')), \
             patch('knowledge_transcribe.subprocess.run',side_effect=process), \
             patch('knowledge_transcribe.scene_times',return_value=[0.5,30.5]), \
             patch('knowledge_transcribe.transcribe_pcm',return_value='Condição falada da estratégia') as transcribe:
            with self.assertRaises(ValueError):
                read_video(None,{},visual,'',{},checkpoint)
            self.assertIn('Condição falada', states[0][1])
            self.assertNotIn('Primeiro slide', states[0][1])
            saved=states[-1][0]
            visual.read.side_effect=None;visual.read.return_value='Segundo slide'
            result=read_video(None,{},visual,'',saved,checkpoint)
            transcribe.assert_called_once()
            self.assertEqual(result.count('Primeiro slide'),1)
            self.assertEqual(result.count('Segundo slide'),1)
            self.assertEqual(states[-1][0]['seconds'],60)

    def test_long_pdf_passages_keep_page_provenance(self):
        from knowledge_store import chunk_text
        chunks=chunk_text('[Página 1/2]\n'+('primeira '*400)+'\n[Pagina ilegível]\n'+
                          '\n[Página 2/2]\n'+('segunda '*400))
        for chunk in chunks:
            if 'primeira' in chunk:
                self.assertTrue(chunk.startswith('[Página 1/2]'))
                self.assertNotIn('segunda',chunk)
            if 'segunda' in chunk:self.assertTrue(chunk.startswith('[Página 2/2]'))

    def test_preview_origin_and_encrypted_cache_respect_revocation(self):
        for bad in ['https://evil.test/7/blobs/1','http://preview.app.basecamp.com/7/blobs/1',
                    'https://user:pass@preview.app.basecamp.com/7/blobs/1']:
            with self.assertRaises(ValueError):preview_origin(bad)
        url='https://preview.app.basecamp.com/7/blobs/1/preview'
        self.store.put_video(self.key,'demo.mp4','https://3.basecampapi.com/7/download/1','video/mp4',100)
        self.store.put_video_preview(self.key,url);self.store.save()
        identifier=self.store.documents_for([self.key])[0]['id']
        from knowledge_store import encrypt,private_write
        import hashlib
        body=b'private jpeg bytes'
        cached=self.store.path.parent/'previews'/(hashlib.sha256(url.encode()).hexdigest()+'.enc')
        private_write(cached,encrypt(self.store.key,b'image/jpeg\n'+body))
        self.assertEqual(video_preview(self.store,identifier),('image/jpeg',body))
        self.assertNotIn(body,cached.read_bytes())
        self.store.prune_project('7','2',set());self.store.save()
        self.assertIsNone(video_preview(self.store,identifier))


if __name__=='__main__':unittest.main()
