import io
import json
import unittest

from wallet_lookup import WalletInputError, WalletUnavailable, lookup_wallet, parse_wallet_text, validate_request


class Response(io.BytesIO):
    def __init__(self, status, body):
        super().__init__(json.dumps(body).encode())
        self.status = status


class WalletLookupTests(unittest.TestCase):
    def test_rejects_invalid_address_before_request(self):
        with self.assertRaises(WalletInputError):
            validate_request({"network": "ethereum", "address": "0x123"})

    def test_chat_address_intent_respects_network(self):
        self.assertEqual(parse_wallet_text("rastreie a wallet 0x" + "a" * 40)["network"], "ethereum")
        self.assertEqual(parse_wallet_text("carteira Solana Du3Ysj1wKbxPKkuPPnvzQLQh8oMSVifs3jGZjJWXFmHN")["network"], "solana")
        self.assertIsNone(parse_wallet_text("me fale sobre a pool ETH/USDC"))

    def test_loading_then_returns_native_balance_and_transactions(self):
        address = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
        responses = iter([
            Response(202, {"status": "loading"}),
            Response(200, {"schema": "altside_wallet_address_lookup_v1", "status": "live", "wallet": {
                "network": "bitcoin", "address": address, "asset": "BTC", "balance_raw": "125000000",
                "decimals": 8, "value_usdc": "75000.25", "observed_at_unix_ms": 1760000000000,
                "transactions": [{"txid": "a" * 64, "direction": "received", "net_base_units": "50000000",
                                  "block_time_unix": 1760000000, "confirmed": True}],
            }}),
        ])
        result = lookup_wallet({"network": "bitcoin", "address": address}, attempts=2,
                               pause=lambda _: None, open_url=lambda *args, **kwargs: next(responses))
        self.assertEqual(result["balance"], "1,250000")
        self.assertEqual(result["value_usdc"], "75.000,25")
        self.assertEqual(result["transactions"][0]["amount"], "0,50000000")
        self.assertIn("consulta pontual", result["reply"])

    def test_loading_timeout_does_not_invent_balance(self):
        with self.assertRaises(WalletUnavailable):
            lookup_wallet({"network": "ethereum", "address": "0x" + "a" * 40}, attempts=2,
                          pause=lambda _: None, open_url=lambda *args, **kwargs: Response(202, {"status": "loading"}))

    def test_unclassified_contract_interaction_stays_visible_without_direction(self):
        address = "0x" + "a" * 40
        response = Response(200, {"schema": "altside_wallet_address_lookup_v1", "status": "live", "wallet": {
            "network": "ethereum", "address": address, "asset": "ETH", "balance_raw": "0", "decimals": 18,
            "transactions": [{"txid": "0x" + "b" * 64, "direction": "self_or_other", "net_base_units": "0",
                              "block_time_iso": "2026-11-18T07:45:35Z", "confirmed": True}],
        }})
        result = lookup_wallet({"network": "ethereum", "address": address}, attempts=1,
                               open_url=lambda *args, **kwargs: response)
        self.assertEqual(result["transactions"][0]["direction"], "self_or_other")
        self.assertIsNone(result["transactions"][0]["amount"])
        self.assertIsInstance(result["transactions"][0]["block_time_unix"], int)


if __name__ == "__main__":
    unittest.main()
