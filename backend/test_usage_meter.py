import unittest

import usage_meter


class UsageMeterTests(unittest.TestCase):
    def test_records_only_provider_reported_tokens_for_current_account(self):
        calls = []
        usage_meter.configure(lambda *args: calls.append(args))
        usage_meter.for_account("ana@altside.com")
        usage_meter.record({"usage": {"prompt_tokens": 10, "completion_tokens": 4}})
        usage_meter.record({"usage": {"total_tokens": 999}})
        self.assertEqual(calls, [("ana@altside.com", 10, 4)])
        usage_meter.configure(None)


if __name__ == "__main__":
    unittest.main()
