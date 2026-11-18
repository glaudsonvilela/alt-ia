import unittest
from unittest.mock import patch

import simulator


CATALOG = {"pools": [{
    "id": "base:uniswap-v3:weth-usdc-030",
    "display_pair": "WETH/USDC",
    "network": {"name": "Base Mainnet"},
    "protocol": {"name": "Uniswap v3"},
    "base_token": {"symbol": "WETH"},
    "quote_token": {"symbol": "USDC"},
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

    def test_noncanonical_result_is_rejected(self):
        invalid = {**SWAP, "source": {"canonical": False, "block_number": 456}}
        with patch.object(simulator, "_json_request", return_value=invalid):
            with self.assertRaises(simulator.SimulationUnavailable):
                simulator.handle_simulation("Simule swap de 100 USDC para WETH")


if __name__ == "__main__":
    unittest.main()
