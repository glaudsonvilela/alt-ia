import unittest
from unittest.mock import patch

import lending_market
import simulator


WETH = {"symbol": "WETH", "address": "0x" + "1" * 40, "price": "2000", "supply_apy": "0.02",
        "borrow_apy": "0.04", "ltv": "0.8", "liquidation_threshold": "0.85",
        "can_supply": True, "can_borrow": True, "can_collateral": True}
USDC = {"symbol": "USDC", "address": "0x" + "2" * 40, "price": "1", "supply_apy": "0.03",
        "borrow_apy": "0.05", "ltv": "0.75", "liquidation_threshold": "0.8",
        "can_supply": True, "can_borrow": True, "can_collateral": True}
MARKET = {"name": "Aave V3 · Ethereum", "chain": "Ethereum", "chain_id": 1,
          "address": "0x" + "3" * 40, "updated_at": "2026-11-21T12:00:00+00:00", "assets": [WETH, USDC]}


class LendingMarketTests(unittest.TestCase):
    def request(self, **changes):
        data = {"kind": "lending", "version": 2, "chain_id": 1, "market_address": MARKET["address"],
                "supplies": [{"asset": WETH["address"], "amount": "10", "collateral": True}],
                "borrows": [{"asset": USDC["address"], "amount": "10000"}],
                "shock": {"asset": WETH["address"], "pct": -20}, "days": 30}
        return {**data, **changes}

    @patch.object(lending_market, "market", return_value=MARKET)
    def test_health_liquidation_and_interest(self, _):
        result = lending_market.simulate(self.request())
        sim = result["simulation"]
        self.assertEqual(sim["metrics"][4]["value"], "1,70")
        self.assertEqual(sim["scenarios"]["rows"][1]["value"], "1,36")
        self.assertEqual(sim["extra_tables"][0]["rows"][0]["value"], "US$ 1.176,47")
        self.assertEqual(sim["extra_tables"][1]["rows"][-1]["label"], "90 dias")

    @patch.object(lending_market, "market", return_value=MARKET)
    def test_multi_asset_and_price_override(self, _):
        supplies = self.request()["supplies"] + [{"asset": USDC["address"], "amount": "1000", "price": "1.1", "collateral": False}]
        result = lending_market.simulate(self.request(supplies=supplies, borrows=[]))
        self.assertEqual(result["simulation"]["metrics"][0]["value"], "US$ 21.100,00")
        self.assertEqual(result["simulation"]["metrics"][4]["value"], "Sem dívida")

    @patch.object(lending_market, "market", return_value=MARKET)
    def test_rejects_duplicate_or_unavailable_assets(self, _):
        with self.assertRaises(lending_market.LendingMarketError):
            lending_market.simulate(self.request(supplies=self.request()["supplies"] * 2))

    @patch.object(lending_market, "market")
    def test_kamino_borrow_factor_changes_health(self, lookup):
        reserve = "StGKGcLQoTsWzQ1tFY2bWqrdiuBhqdFE4niiAutQxQB"
        debt_reserve = "d4A2prbA2whesmvHaL88BH6Ewn5N4bTSU2Ze8P6Bc4Q"
        lookup.return_value = {**MARKET, "protocol": "kamino", "assets": [
            {**WETH, "address": reserve}, {**USDC, "address": debt_reserve, "borrow_factor": "1.25"}]}
        request = self.request(chain_id=101, market_address="7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF",
                               supplies=[{"asset": reserve, "amount": "10", "collateral": True}],
                               borrows=[{"asset": debt_reserve, "amount": "10000"}],
                               shock={"asset": reserve, "pct": -20})
        result = lending_market.simulate(request)
        self.assertEqual(result["simulation"]["metrics"][4]["value"], "1,36")
        self.assertEqual(result["simulation"]["scenarios"]["rows"][1]["value"], "1,09")

    def test_chat_followup_keeps_position_and_updates_days(self):
        previous = self.request()
        updated = simulator.lending_followup_request("e se ficar assim por 7 dias?", previous)
        self.assertEqual(updated["days"], 7)
        self.assertEqual(updated["supplies"], previous["supplies"])


if __name__ == "__main__":
    unittest.main()
