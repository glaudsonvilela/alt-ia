import unittest
from unittest.mock import patch

import simulator


CATALOG = {"pools": [{
    "id": "base:uniswap-v3:weth-usdc-030",
    "display_pair": "WETH/USDC",
    "network": {"name": "Base Mainnet"},
    "protocol": {"name": "Uniswap v3"},
    "base_token": {"symbol": "WETH", "address": "0x4200"},
    "quote_token": {"symbol": "USDC", "address": "0x8335"},
    "token0": {"address": "0x4200", "decimals": 18},
    "token1": {"address": "0x8335", "decimals": 6},
    "tick_spacing": 60,
    "capabilities": {"simulation_engine": "canonical_entry_preview"},
}]}
POOL = {
    "read_only": True,
    "simulation_type": "canonical_concentrated_liquidity_entry_preview",
    "pool_id": CATALOG["pools"][0]["id"],
    "source": {"canonical": True, "block_number": 123, "block_timestamp": 1795045000},
    "allocation": {"formatted": {"base_required": "0.2", "quote_required": "500", "unused_quote": "0"}},
}
SWAP = {
    "read_only": True,
    "quote_type": "uniswap_v3_exact_input_single",
    "source": {"canonical": True, "block_number": 456},
    "route": {"network": "Ethereum Mainnet", "protocol": "uniswap_v3", "fee_percent": "0.05%"},
    "input": {"asset": "USDC", "amount": "100"},
    "output": {"asset": "WETH", "expected_amount": "0.05", "minimum_amount": "0.0499"},
}
SNAPSHOT = {
    "snapshot_type": "altside_selected_pool_live_snapshot",
    "pool_id": CATALOG["pools"][0]["id"],
    "source": {"canonical": True, "block_number": 789},
    "state": {"tick": -201496},
    "price": {"status": "available", "quote_per_base": "1776.5"},
}
CHART = {"schema": "altside_pool_chart_v1", "pool_id": CATALOG["pools"][0]["id"], "interval": "1h",
         "source": "geckoterminal", "stale": False, "fetched_at_unix": 1795045000,
         "candles": [{"time": 1795042800, "open": 1780.0, "high": 1790.0, "low": 1770.0, "close": 1784.0}]}


class SimulatorTests(unittest.TestCase):
    def test_swap_calls_engine_with_explicit_amount(self):
        with patch.object(simulator, "_json_request", return_value=SWAP) as request:
            result = simulator.handle_simulation("Simule swap de 100 USDC para WETH com slippage de 0,2%")
        request.assert_called_once_with("/simulate/swap-quote", {
            "token_in": "USDC", "token_out": "WETH", "amount_in": "100", "slippage_bps": 20,
        })
        self.assertEqual(result["simulation"]["source"]["block_number"], 456)

    def test_missing_swap_amount_does_not_call_engine(self):
        with patch.object(simulator, "_json_request") as request:
            result = simulator.handle_simulation("Simule swap de ETH para USDC")
        request.assert_not_called()
        self.assertIn("Qual valor", result["reply"])

    def test_pool_uses_catalog_and_canonical_engine(self):
        with patch.object(simulator, "_json_request", side_effect=[CATALOG, POOL]) as request:
            result = simulator.handle_simulation("Simule entrada de 1000 USDC na pool WETH/USDC da Base com faixa de 1200 ticks")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.args[1], {"capital_quote": "1000", "range_ticks": 1200, "slippage_bps": 20})
        self.assertEqual(result["simulation"]["metrics"][1]["value"], "0.2 WETH")

    def test_incomplete_pool_request_opens_configuration(self):
        with patch.object(simulator, "_json_request", return_value=CATALOG) as request:
            result = simulator.handle_simulation("Quero simular uma pool WETH/USDC da Base")
        request.assert_called_once_with("/markets/pools")
        self.assertEqual(result["input_request"]["kind"], "pool")
        self.assertEqual(result["input_request"]["pool_id"], CATALOG["pools"][0]["id"])

    def test_structured_pool_request_rejects_unknown_pool(self):
        with patch.object(simulator, "_json_request", return_value=CATALOG):
            with self.assertRaises(simulator.SimulationInputError):
                simulator.simulate_pool_request({"kind": "pool", "pool_id": "unknown", "capital_quote": "1000", "range_ticks": 1200, "slippage_bps": 20})

    def test_structured_pool_request_uses_selected_parameters(self):
        with patch.object(simulator, "_json_request", side_effect=[CATALOG, POOL]) as request:
            result = simulator.simulate_pool_request({"kind": "pool", "pool_id": CATALOG["pools"][0]["id"], "capital_quote": "2500,50", "range_ticks": 1800, "slippage_bps": 35})
        self.assertEqual(request.call_args.args[1], {"capital_quote": "2500.50", "range_ticks": 1800, "slippage_bps": 35})
        self.assertEqual(result["simulation"]["kind"], "pool")

    def test_snapshot_returns_canonical_tick_for_range_chart(self):
        with patch.object(simulator, "_json_request", side_effect=[CATALOG, SNAPSHOT]) as request:
            result = simulator.pool_snapshot(CATALOG["pools"][0]["id"])
        self.assertEqual(request.call_count, 2)
        self.assertEqual(result["current_tick"], -201496)
        self.assertEqual(result["block_number"], 789)

    def test_pool_chart_uses_real_ohlc(self):
        with patch.object(simulator, "_json_request", side_effect=[CATALOG, CHART]):
            result = simulator.pool_chart(CATALOG["pools"][0]["id"], "1h")
        self.assertEqual(result["candles"][0]["high"], 1790.0)

    def test_pool_chart_rejects_invalid_candle(self):
        invalid = {**CHART, "candles": [{**CHART["candles"][0], "low": 1800.0}]}
        with patch.object(simulator, "_json_request", side_effect=[CATALOG, invalid]):
            with self.assertRaises(simulator.SimulationUnavailable):
                simulator.pool_chart(CATALOG["pools"][0]["id"], "1h")

    def test_dragged_bounds_are_sent_to_engine(self):
        payload = {"kind": "pool", "pool_id": CATALOG["pools"][0]["id"], "capital_quote": "1000",
                   "range_ticks": 1260, "slippage_bps": 20, "tick_lower": -202080, "tick_upper": -200820}
        with patch.object(simulator, "_json_request", side_effect=[CATALOG, POOL]) as request:
            result = simulator.simulate_pool_request(payload)
        self.assertEqual(request.call_args.args[1]["tick_lower"], -202080)
        self.assertEqual(request.call_args.args[1]["tick_upper"], -200820)
        self.assertIn("-202080 a -200820", result["simulation"]["assumptions"][0])

    def test_unaligned_dragged_bounds_are_rejected(self):
        payload = {"kind": "pool", "pool_id": CATALOG["pools"][0]["id"], "capital_quote": "1000",
                   "range_ticks": 1260, "slippage_bps": 20, "tick_lower": -202081, "tick_upper": -200821}
        with patch.object(simulator, "_json_request", return_value=CATALOG):
            with self.assertRaises(simulator.SimulationInputError):
                simulator.simulate_pool_request(payload)

    def test_noncanonical_result_is_rejected(self):
        invalid = {**SWAP, "source": {"canonical": False, "block_number": 456}}
        with patch.object(simulator, "_json_request", return_value=invalid):
            with self.assertRaises(simulator.SimulationUnavailable):
                simulator.handle_simulation("Simule swap de 100 USDC para WETH")


if __name__ == "__main__":
    unittest.main()
