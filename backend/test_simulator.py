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
    def test_in_range_earnings_are_explicit_fee_scenarios(self):
        basis = {"pool": {"pair": "WETH/USDC", "network": "Base Mainnet", "base_symbol": "WETH", "quote_symbol": "USDC"},
                 "capital": "1000", "source": {"canonical": True, "block_number": 123}}
        self.assertEqual(simulator.in_range_days("Quanto eu ganharia se a pool permanecesse nessa range por 7 dias?"), 7)
        result = simulator.simulate_in_range_days(basis, 7)
        rows = result["simulation"]["scenarios"]["rows"]
        self.assertEqual([row["pnl"] for row in rows], ["0,00 USDC", "+3,50 USDC", "+7,00 USDC"])
        self.assertIn("não são rendimentos previstos", result["reply"])
        self.assertEqual(result["mode"], "pool")

    def test_multichain_catalog_marks_live_and_history_capabilities(self):
        robinhood = {**CATALOG["pools"][0], "id": "robinhood:uniswap-v3:weth-usdg-001",
                     "network": {"name": "Robinhood Chain Mainnet"}, "capabilities": {"simulation_engine": "robinhood_usdg_entry_preview"}}
        hyper = {**CATALOG["pools"][0], "id": "hyperevm:project-x-v3:khype-usdc-030",
                 "network": {"name": "HyperEVM Mainnet"}, "capabilities": {"simulation_engine": "hyperevm_analytical_preview"}}
        solana = {**CATALOG["pools"][0], "id": "svm:solana:orca:whirlpool:Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE",
                  "network": {"name": "Solana Mainnet"}, "capabilities": {"simulation_engine": "orca_entry_preview"}}
        with patch.object(simulator, "_json_request", return_value={"pools": [robinhood, hyper, solana]}):
            options = simulator.pool_options()
        self.assertEqual([item["simulation_available"] for item in options], [True, True, True])
        self.assertEqual([item["chart_available"] for item in options], [True, True, True])

    def test_sol_usdc_chart_uses_verified_orca_route(self):
        solana = {**CATALOG["pools"][0], "id": "svm:solana:orca:whirlpool:Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE",
                  "base_token": {"symbol": "SOL", "address": "sol"}, "quote_token": {"symbol": "USDC", "address": "usdc"},
                  "capabilities": {"simulation_engine": "orca_entry_preview"}}
        chart = {**CHART, "schema": "altside_orca_chart_v1", "pool_id": "orca"}
        with patch.object(simulator, "_json_request", side_effect=[{"pools": [solana]}, chart]) as request:
            result = simulator.pool_chart(solana["id"], "1h")
        self.assertEqual(result["pool_id"], solana["id"])
        self.assertEqual(request.call_args.args[0], "/markets/orca-chart?interval=1h")

    def test_legacy_pool_calls_read_only_rust_route(self):
        pool = {**CATALOG["pools"][0], "id": "ethereum:uniswap-v3:weth-usdc-005",
                "capabilities": {"simulation_engine": "legacy_weth_usdc"}}
        raw = {"simulation": "uniswap_v3_equal_value_position", "stateless": True, "persisted": False,
               "source": {"canonical": True, "block_number": 123},
               "market": {"weth_price_usdc_x6": "2000000000"},
               "position": {"weth_used_raw": "250000000000000000", "usdc_used_raw": "499000000",
                            "capital_unused_usdc_x6": "1000000", "tick_lower": -204000, "tick_upper": -202800}}
        with patch.object(simulator, "_json_request", side_effect=[{"pools": [pool]}, raw]) as request:
            result = simulator.simulate_pool_request({"kind": "pool", "pool_id": pool["id"],
                "capital_quote": "1000", "range_ticks": 1200, "slippage_bps": 20})
        self.assertEqual(request.call_args.args, ("/simulate/pool", {"capital_usdc": 1000, "range_ticks": 600}))
        self.assertEqual(result["simulation"]["metrics"][1]["value"], "0.25 WETH")

    def test_hyperevm_analytical_preview_is_labeled_as_estimate(self):
        pool = {**CATALOG["pools"][0], "id": "hyperevm:project-x-v3:khype-usdc-030",
                "capabilities": {"simulation_engine": "hyperevm_analytical_preview"}}
        snapshot = {**SNAPSHOT, "pool_id": pool["id"], "price": {"status": "available", "quote_per_base": "1776.5"}}
        with patch.object(simulator, "_json_request", side_effect=[{"pools": [pool]}, snapshot]):
            result = simulator.simulate_pool_request({"kind": "pool", "pool_id": pool["id"],
                "capital_quote": "1000", "range_ticks": 1200, "slippage_bps": 20})
        self.assertEqual(result["simulation"]["source"]["engine"], "Alt-IA · preço Altside")
        self.assertEqual(len(result["simulation"]["scenarios"]["rows"]), 5)

    def test_registered_orca_pool_uses_read_only_budget_and_slot(self):
        pool = {**CATALOG["pools"][0], "id": "svm:solana:orca:whirlpool:31KrYUDzgEQhEgr1JSNVfHAknWACcF97CtUaU8enKQsy",
                "base_token": {"symbol": "HYPE", "address": "hype"}, "quote_token": {"symbol": "SOL", "address": "sol"},
                "token0": {"address": "sol", "decimals": 9}, "token1": {"address": "hype", "decimals": 9},
                "tick_spacing": 64, "capabilities": {"simulation_engine": "orca_entry_preview"}}
        snapshot = {**SNAPSHOT, "pool_id": pool["id"], "source": {"canonical": True, "slot": 500},
                    "state": {"tick": 939}, "price": {"status": "available", "quote_per_base": "0.9"}}
        budget = {"pool_id": pool["id"], "read_only": True, "writes_performed": False,
                  "commitment": "confirmed", "slot": 501, "age_ms": 1000,
                  "budget": {"capital_raw": "1000000000", "capital_symbol": "SOL",
                             "tick_lower": 320, "tick_upper": 1600,
                             "deposit_a_raw": "510000000", "deposit_b_raw": "530000000",
                             "residual_a_raw": "1000000", "residual_b_raw": "2000000"}}
        with patch.object(simulator, "_json_request", side_effect=[{"pools": [pool]}, snapshot, budget]) as request:
            result = simulator.simulate_pool_request({"kind": "pool", "pool_id": pool["id"],
                "capital_quote": "1", "range_ticks": 1200, "slippage_bps": 20})
        self.assertIn("/solana/orca/pools/hype-sol/budget-preview?capital_raw=1000000000", request.call_args.args[0])
        self.assertEqual(result["simulation"]["source"]["source_label"], "Slot")
        self.assertEqual(len(result["simulation"]["scenarios"]["rows"]), 5)

    def test_historical_prompt_opens_historical_configuration(self):
        with patch.object(simulator, "_json_request", return_value=CATALOG):
            result = simulator.handle_simulation("Simule o histórico de 30 dias da pool WETH/USDC na Base")
        self.assertEqual(result["input_request"], {"kind": "historical_pool", "pool_id": CATALOG["pools"][0]["id"], "period_days": 30})

    def test_historical_request_uses_altside_candles(self):
        with patch.object(simulator, "_json_request", return_value=CATALOG), patch.object(simulator, "pool_chart", return_value=CHART) as chart, patch.object(simulator, "replay_pool_history", return_value={"kind": "historical_pool"}) as replay:
            result = simulator.simulate_pool_request({"kind": "historical_pool", "pool_id": CATALOG["pools"][0]["id"], "capital_quote": "1000", "range_ticks": 1200, "period_days": 7})
        chart.assert_called_once_with(CATALOG["pools"][0]["id"], "1h")
        replay.assert_called_once()
        self.assertEqual(result["simulation"]["kind"], "historical_pool")

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

    def test_short_pool_followup_uses_previous_parameters(self):
        previous = {"kind": "pool", "pool_id": CATALOG["pools"][0]["id"], "capital_quote": "1000",
                    "range_ticks": 1260, "slippage_bps": 20, "tick_lower": -202080, "tick_upper": -200820}
        new_capital = simulator.pool_followup_request("e com 2000 USDC?", previous)
        self.assertEqual(new_capital["capital_quote"], "2000")
        self.assertEqual(new_capital["range_ticks"], 1260)
        new_range = simulator.pool_followup_request("e faixa de 1800 ticks?", previous)
        self.assertEqual(new_range["range_ticks"], 1800)
        self.assertNotIn("tick_lower", new_range)
        self.assertIsNone(simulator.pool_followup_request("e as notícias?", previous))

    def test_implicit_price_shock_requires_pool_context(self):
        self.assertIsNone(simulator.parse_price_shock("e se cair 20%?"))
        self.assertEqual(simulator.parse_price_shock("e se cair 20%?", allow_implicit=True), ("BASE", -simulator.Decimal("20")))


if __name__ == "__main__":
    unittest.main()
