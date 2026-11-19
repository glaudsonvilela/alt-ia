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
        result_page = {"url": "https://example.com/", "title": "Example", "text": "Example", "elements": []}
        with patch.object(agent_browser, "worker_call", side_effect=[blank, result_page]) as worker, \
             patch.object(agent_browser, "choose_action", side_effect=[{"action": "navigate", "url": "https://example.com/"},
                                                                  {"action": "finish", "answer": "Página aberta."}]):
            result = agent_browser.run("Pesquise bitcoin", "a" * 48, "nvapi-test")
        self.assertEqual(result["reply"], "Página aberta.")
        self.assertEqual(worker.call_args_list[1].args[1], "/sessions/" + "a" * 48 + "/navigate")

    def test_google_verification_uses_search_service_and_opens_playlist(self):
        challenge = {"url": "https://www.google.com/sorry/index?continue=/search", "title": "Google", "text": "Verify", "elements": []}
        playlist_url = "https://www.youtube.com/playlist?list=PLRknjXeAnCio"
        sources = [{"title": "Muse playlist", "url": playlist_url, "summary": "Músicas da banda Muse"}]
        with patch.object(agent_browser, "worker_call", return_value=challenge) as worker, \
             patch.object(agent_browser, "search_web", return_value={"sources": sources}) as search, \
             patch.object(agent_browser, "choose_action", side_effect=[{"action": "search", "query": "Muse playlist YouTube"},
                                                                  {"action": "navigate", "url": playlist_url}]):
            result = agent_browser.run("Abra uma playlist boa da banda Muse", "a" * 48, "nvapi-test")
        self.assertEqual(result["video"]["kind"], "playlist")
        self.assertEqual(result["video"]["title"], "Muse playlist")
        self.assertIn("playlist", result["reply"])
        self.assertEqual(worker.call_count, 1)
        search.assert_called_once_with("Muse playlist YouTube", "research")

    def test_blank_page_presearches_media_before_model_choice(self):
        blank = {"url": "about:blank", "title": "", "text": "", "elements": []}
        playlist_url = "https://www.youtube.com/playlist?list=PLRknjXeAnCio"
        sources = [{"title": "Muse playlist", "url": playlist_url, "summary": "Músicas da banda Muse"}]
        with patch.object(agent_browser, "worker_call", return_value=blank) as worker, \
             patch.object(agent_browser, "search_web", return_value={"sources": sources}) as search, \
             patch.object(agent_browser, "choose_action", return_value={"action": "navigate", "url": playlist_url,
                                                                    "answer": "🎵 Muse para embalar sua sessão!"}) as model:
            result = agent_browser.run("Abra uma playlist boa da banda Muse para tocar", "a" * 48, "nvapi-test")
        search.assert_called_once_with("Muse playlist youtube", "research")
        self.assertEqual(model.call_count, 1)
        self.assertEqual(worker.call_count, 1)
        self.assertEqual(result["reply"], "🎵 Muse para embalar sua sessão!")
        self.assertEqual(result["video"]["kind"], "playlist")

    def test_abre_playlist_uses_player_instead_of_static_browser_preview(self):
        blank = {"url": "about:blank", "title": "", "text": "", "elements": []}
        playlist_url = "https://www.youtube.com/watch?v=9gsAz6S_zSw&list=PLxA687tYuMWjZQiHa3liNe3z-zcJxikvP"
        sources = [{"title": "Slipknot Playlist", "url": playlist_url, "summary": "Slipknot"}]
        with patch.object(agent_browser, "worker_call", return_value=blank) as worker, \
             patch.object(agent_browser, "search_web", return_value={"sources": sources}) as search, \
             patch.object(agent_browser, "choose_action", return_value={"action": "navigate", "url": playlist_url}):
            result = agent_browser.run("abre playlist slipknot", "a" * 48, "nvapi-test")
        self.assertEqual(result["video"]["kind"], "playlist")
        self.assertEqual(result["video"]["id"], "PLxA687tYuMWjZQiHa3liNe3z-zcJxikvP")
        self.assertEqual(worker.call_count, 1)
        search.assert_called_once_with("slipknot playlist youtube", "research")

    def test_repeated_search_for_music_still_starts_player(self):
        blank = {"url": "about:blank", "title": "", "text": "", "elements": []}
        sources = [{"title": "Slipknot Playlist", "url": "https://www.youtube.com/playlist?list=PLRknjXeAnCio"}]
        with patch.object(agent_browser, "worker_call", return_value=blank) as worker, \
             patch.object(agent_browser, "search_web", return_value={"sources": sources}) as search, \
             patch.object(agent_browser, "choose_action", return_value={"action": "search", "query": "Slipknot playlist"}) as model:
            result = agent_browser.run("abre playlist slipknot", "a" * 48, "nvapi-test")
        self.assertEqual(result["video"]["kind"], "playlist")
        self.assertEqual(worker.call_count, 1)
        self.assertEqual(search.call_count, 1)
        self.assertEqual(model.call_count, 1)

    def test_ai_can_start_player_from_natural_music_request(self):
        blank = {"url": "about:blank", "title": "", "text": "", "elements": []}
        playlist_url = "https://www.youtube.com/playlist?list=PLxA687tYuMWjZQiHa3liNe3z-zcJxikvP"
        sources = [{"title": "Slipknot Playlist", "url": playlist_url, "summary": "Slipknot"}]
        with patch.object(agent_browser, "worker_call", return_value=blank), \
             patch.object(agent_browser, "search_web", return_value={"sources": sources}), \
             patch.object(agent_browser, "choose_action", side_effect=[
                 {"action": "search", "query": "Slipknot playlist"},
                 {"action": "play", "url": playlist_url, "kind": "playlist"}]):
            result = agent_browser.run("coloca um som da banda Slipknot", "a" * 48, "nvapi-test")
        self.assertEqual(result["video"]["kind"], "playlist")
        self.assertIn("Iniciou o player", result["steps"][-1])

    def test_page_summary_reads_full_dom_and_ocr_before_answering(self):
        first = {"url": "https://example.org/article", "title": "Artigo", "text": "Início", "elements": []}
        full = {**first, "text": "Artigo completo", "ocr": "Texto de uma imagem", "full_read": True}
        with patch.object(agent_browser, "worker_call", side_effect=[first, full]) as worker, \
             patch.object(agent_browser, "choose_action", side_effect=[
                 {"action": "finish", "answer": "Resumo incompleto"},
                 {"action": "finish", "answer": "Resumo do artigo e da imagem"}]) as model:
            result = agent_browser.run("Resuma a página inteira", "a" * 48, "nvapi-test")
        self.assertEqual(result["reply"], "Resumo do artigo e da imagem")
        self.assertEqual(worker.call_args_list[1].args[1], "/sessions/" + "a" * 48 + "/read")
        self.assertEqual(model.call_args_list[1].args[1]["ocr"], "Texto de uma imagem")

    def test_ai_can_request_visual_ocr_for_a_page(self):
        page = {"url": "https://example.org/chart", "title": "Gráfico", "text": "Vendas", "elements": []}
        read = {**page, "ocr": "Receita 20 milhões", "full_read": True, "visual_read": True}
        with patch.object(agent_browser, "worker_call", side_effect=[page, read]) as worker, \
             patch.object(agent_browser, "choose_action", side_effect=[
                 {"action": "read", "visual": True}, {"action": "finish", "answer": "Receita de 20 milhões."}]):
            result = agent_browser.run("Interprete o gráfico", "a" * 48, "nvapi-test")
        self.assertEqual(result["reply"], "Receita de 20 milhões.")
        self.assertEqual(worker.call_args_list[1].args[1], "/sessions/" + "a" * 48 + "/read?visual=1")

    def test_open_youtube_playlist_can_be_played_on_follow_up(self):
        page = {"url": "https://www.youtube.com/watch?v=9gsAz6S_zSw&list=PLxA687tYuMWjZQiHa3liNe3z-zcJxikvP",
                "title": "Slipknot Playlist", "text": "YouTube", "elements": []}
        with patch.object(agent_browser, "worker_call", return_value=page) as worker:
            result = agent_browser.run("toque essa playlist", "a" * 48, "nvapi-test")
        self.assertEqual(result["video"]["kind"], "playlist")
        self.assertEqual(worker.call_count, 1)

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
