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

    def test_public_search_submits_with_enter_and_reads_results(self):
        before = {"url": "https://duckduckgo.com/", "title": "DuckDuckGo", "text": "Search",
                  "elements": [{"index": 10, "kind": "textarea", "label": "Search with DuckDuckGo", "inputType": ""}]}
        filled = {**before, "text": "bitcoin news"}
        results = {"url": "https://duckduckgo.com/?q=bitcoin+news", "title": "bitcoin news", "text": "Resultados de bitcoin news",
                   "elements": []}
        with patch.object(agent_browser, "worker_call", side_effect=[before, filled, results]) as worker, \
             patch.object(agent_browser, "choose_action", side_effect=[{"action": "fill", "index": 10, "value": "bitcoin news"},
                                                                 {"action": "finish", "answer": "Encontrei os resultados."}]):
            result = agent_browser.run("pesquisa sobre bitcoin news", "a" * 48, "nvapi-test")
        self.assertEqual(result["reply"], "Encontrei os resultados.")
        self.assertEqual(worker.call_args_list[2].args[1], "/sessions/" + "a" * 48 + "/key")
        self.assertEqual(worker.call_args_list[2].args[3], {"key": "Enter"})

    def test_other_form_does_not_submit(self):
        snapshot = {"url": "https://example.com/", "title": "Example", "text": "Mensagem",
                    "elements": [{"index": 1, "kind": "textarea", "label": "Search", "inputType": ""}]}
        with patch.object(agent_browser, "worker_call", side_effect=[snapshot, snapshot]) as worker, \
             patch.object(agent_browser, "choose_action", side_effect=[{"action": "fill", "index": 1, "value": "olá"},
                                                                 {"action": "finish", "answer": "Pronto."}]):
            agent_browser.run("Preencha o campo", "a" * 48, "nvapi-test")
        self.assertEqual(worker.call_count, 2)

    def test_agent_can_choose_first_site_from_blank_page(self):
        blank = {"url": "about:blank", "title": "", "text": "", "elements": []}
        result_page = {"url": "https://duckduckgo.com/", "title": "DuckDuckGo", "text": "Search", "elements": []}
        with patch.object(agent_browser, "worker_call", side_effect=[blank, result_page]) as worker, \
             patch.object(agent_browser, "choose_action", side_effect=[{"action": "navigate", "url": "https://duckduckgo.com/"},
                                                                  {"action": "finish", "answer": "Página aberta."}]):
            result = agent_browser.run("Pesquise bitcoin", "a" * 48, "nvapi-test")
        self.assertEqual(result["reply"], "Página aberta.")
        self.assertEqual(worker.call_args_list[1].args[1], "/sessions/" + "a" * 48 + "/navigate")

    def test_play_video_returns_embedded_video_without_loading_youtube_in_worker(self):
        result_page = {"url": "https://duckduckgo.com/?q=cyberpunk+music", "title": "Pesquisa", "text": "Vídeos",
                       "elements": [{"index": 4, "kind": "a", "label": "Cyberpunk soundtrack", "risky": False,
                                     "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}]}
        with patch.object(agent_browser, "worker_call", return_value=result_page) as worker, \
             patch.object(agent_browser, "choose_action", return_value={"action": "click", "index": 4}):
            result = agent_browser.run("Quero assistir vídeo de música cyberpunk", "a" * 48, "nvapi-test")
        self.assertEqual(result["video"]["id"], "dQw4w9WgXcQ")
        self.assertEqual(worker.call_count, 1)

    def test_unrelated_youtube_link_is_not_treated_as_video_playback(self):
        self.assertFalse(agent_browser.requested_video("Resuma as notícias do YouTube"))
        self.assertIsNone(agent_browser.youtube_video("https://evil.example/watch?v=dQw4w9WgXcQ"))
        self.assertEqual(agent_browser.youtube_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                                                     "https://www.youtube.com › watch?v=dQw4w9WgXcQ")["title"], "")


if __name__ == "__main__":
    unittest.main()
