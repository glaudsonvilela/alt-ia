import unittest

from scenarios import pool_price_scenarios


class PoolScenarioTests(unittest.TestCase):
    def setUp(self):
        self.pool = {"base_symbol": "WETH", "quote_symbol": "USDC", "base_is_token0": True,
                     "token0_decimals": 0, "token1_decimals": 0}
        self.raw = {
            "allocation": {"formatted": {"base_required": "500", "quote_required": "500", "unused_quote": "0"}},
            "range": {"tick_lower": -1000, "tick_upper": 1000},
            "position_descriptor": {"entry_sqrt_price_x96": str(2**96)},
        }

    def test_price_scenarios_show_gain_and_loss_without_future_fees(self):
        result = pool_price_scenarios(self.raw, self.pool, "1000")
        self.assertEqual(result["unit"], "USDC")
        self.assertEqual([row["label"] for row in result["rows"]],
                         ["Queda 20%", "Queda 10%", "Preço atual", "Alta 10%", "Alta 20%"])
        self.assertEqual(result["rows"][2]["value"], "1.000,00")
        self.assertEqual(result["rows"][2]["pnl"], "0,00")
        self.assertEqual(result["rows"][0]["tone"], "loss")
        self.assertEqual(result["rows"][-1]["tone"], "gain")
        self.assertIn("sem taxas futuras", result["note"])

    def test_inverted_token_order_keeps_quote_per_base_orientation(self):
        self.pool["base_is_token0"] = False
        result = pool_price_scenarios(self.raw, self.pool, "1000")
        self.assertEqual(result["rows"][2]["price"], "1,00")
        self.assertEqual(result["rows"][2]["pnl"], "0,00")

    def test_non_reconciling_allocation_is_not_displayed(self):
        self.raw["allocation"]["formatted"]["unused_quote"] = "100"
        with self.assertRaises(ValueError):
            pool_price_scenarios(self.raw, self.pool, "1000")


if __name__ == "__main__":
    unittest.main()
