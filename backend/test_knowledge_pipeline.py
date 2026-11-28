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

    @unittest.skipUnless(os.geteuid() == 0, 'Cross-UID regression requires container root')
    def test_atomic_write_keeps_worker_ownership_and_private_modes(self):
        from knowledge_store import private_write
        root=Path(self.temp.name)/'shared';root.mkdir(mode=0o700);os.chown(root,1000,1000)
        target=root/'knowledge.enc'
        for value in [b'first',b'priority update']:
            private_write(target,value)
            self.assertEqual(target.read_bytes(),value)
            self.assertEqual(target.stat().st_uid,1000)
            self.assertEqual(target.stat().st_mode & 0o777,0o600)
        nested=root/'video-text'/'memo.txt.enc';private_write(nested,b'encrypted')
        self.assertEqual(nested.parent.stat().st_uid,1000)
        self.assertEqual(nested.parent.stat().st_mode & 0o777,0o700)
        self.assertEqual(nested.stat().st_uid,1000)

    def test_internal_window_action_does_not_become_repository_explanation(self):
        from knowledge_research import requested_app_action
        messages=[{'role':'user','content':'Quero simular um empréstimo'},
                  {'role':'assistant','content':'Podemos usar o simulador de lending.'},
                  {'role':'user','content':'abre esse simulador'}]
        plan={'intent':'explain','question':'Abra o simulador de lending',
              'app_action':{'kind':'lending','request_quote':'abre esse simulador'},'source_ids':['S1']}
        result=research(self.store,messages,lambda *_:plan)
        self.assertEqual(result['app_action'],'lending')
        self.assertEqual(result['sources'],[])
        self.assertEqual(result['status'],'not_needed')
        self.assertIsNone(result['agent_task'])
        plan['app_action']['request_quote']='Podemos usar o simulador'
        self.assertIsNone(requested_app_action(plan,messages))
        plan['app_action']={'kind':'execute_code','request_quote':'abre esse simulador'}
        self.assertIsNone(requested_app_action(plan,messages))

    def test_contextual_site_handoff_preserves_resolved_task(self):
        from knowledge_research import requested_site_task
        messages=[{'role':'user','content':'Me explique a Meteora'},
                  {'role':'assistant','content':'Meteora é o protocolo que acabamos de comparar.'},
                  {'role':'user','content':'abre ela pra mim'}]
        plan={'intent':'browser','question':'Abra o aplicativo da Meteora', 'source_ids':['S1'],
              'browser_action':{'kind':'open_site','request_quote':'abre ela pra mim'}}
        def complete(_, payload):
            self.assertEqual(payload['conversation'],messages)
            return plan
        result=research(self.store,messages,complete,browser_available=True)
        self.assertEqual(result['agent_task'],'Abra o aplicativo da Meteora')
        self.assertTrue(result['sources'])
        self.assertIsNone(requested_site_task(plan,messages,False))
        plan['browser_action']['request_quote']='Me explique a Meteora'
        self.assertIsNone(requested_site_task(plan,messages,True))
        plan['browser_action']={'kind':'none','request_quote':'abre ela pra mim'}
        self.assertIsNone(requested_site_task(plan,messages,True))

    def test_empty_catalog_still_interprets_navigation_context(self):
        store=Mock();store.catalog.return_value=[];store.search.return_value=[];store.read_sources.return_value=[];store.discussion_parents.return_value=[]
        plan={'intent':'browser','needs_knowledge':False,'question':'Abra Meteora',
              'browser_action':{'kind':'open_site','request_quote':'abra Meteora'}}
        result=research(store,[{'role':'user','content':'abra Meteora'}],lambda *_:plan,browser_available=True)
        self.assertEqual(result['agent_task'],'Abra Meteora')

    def test_requested_video_is_delivered_without_a_transcript(self):
        from knowledge_delivery import requested_media
        self.store.put_video(self.key,'tutorial.mp4','https://3.basecampapi.com/7/download/1','video/mp4',100)
        plan={'intent':'browser','question':'Mostre os vídeos internos',
              'media_request':'show_video','media_source_ids':['S1','unknown'],'source_ids':['S1'],
              'browser_action':{'kind':'open_site','request_quote':'mostre o vídeo'}}
        result=research(self.store,[{'role':'user','content':'mostre o vídeo'}],lambda *_:plan,browser_available=True)
        self.assertIsNone(result['agent_task'])
        self.assertEqual(result['media_source_keys'],[self.key])
        response=requested_media(result,self.store)
        self.assertEqual(len(response['documents']),1)
        self.assertEqual(response['documents'][0]['kind'],'video')
        self.assertTrue(response['requested_documents'])
        self.assertNotIn('transcrição',response['reply'])
        self.assertIsNone(requested_media({**result,'media_request':'none'},self.store))
        self.assertIsNone(requested_media({**result,'media_source_keys':['unknown']},self.store))

    def test_display_shortcut_never_swallows_requested_summary(self):
        plan={'intent':'explain','question':'Resuma o vídeo','media_request':'show_video',
              'media_source_ids':['S1'],'source_ids':['S1']}
        for text in ['resuma o vídeo', 'poderia resumir para mim?', 'me dê um resumo do vídeo', 'descreva o conteúdo']:
            result=research(self.store,[{'role':'user','content':text}],lambda *_:plan)
            self.assertEqual(result['media_request'],'none')
            self.assertTrue(result['sources'])
        result=research(self.store,[{'role':'user','content':'abra o vídeo Análise de funcionamento Orca'}],lambda *_:plan)
        self.assertEqual(result['media_request'],'show_video')

    def test_current_news_offers_agent_with_resolved_context(self):
        from knowledge_delivery import current_web_offer
        result={'question':'Pesquise notícias de hoje sobre a Orca na Solana','web_query':'Orca Solana notícias hoje'}
        offer=current_web_offer(result)
        self.assertEqual(offer['task'],result['question'])
        self.assertIn('agente',offer['question'])
        self.assertIsNone(current_web_offer({**result,'web_query':''}))
        self.assertIsNone(current_web_offer({**result,'media_request':'show_video'}))

    def test_web_confirmation_requires_signed_offer_and_immediate_answer(self):
        from chat_context import confirmed_web_task, research_state
        secret=b'x'*32; email='test@altside.com'
        question='Quer que eu abra o agente para procurar na web?'
        token=research_state({'sources':[],'question':'vídeos de Kamino',
            'web_offer':{'question':question,'task':'vídeos de Kamino'}},email,secret)
        history=[{'role':'assistant','content':'Não encontrei.\n\n'+question+'\n[Arquivos mostrados nesta resposta: PDF]'},
                 {'role':'user','content':'sim'}]
        for answer in ['sim', 's', 'Sim, pesquisar', 'pode sim']:
            history[-1]['content']=answer
            self.assertEqual(confirmed_web_task(token,email,secret,history),'vídeos de Kamino')
        from chat_context import web_offer_decision
        history[-1]['content']='Não agora'
        self.assertFalse(web_offer_decision(token,email,secret,history)['accepted'])
        history[-1]['content']='sim'
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

    def test_cloud_audio_and_local_fallback_keep_the_same_text_contract(self):
        from knowledge_transcribe import transcribe_pcm
        pcm=b'\xff\x01'*16000
        with patch.dict(os.environ,{'ALT_IA_ASR_PROVIDER':'nvidia'}), \
             patch('knowledge_transcribe._nvidia_retry_at',0), \
             patch('knowledge_transcribe.transcribe_nvidia',return_value='Fala transcrita') as cloud, \
             patch('knowledge_transcribe.transcribe_local',return_value='Fallback local') as local:
            self.assertEqual(transcribe_pcm(pcm,'test-key'),'Fala transcrita')
            local.assert_not_called()
            cloud.side_effect=TimeoutError()
            self.assertEqual(transcribe_pcm(pcm,'test-key'),'Fallback local')
            self.assertEqual(transcribe_pcm(pcm,'test-key'),'Fallback local')
            self.assertEqual(cloud.call_count,2)
            self.assertEqual(transcribe_pcm(b'\0'*32000,'test-key'),'')

    def test_full_audio_precedes_visual_and_fractional_end_is_not_repeated(self):
        from contextlib import nullcontext
        from knowledge_transcribe import read_video
        import json
        states=[]; order=[]
        def checkpoint(state,body): states.append(json.loads(json.dumps(state)))
        def process(args, **kwargs):
            if args[0]=='ffprobe':
                return SimpleNamespace(stdout=b'{"format":{"duration":120.5},"streams":[{"codec_type":"audio"},{"codec_type":"video"}]}')
            return SimpleNamespace(stdout=b'fixture')
        def speech(*_): order.append('audio'); return 'Fala da estratégia'
        visual=Mock();visual.read.side_effect=lambda *_:order.append('visual') or 'Cena'
        with patch('knowledge_transcribe.media_bridge',return_value=nullcontext('http://local')), \
             patch('knowledge_transcribe.subprocess.run',side_effect=process), \
             patch('knowledge_transcribe.scene_times',side_effect=lambda _,start,duration:[start+.1]), \
             patch('knowledge_transcribe.transcribe_pcm',side_effect=speech) as transcribe:
            result=read_video(None,{},visual,'',{},checkpoint)
            self.assertEqual(order,['audio']*3+['visual']*3)
            self.assertTrue(states[2]['audio_complete'])
            self.assertEqual(states[2]['audio_seconds'],120.5)
            read_video(None,{},visual,'',states[-1],checkpoint)
            self.assertEqual(transcribe.call_count,3)
            self.assertEqual(visual.read.call_count,3)
            self.assertEqual(result.count('Fala da estratégia'),3)

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
