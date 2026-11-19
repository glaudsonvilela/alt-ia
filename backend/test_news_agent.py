import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from news_agent import LOCAL_TIME, plan, run


class NewsAgentTests(unittest.TestCase):
    def test_news_intent_does_not_capture_simulation(self):
        self.assertEqual(plan("Resumo das notícias de hoje"), {"scope": "daily"})
        self.assertEqual(plan("notícias da HYPE")["asset"], "HYPE")
        self.assertIsNone(plan("Simule a pool HYPE se subir 35%"))
        self.assertEqual(plan("sobre a hyper", "news")["asset"], "HYPE")
        self.assertEqual(plan("sobre bitcoin", "news")["asset"], "BTC")
        self.assertIsNone(plan("resuma em poucas palavras pra mim", "news", "BTC"))
        self.assertIsNone(plan("qual notícia é mais importante?", "news", "BTC"))
        self.assertIsNone(plan("o que isso significa para o bitcoin?", "news", "BTC"))
        self.assertIsNone(plan("sobre bitcoin", "news", "BTC"))
        self.assertEqual(plan("mais notícias", "news", "BTC")["asset"], "BTC")
        self.assertIsNone(plan("sobre bitcoin"))
        self.assertIsNone(plan("e se cair 20%?", "news"))

    def test_daily_uses_only_todays_dated_public_news(self):
        today = datetime.now(LOCAL_TIME).date()
        current = datetime.now(timezone.utc).isoformat()
        feed = {"news": {"articles": [
            {"title": "Bitcoin reage ao mercado", "url": "https://example.com/a", "source": "Fonte", "publishedAt": current, "summary": "Resumo."},
            {"title": "Bitcoin reage ao mercado", "url": "https://example.com/b", "source": "Outra", "publishedAt": current},
            {"title": "Documento privado", "url": "https://app.basecamp.com/d", "source": "Interno", "publishedAt": "2020-01-01T12:00:00Z"},
        ]}}
        with patch("news_agent._load", return_value=feed):
            result = run("Resumo das notícias de hoje")
        self.assertEqual(len(result["news"]), 1)
        self.assertEqual(result["news"][0]["title"], "Bitcoin reage ao mercado")
        self.assertIn(today.strftime("%d/%m/%Y"), result["reply"])

    def test_asset_excludes_research_and_internal_documents(self):
        current = datetime.now(LOCAL_TIME).date().isoformat()
        search = {"itens": [
            {"tipo": "casa", "origem": "basecamp", "titulo": "HYPE plano interno", "url": "https://app.basecamp.com/d", "data": current},
            {"tipo": "casa", "origem": "wordpress", "titulo": "HYPE research", "url": "https://example.com/research", "data": current},
            {"tipo": "noticia", "origem": "acervo", "titulo": "HYPE ganha destaque", "url": "https://example.com/news", "casa": "Fonte", "data": current, "previa": "HYPE em notícia."},
            {"tipo": "noticia", "origem": "acervo", "titulo": "Outra moeda", "url": "https://example.com/other", "casa": "Fonte", "data": current, "previa": "HYPE citado apenas no corpo."},
            {"tipo": "noticia", "origem": "basecamp", "titulo": "HYPE interno", "url": "https://example.com/internal", "data": current},
        ]}
        with patch("news_agent._load", return_value=search):
            result = run("notícias da HYPE")
        self.assertEqual([item["title"] for item in result["news"]], ["HYPE ganha destaque"])
        self.assertFalse(result["news"][0]["time_known"])


if __name__ == "__main__":
    unittest.main()
