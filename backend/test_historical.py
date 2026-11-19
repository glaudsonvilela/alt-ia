import unittest

from historical import replay_pool_history


POOL = {"id": "base:uniswap-v3:weth-usdc-030", "pair": "WETH/USDC", "network": "Base Mainnet",
        "protocol": "Uniswap v3", "base_symbol": "WETH", "quote_symbol": "USDC", "tick_spacing": 60,
        "base_is_token0": True, "token0_decimals": 18, "token1_decimals": 6}


def chart(start_price=1800, end_price=1800, count=169):
    start_time = 1_790_000_000
    candles = []
    for index in range(count):
        price = start_price + (end_price - start_price) * index / (count - 1)
        candles.append({"time": start_time + index * 3600, "open": price, "high": price, "low": price, "close": price})
    return {"pool_id": POOL["id"], "interval": "1h", "source": "GeckoTerminal via Altside", "candles": candles, "stale": False}


class HistoricalReplayTests(unittest.TestCase):
    def test_flat_market_preserves_principal(self):
        result = replay_pool_history(chart(), POOL, "1000", 1200, 7)
        self.assertEqual(result["metrics"][3]["value"], "1.000,00 USDC")
        self.assertEqual(result["metrics"][4]["value"], "0,00 USDC")
        self.assertEqual(len(result["scenarios"]["rows"]), 5)
        self.assertEqual(result["source"]["kind"], "historical_candles")

    def test_down_market_shows_loss_and_hold_comparison(self):
        result = replay_pool_history(chart(1800, 1500), POOL, "1000", 1200, 7)
        self.assertTrue(result["metrics"][4]["value"].startswith("−"))
        self.assertTrue(result["metrics"][5]["value"].startswith("−"))
        self.assertEqual(result["scenarios"]["rows"][-1]["tone"], "loss")

    def test_rejects_incomplete_period(self):
        with self.assertRaises(ValueError):
            replay_pool_history(chart(count=30), POOL, "1000", 1200, 7)

    def test_rejects_pool_or_interval_mismatch(self):
        with self.assertRaises(ValueError):
            replay_pool_history({**chart(), "pool_id": "different"}, POOL, "1000", 1200, 7)


if __name__ == "__main__":
    unittest.main()
