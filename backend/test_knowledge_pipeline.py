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

    def test_agent_handoff_requires_available_capability_and_keeps_task(self):
        complete=lambda *_:{'intent':'browser','needs_knowledge':False,'question':'Abra outro vídeo da banda indicada'}
        messages=[{'role':'user','content':'agora outro'}]
        result=research(self.store,messages,complete,browser_available=True)
        self.assertEqual(result['intent'],'browser');self.assertEqual(result['sources'],[])
        self.assertEqual(result['question'],'Abra outro vídeo da banda indicada')
        self.assertNotEqual(research(self.store,messages,complete)['intent'],'browser')

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
