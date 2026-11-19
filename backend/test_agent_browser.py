import unittest
from unittest.mock import patch

import agent_browser


class AgentBrowserTests(unittest.TestCase):
    def test_cookie_cannot_be_forged(self):
        key = "nvapi-test"
        session_id = "a" * 48
        cookie = agent_browser.cookie_value(session_id, key)
        self.assertEqual(agent_browser.session_from_cookie(f"other=x; alt_ia_agent={cookie}", key), session_id)
        self.assertIsNone(agent_browser.session_from_cookie(f"alt_ia_agent={session_id}.{'0' * 64}", key))

    def test_risky_action_never_reaches_worker(self):
        snapshot = {"url": "https://example.com/", "title": "Example", "text": "Enviar",
                    "elements": [{"index": 2, "kind": "button", "label": "Enviar", "risky": True}]}
        with patch.object(agent_browser, "worker_call", return_value=snapshot) as worker, \
             patch.object(agent_browser, "choose_action", return_value={"action": "click", "index": 2}):
            result = agent_browser.run("Veja minha mensagem", "a" * 48, "nvapi-test")
        self.assertIn("Faça o clique", result["reply"])
        self.assertEqual(worker.call_count, 1)

    def test_observe_act_verify_cycle(self):
        before = {"url": "https://example.com/", "title": "Início", "text": "Caixa de entrada",
                  "elements": [{"index": 0, "kind": "a", "label": "Caixa de entrada", "risky": False}]}
        after = {"url": "https://example.com/inbox", "title": "Caixa de entrada", "text": "Uma mensagem",
                 "elements": []}
        with patch.object(agent_browser, "worker_call", side_effect=[before, after]) as worker, \
             patch.object(agent_browser, "choose_action", side_effect=[{"action": "click", "index": 0},
                                                                  {"action": "finish", "answer": "Há uma mensagem."}]):
            result = agent_browser.run("Veja minhas mensagens", "a" * 48, "nvapi-test")
        self.assertEqual(result["reply"], "Há uma mensagem.")
        self.assertEqual(len(result["steps"]), 1)
        self.assertEqual(worker.call_args_list[1].args[0], "POST")


if __name__ == "__main__":
    unittest.main()
