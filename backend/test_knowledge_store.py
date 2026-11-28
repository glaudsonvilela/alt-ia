import os
import tempfile
import threading
import unittest
from pathlib import Path

from knowledge_store import KnowledgeStore, search_terms
from basecamp_import import html_text, source_record, scan_project


class FakeService:
    def __init__(self, items=None, detail=None):
        self.items = items or []
        self.detail = detail

    def list(self, **kwargs):
        return self.items

    def get(self, **kwargs):
        return self.detail


class KnowledgeStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.key = root / "key"
        self.key.write_bytes(os.urandom(32))
        self.path = root / "knowledge.enc"
        self.store = KnowledgeStore(self.path, self.key)

    def test_encryption_search_and_atomic_reload(self):
        self.store.select("7", {"42"})
        self.store.upsert({"key": "7:document:1", "account_id": "7", "project_id": "42",
            "project_name": "Estratégia", "title": "Política de risco", "url": "https://3.basecamp.com/doc/1",
            "kind": "document", "updated_at": "2026-11-01", "body": "Limite de exposição em Bitcoin por cliente."})
        self.store.save()
        encrypted = self.path.read_bytes()
        self.assertNotIn(b"Bitcoin", encrypted)
        self.assertNotIn(b"SQLite format 3", encrypted)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        other = KnowledgeStore(self.path, self.key)
        self.assertEqual(other.search("Qual o limite Bitcoin?")[0]["title"], "Política de risco")
        self.store.prune_project("7", "42", set())
        self.store.save()
        self.assertEqual(other.search("Bitcoin"), [])

    def test_wrong_key_rejected(self):
        self.store.save()
        wrong = Path(self.temp.name) / "wrong"
        wrong.write_bytes(os.urandom(32))
        with self.assertRaises(Exception):
            KnowledgeStore(self.path, wrong)

    def test_strategy_overview_uses_documents_instead_of_folder_guide(self):
        self.store.select("7", {"42"})
        for number, title, body in (
            (1, "GUIA PRÁTICO DAS PASTAS", "Este guia apresenta as pastas de estratégias da Altside. " * 8),
            (2, "FILOSOFIA DA ALTSIDE", "A filosofia da Altside considera objetivos, horizonte e risco. " * 7),
            (3, "PROCESSO DE RESEARCH", "A equipe compara hipóteses, fontes e cenários antes de recomendar. " * 7),
            (4, "MÉTODO DE ENTRADA DCA", "A estratégia de entrada distribui compras no tempo e observa risco. " * 7),
            (5, "Objetivos e Metas", "A empresa discute estratégias em suas metas anuais. " * 8),
        ):
            self.store.upsert({"key": f"7:document:{number}", "account_id": "7", "project_id": "42",
                "project_name": "Research", "title": title, "url": f"https://3.basecamp.com/doc/{number}",
                "kind": "document", "updated_at": "2026-11-28", "body": body})
        self.store.save()
        self.assertEqual(search_terms("Quais as estratégias da Altside?"), ["estrategia"])
        self.assertEqual(search_terms("Quero saber as estratégias da Altside"), ["estrategia"])
        titles = [item["title"] for item in self.store.research("Quais as estratégias da Altside?")]
        self.assertIn("FILOSOFIA DA ALTSIDE", titles)
        self.assertIn("PROCESSO DE RESEARCH", titles)
        self.assertIn("MÉTODO DE ENTRADA DCA", titles)
        self.assertNotIn("GUIA PRÁTICO DAS PASTAS", titles)
        self.assertNotIn("Objetivos e Metas", titles)

    def test_snapshot_reload_across_request_threads(self):
        self.store.select("7", {"42"})
        self.store.upsert({"key": "7:document:1", "account_id": "7", "project_id": "42",
            "project_name": "Empresa", "title": "Política", "url": "https://3.basecamp.com/doc/1",
            "kind": "document", "updated_at": "2026-11-01", "body": "Alocação de Bitcoin."})
        self.store.save()
        reader = KnowledgeStore(self.path, self.key)
        errors = []
        results = []

        def search():
            try:
                results.append(reader.search("Bitcoin"))
            except Exception as error:
                errors.append(error)

        first = threading.Thread(target=search)
        first.start()
        first.join()
        self.store.upsert({"key": "7:document:2", "account_id": "7", "project_id": "42",
            "project_name": "Empresa", "title": "Pesquisa", "url": "https://3.basecamp.com/doc/2",
            "kind": "document", "updated_at": "2026-11-02", "body": "Pesquisa sobre Ethereum."})
        self.store.save()
        second = threading.Thread(target=search)
        second.start()
        second.join()
        self.assertEqual(errors, [])
        self.assertEqual(results[0][0]["title"], "Política")
        self.assertEqual(reader.search("Ethereum")[0]["title"], "Pesquisa")

    def test_project_scan_is_scoped_and_prunes_old_items(self):
        item = {"id": 9, "title": "Estratégia", "app_url": "https://3.basecamp.com/doc/9",
                "updated_at": "2026-11-28", "content": "<p>Atender <strong>consultores</strong>.</p>"}
        class Account:
            projects = FakeService(detail={"dock": [{"id": 3, "name": "vault", "enabled": True}]})
            vaults = FakeService()
            documents = FakeService(items=[item])
            uploads = FakeService()
            messages = FakeService()
        self.store.select("7", {"42"})
        stats = scan_project(Account(), "7", {"id": 42, "name": "Empresa"}, self.store)
        self.assertEqual(stats["updated"], 1)
        self.assertEqual(self.store.search("consultores")[0]["project"], "Empresa")
        Account.documents = FakeService()
        scan_project(Account(), "7", {"id": 42, "name": "Empresa"}, self.store)
        self.assertEqual(self.store.search("consultores"), [])

    def test_unsupported_replacement_removes_old_file_text(self):
        self.store.select("7", {"42"})
        self.store.upsert({"key": "7:upload:4", "account_id": "7", "project_id": "42",
            "project_name": "Empresa", "title": "Manual.pdf", "url": "https://3.basecamp.com/file/4",
            "kind": "upload", "updated_at": "old", "body": "Procedimento confidencial obsoleto"})
        class Account:
            projects = FakeService(detail={"dock": [{"id": 3, "name": "vault", "enabled": True}]})
            vaults = FakeService()
            documents = FakeService()
            uploads = FakeService(items=[{"id": 4, "filename": "Imagem.png", "title": "Imagem.png",
                                          "updated_at": "new", "description": ""}])
            messages = FakeService()
        scan_project(Account(), "7", {"id": 42, "name": "Empresa"}, self.store)
        self.assertEqual(self.store.search("confidencial"), [])


if __name__ == "__main__":
    unittest.main()
