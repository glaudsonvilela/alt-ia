import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from knowledge_store import KnowledgeStore
from knowledge_video import api_download_url, signed_destination, range_header, video_response
from basecamp_import import import_video

class VideoTest(unittest.TestCase):
    def test_private_metadata_is_encrypted_revocable_and_never_downloads(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); key=root/'key'; key.write_bytes(os.urandom(32))
            store=KnowledgeStore(root/'knowledge.enc',key)
            record=dict(key='7:upload:1',account_id='7',project_id='42',project_name='Research',title='DCA.mp4',
                        url='https://3.basecamp.com/7/file',kind='upload',updated_at='today')
            item=dict(filename='DCA.mp4',content_type='video/mp4',byte_size=900000000,
                      download_url='https://storage.3.basecamp.com/7/video')
            self.assertTrue(import_video(item,record,store))
            store.save()
            card=store.documents_for([record['key']])[0]
            self.assertEqual(card['kind'],'video'); self.assertNotIn('download_url',card)
            self.assertNotIn(item['download_url'].encode(),store.path.read_bytes())
            self.assertEqual(store.get_video(card['id'])['byte_size'],900000000)
            self.assertEqual(store.document_context(card['id'])['source_id'],record['key'])
            self.assertEqual(sorted(p.name for p in root.iterdir()),['key','knowledge.enc'])
            store.prune_project('7','42',set()); store.save()
            self.assertIsNone(store.get_video(card['id']))

    def test_urls_and_ranges(self):
        self.assertEqual(api_download_url('https://storage.3.basecamp.com/7/download/video.mp4'),'https://3.basecampapi.com/7/download/video.mp4')
        for value in ['http://3.basecampapi.com/x','https://evil.test/x','https://3.basecampapi.com@evil.test/x','https://127.0.0.1/x']:
            with self.assertRaises(ValueError):api_download_url(value)
        for value in ['https://evil.test/x','http://storage.3.basecamp.com/x','https://bucket.amazonaws.com.evil.test/x']:
            with self.assertRaises(ValueError):signed_destination(value)
        for value in ['bytes=0-65535','bytes=90-','bytes=-100']:
            self.assertEqual(range_header(value),value)
        for value in ['bytes=2-1','bytes=0-10,20-30','bytes=-0','other=1-2']:
            with self.assertRaises(ValueError):range_header(value)

    def test_streaming_preserves_range_and_strips_authorization_on_signed_hop(self):
        requests=[]
        def transport(request):
            requests.append(request)
            if len(requests)==1:
                return httpx.Response(302,headers={'location':'https://bucket.s3.amazonaws.com/video?signature=opaque'})
            return httpx.Response(206,headers={'content-type':'video/mp4','content-length':'4','content-range':'bytes 10-13/100'},content=b'data')
        client=httpx.Client(transport=httpx.MockTransport(transport))
        with patch('knowledge_video.httpx.Client',return_value=client),patch('knowledge_video.access_token',return_value='private-token'):
            with video_response(None,{'download_url':'https://storage.3.basecamp.com/7/file'},'bytes=10-13') as response:
                self.assertEqual(response.status_code,206)
                self.assertEqual(response.headers['content-range'],'bytes 10-13/100')
                self.assertEqual(response.content,b'data')
        self.assertEqual(requests[0].headers['authorization'],'Bearer private-token')
        self.assertNotIn('authorization',requests[1].headers)
        self.assertEqual(requests[1].headers['range'],'bytes=10-13')
