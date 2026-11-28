import unittest
from chat_context import validate_messages, research_state, read_research_state
from scenario_tokens import issue

class ChatContextTest(unittest.TestCase):
    def test_long_answer_and_short_followup(self):
        messages = [{"role":"user","content":"Explique as estratégias"},
                    {"role":"assistant","content":"Detalhes " * 900 + "Qual das duas?"},
                    {"role":"user","content":"a segunda"}]
        self.assertEqual(validate_messages(messages), messages)
        with self.assertRaises(ValueError):
            validate_messages([{"role":"user","content":"x" * 4001}])
        with self.assertRaises(ValueError):
            validate_messages([{"role":"assistant","content":"x" * 16001}, messages[-1]])
        with self.assertRaises(ValueError):
            validate_messages([{"role":"assistant","content":"x" * 16000}] * 4 + [messages[-1]])

    def test_state_is_signed_account_bound_and_purpose_bound(self):
        state = research_state({"question":"DCA", "sources":[{"key":"company:1"}]}, "one@altside.com", b"secret")
        self.assertEqual(read_research_state(state,"one@altside.com",b"secret")["source_ids"], ["company:1"])
        self.assertIsNone(read_research_state(state,"two@altside.com",b"secret"))
        self.assertIsNone(read_research_state(state,"one@altside.com",b"wrong"))
        self.assertIsNone(read_research_state(issue({"account":"one@altside.com"},b"secret"),"one@altside.com",b"secret"))
        self.assertIsNone(read_research_state(None,"one@altside.com",b"secret"))
