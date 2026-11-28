import io,json,time,unittest
from chat_stream import answer_prefix,consume_stream

class StreamTest(unittest.TestCase):
    def test_partial_escapes_and_surrogates(self):
        content=json.dumps({'answer':'Olá 💡 "DCA"\nReserva','follow_up':'Qual?','document_ids':['D1']})
        last=''
        for index in range(len(content)+1):
            current=answer_prefix(content[:index])
            self.assertTrue(current.startswith(last),repr(current))
            current.encode('utf-8')
            last=current
        self.assertEqual(last,'Olá 💡 "DCA"\nReserva')

    def test_only_answer_streams_and_usage_is_preserved(self):
        source=json.dumps({'answer':'Resposta com contexto','follow_up':'Quer mais?','document_ids':['D1']})
        events=[{'choices':[{'delta':{'reasoning_content':'PRIVATE'},'finish_reason':None}]}]
        events.extend({'choices':[{'delta':{'content':letter},'finish_reason':None}]} for letter in source)
        events.append({'choices':[{'delta':{},'finish_reason':'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':20}})
        upstream=io.BytesIO(b''.join(b'data: '+json.dumps(event).encode()+b'\n\n' for event in events)+b'data: [DONE]\n\n')
        pieces=[]; result=consume_stream(upstream,pieces.append,True,time.monotonic()+10)
        self.assertEqual(''.join(pieces),'Resposta com contexto')
        self.assertEqual(result['choices'][0]['message']['content'],source)
        self.assertEqual(result['usage']['completion_tokens'],20)

    def test_truncated_generation_is_not_a_complete_answer(self):
        event={'choices':[{'delta':{'content':'partial'},'finish_reason':'length'}]}
        with self.assertRaises(ValueError):consume_stream(io.BytesIO(b'data: '+json.dumps(event).encode()+b'\n'),lambda _:None,False,time.monotonic()+10)
