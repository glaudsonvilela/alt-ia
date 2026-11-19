import unittest
from decimal import Decimal
from unittest.mock import patch

from wallet_agent import analyze_wallet
from wallet_lookup import WalletUnavailable


class WalletAgentTests(unittest.TestCase):
    def test_allocation_and_periods_use_fixed_current_holdings(self):
        def lookup(_):
            return {"network": "ethereum", "network_label": "Ethereum", "address": "0x" + "a" * 40,
                    "asset": "ETH", "balance_raw": "2000000000000000000", "decimals": 18,
                    "balance": "2,000000", "transactions": [], "reply": ""}

        def balances(_network, _address):
            return [{"symbol": "USDC", "quantity": Decimal("100"), "price_id": "ethereum:usdc", "source": "Ethereum RPC"}]

        def prices(_ids, _now):
            return {"now": {"coingecko:ethereum": Decimal("1000"), "ethereum:usdc": Decimal("1")},
                    "day": {"coingecko:ethereum": Decimal("900"), "ethereum:usdc": Decimal("1")},
                    "week": {"coingecko:ethereum": Decimal("1100"), "ethereum:usdc": Decimal("1")},
                    "month": {"coingecko:ethereum": Decimal("1000"), "ethereum:usdc": Decimal("1")}}

        result = analyze_wallet({"network": "ethereum", "address": "0x" + "a" * 40},
                                lookup=lookup, balances=balances, prices=prices, now=1000)
        self.assertEqual(result["total_usdc"], "2.100,00")
        self.assertAlmostEqual(result["allocation"][0]["percent"], 2000 / 2100 * 100)
        self.assertEqual(result["performance"][0]["change_usdc"], "+200,00")
        self.assertEqual(result["performance"][1]["change_usdc"], "-200,00")
        self.assertIn("não lucro real", result["reply"])

    def test_missing_history_is_unavailable(self):
        def lookup(_):
            return {"network": "bitcoin", "network_label": "Bitcoin", "address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
                    "asset": "BTC", "balance_raw": "100000000", "decimals": 8,
                    "balance": "1,000000", "transactions": [], "reply": ""}

        result = analyze_wallet({"network": "bitcoin", "address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"},
                                lookup=lookup, prices=lambda ids, now: {"now": {ids[0]: Decimal("50000")}}, now=1000)
        self.assertFalse(result["performance"][0]["available"])

    def test_falls_back_to_direct_chain_source_when_altside_is_loading(self):
        direct = {"network": "bitcoin", "network_label": "Bitcoin", "address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
                  "asset": "BTC", "balance_raw": "100000000", "decimals": 8,
                  "balance": "1,000000", "transactions": [], "source": "Blockstream"}
        with patch("wallet_agent.lookup_wallet", side_effect=WalletUnavailable("loading")), \
                patch("wallet_agent._native_fallback", return_value=direct):
            result = analyze_wallet({"network": "bitcoin", "address": direct["address"]},
                                    prices=lambda ids, now: {"now": {ids[0]: Decimal("50000")}}, now=1000)
        self.assertIn("Blockstream", result["sources"])


if __name__ == "__main__":
    unittest.main()
