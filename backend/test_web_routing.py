import unittest
from knowledge_research import requested_site_task, requested_web_query
from chat_context import research_state, web_offer_decision
from knowledge_delivery import current_web_offer


class WebRoutingTests(unittest.TestCase):
    def test_contextual_research_is_separate_from_opening_a_page(self):
        messages = [{'role':'assistant','content':'O método usa liquidez concentrada na Uniswap.'},
                    {'role':'user','content':'existe alguma estratégia parecida na internet sobre esse método?'}]
        plan = {'question':'Compare estratégias públicas de liquidez concentrada na Uniswap',
                'web_query':'Uniswap concentrated liquidity strategy',
                'web_action':{'kind':'search','request_quote':messages[-1]['content']},
                'browser_action':{'kind':'none'}}
        self.assertEqual(requested_web_query(plan,messages),plan['web_query'])
        self.assertIsNone(requested_site_task(plan,messages,True))
        plan['web_action']['request_quote'] = messages[0]['content']
        self.assertEqual(requested_web_query(plan,messages),'')

    def test_search_confirmation_retains_the_resolved_public_query(self):
        result = {'sources':[], 'question':'Compare estratégias de liquidez concentrada',
                  'web_query':'Uniswap concentrated liquidity strategy'}
        result['web_offer'] = current_web_offer(result)
        token = research_state(result,'test@altside.com',b'secret')
        messages = [{'role':'assistant','content':result['web_offer']['question']},
                    {'role':'user','content':'Sim, pesquisar'}]
        decision = web_offer_decision(token,'test@altside.com',b'secret',messages)
        self.assertEqual(decision['query'],result['web_query'])
        self.assertEqual(decision['task'],result['question'])
        self.assertIsNone(web_offer_decision(token,'other@altside.com',b'secret',messages))

    def test_explicit_page_open_keeps_browser_action(self):
        message={'role':'user','content':'abra a página da Kamino'}
        plan={'question':'Abra o aplicativo Kamino Finance na Solana',
              'browser_action':{'kind':'open_site','request_quote':message['content']},
              'web_action':{'kind':'none'}}
        self.assertEqual(requested_site_task(plan,[message],True),plan['question'])
        self.assertEqual(requested_web_query(plan,[message]),'')
