import unittest
from decimal import Decimal

from scenarios import pool_price_scenarios
from scenario_tokens import issue, verify
from simulator import parse_price_shock, simulate_price_shock


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

    def test_quote_token_rise_reverses_pair_price_and_calculates_six_decimals(self):
        self.pool.update(base_symbol="HYPE", quote_symbol="SOL")
        result = pool_price_scenarios(self.raw, self.pool, "1000", changes=(0, 35), shock_symbol="SOL")
        self.assertAlmostEqual(Decimal(result["analysis"]["target_price"]), Decimal(1) / Decimal("1.35"))
        self.assertEqual(result["rows"][1]["label"], "SOL +35%")
        self.assertNotEqual(result["rows"][1]["pnl"], "0,000000")

    def test_follow_up_uses_signed_basis_and_rejects_tampering(self):
        self.pool.update(base_symbol="HYPE", quote_symbol="SOL", id="test", pair="HYPE/SOL", network="Solana", protocol="Orca")
        basis = {"pool": self.pool, "capital": "1000", "raw": self.raw,
                 "source": {"block_number": 123, "source_label": "Slot", "captured_at": "2026-01-01T00:00:00Z"}}
        token = issue(basis, b"secret")
        self.assertEqual(verify(token, b"secret"), basis)
        self.assertIsNone(verify(token[:-1] + ("a" if token[-1] != "a" else "b"), b"secret"))
        shock = parse_price_shock("o que acontece na pool se SOL subir 35%?")
        result = simulate_price_shock(verify(token, b"secret"), shock)
        self.assertEqual(result["simulation"]["scenarios"]["rows"][1]["label"], "SOL +35%")
        self.assertIn("−", result["simulation"]["metrics"][2]["value"])
        self.assertEqual(parse_price_shock("e se o preço cair 20%?"), ("BASE", Decimal("-20")))


if __name__ == "__main__":
    unittest.main()
