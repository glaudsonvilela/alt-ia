import json
import unittest
from unittest.mock import patch

from research_agent import search_web


class ResearchAgentTests(unittest.TestCase):
    @patch("research_agent.urllib.request.urlopen")
    def test_keeps_distinct_public_sources_and_strips_markup(self, urlopen):
        results = {"results": [
            {"url": "https://example.org/a", "title": "<b>Ethereum</b> upgrade", "content": "<p>Technical details &amp; risks</p>"},
            {"url": "https://example.org/duplicate", "title": "Ethereum upgrade", "content": "Duplicate"},
            {"url": "http://example.org/unsafe", "title": "HTTP", "content": "No"},
            {"url": "https://127.0.0.1/secret", "title": "Private", "content": "No"},
        ]}
        urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(results).encode()
        result = search_web("Ethereum upgrade", "research")
        self.assertEqual(len(result["sources"]), 1)
        self.assertEqual(result["sources"][0]["title"], "Ethereum upgrade")
        self.assertEqual(result["sources"][0]["summary"], "Technical details & risks")

    @patch("research_agent.urllib.request.urlopen")
    def test_short_followup_uses_previous_subject(self, urlopen):
        urlopen.return_value.__enter__.return_value.read.return_value = b'{"results": []}'
        result = search_web("e os riscos?", "strategies", "staking de ETH")
        self.assertIn("staking de ETH", result["query"])
        self.assertIn("riscos", result["query"])
        requested_url = urlopen.call_args.args[0].full_url
        self.assertIn("estrat%C3%A9gia+DeFi", requested_url)


if __name__ == "__main__":
    unittest.main()
