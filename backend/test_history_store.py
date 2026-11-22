import os
import tempfile
import unittest

from cryptography.fernet import Fernet
from history_store import HistoryStore


class HistoryStoreTests(unittest.TestCase):
    def test_account_role_is_encrypted_and_usage_is_account_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(directory, "state.sqlite3")
            key_file = os.path.join(directory, "history.key")
            with open(key_file, "wb") as file:
                file.write(Fernet.generate_key())
            store = HistoryStore(database_path, key_file)
            store.set_role("ana@altside.com", "Consultora de investimentos")
            store.add_usage("ana@altside.com", 120, 45)
            store.add_usage("ana@altside.com", 20, 10)
            store.add_usage("bia@altside.com", 8, 5)
            self.assertEqual(store.account_for("ana@altside.com")["usage"],
                             {"prompt_tokens": 140, "completion_tokens": 55, "total_tokens": 195, "requests": 2})
            self.assertEqual(store.account_for("bia@altside.com")["role"], "")
            self.assertEqual(store.account_for("bia@altside.com")["usage"]["total_tokens"], 13)
            with open(database_path, "rb") as file:
                self.assertNotIn(b"Consultora de investimentos", file.read())
            with self.assertRaises(ValueError):
                store.set_role("ana@altside.com", "x" * 81)

    def test_account_isolation_encryption_and_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(directory, "state.sqlite3")
            key_file = os.path.join(directory, "history.key")
            with open(key_file, "wb") as file:
                file.write(Fernet.generate_key())
            store = HistoryStore(database_path, key_file, now=lambda: 2)
            conversation = {"id": "example-1", "title": "Minha estratégia", "updatedAt": 1000,
                            "messages": [{"role": "user", "text": "segredo da conversa"}]}
            store.save_for("ana@altside.com", [conversation])
            self.assertEqual(store.list_for("ana@altside.com")["conversations"], [conversation])
            self.assertEqual(store.list_for("bia@altside.com")["conversations"], [])
            newer = {**conversation, "title": "Estratégia revisada", "updatedAt": 1200}
            store.save_for("ana@altside.com", [newer])
            store.save_for("ana@altside.com", [conversation])
            self.assertEqual(store.list_for("ana@altside.com")["conversations"], [newer])
            with open(database_path, "rb") as file:
                self.assertNotIn(b"segredo da conversa", file.read())
            store.delete_for("ana@altside.com", "example-1")
            store.save_for("ana@altside.com", [conversation])
            self.assertEqual(store.list_for("ana@altside.com")["conversations"], [])
            self.assertEqual(store.list_for("ana@altside.com")["deleted"][0]["id"], "example-1")


if __name__ == "__main__":
    unittest.main()
