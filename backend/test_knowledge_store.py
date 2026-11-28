import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from knowledge_store import KnowledgeStore, search_terms
from basecamp_import import html_text, source_record, scan_project
from knowledge_research import research, evidence_prompt, render_citations


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

    def seed_research(self):
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

    def test_research_uses_conversation_catalog_and_validated_source_ids(self):
        self.seed_research()
        messages = [{"role": "user", "content": "Explique a entrada gradual"},
                    {"role": "assistant", "content": "Podemos investigar compras no tempo."},
                    {"role": "user", "content": "e como ela se relaciona com nossa filosfia?"}]
        calls = []
        def complete(system, data):
            calls.append(data)
            self.assertEqual(data["conversation"], messages)
            self.assertEqual(len(data["catalog"]), 5)
            if len(calls) == 1:
                return {"intent": "explain", "source_ids": ["7:document:4", "injected-source"],
                        "queries": ["compras"], "question": "Relação entre entrada gradual e filosofia"}
            return {"source_ids": ["7:document:2"], "queries": [], "gaps": []}
        result = research(self.store, messages, complete)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["intent"], "explain")
        keys = {item["key"] for item in result["sources"]}
        self.assertEqual(keys, {"7:document:4", "7:document:2"})
        self.assertTrue(all(item["coverage"] == "complete" for item in result["sources"]))
        self.assertIn("filosofia", evidence_prompt(result))

    def test_research_failure_keeps_context_search_without_claiming_absence(self):
        self.seed_research()
        def unavailable(*args):
            raise TimeoutError()
        result = research(self.store, [{"role": "user", "content": "Compare a filosofia"},
                                      {"role": "user", "content": "e os riscos?"}], unavailable)
        self.assertEqual(result["status"], "degraded")
        self.assertTrue(result["sources"])
        self.assertTrue(result["gaps"])

    def test_review_discards_irrelevant_sources_and_preserves_citation_mapping(self):
        self.seed_research()
        calls = []
        def complete(*args):
            calls.append(args)
            if len(calls) == 1:
                return {"intent": "explain", "source_ids": ["7:document:1", "7:document:4"], "queries": ["compras"]}
            return {"keep_source_ids": ["7:document:4", "invented"], "source_ids": [], "queries": []}
        result = research(self.store, [{"role": "user", "content": "Como distribuir as entradas?"}], complete)
        self.assertEqual([item["key"] for item in result["sources"]], ["7:document:4"])
        self.assertEqual(render_citations("Entrada gradual [F1], inválido [F999]", result["sources"]),
                         "Entrada gradual [1], inválido ")

    def test_research_skips_irrelevant_base_without_retrieving_content(self):
        self.seed_research()
        calls = []
        def complete(*args):
            calls.append(args)
            return {"needs_knowledge": False, "intent": "other"}
        result = research(self.store, [{"role": "user", "content": "bom dia"}], complete)
        self.assertEqual(result["sources"], [])
        self.assertEqual(len(calls), 1)

    def test_long_document_reads_relevant_late_passages_and_reports_partial_coverage(self):
        self.store.upsert({"key": "7:document:90", "account_id": "7", "project_id": "42",
            "project_name": "Research", "title": "Manual.pdf", "url": "https://3.basecamp.com/doc/90",
            "kind": "upload", "updated_at": "2026-11-28",
            "body": ("Conteúdo introdutório amplo sem a resposta. " * 300) +
                    " Política específica de desligamento: revogar credenciais no mesmo dia. " +
                    ("Outro conteúdo extenso. " * 300)})
        self.store.save()
        rows = self.store.read_sources(["7:document:90", "not-real"], ["desligamento credenciais"], budget=3000)
        self.assertEqual(len(rows), 1)
        self.assertIn("revogar credenciais", rows[0]["excerpt"])
        self.assertEqual(rows[0]["coverage"], "partial")
        self.assertLessEqual(len(rows[0]["excerpt"]), 3000)

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

    def test_inline_attachment_content_is_indexed_cached_and_pruned_with_parent(self):
        item = {"id": 9, "title": "Procedimento", "app_url": "https://3.basecamp.com/doc/9",
                "updated_at": "2026-11-28", "content": "<p>Leia o anexo.</p>",
                "content_attachments": [
                    {"id": 10, "filename": "Manual.txt", "download_url": "https://storage.app.basecamp.com/file", "byte_size": 100},
                    {"id": 11, "filename": "Tutorial.mp4", "download_url": "https://storage.app.basecamp.com/video", "byte_size": 90000}]}
        calls = []
        class Account:
            projects = FakeService(detail={"dock": [{"id": 3, "name": "vault", "enabled": True}]})
            vaults = FakeService()
            documents = FakeService(items=[item])
            uploads = FakeService()
            messages = FakeService()
            def download_url(self, url):
                calls.append(url)
                return SimpleNamespace(body=b"Contratacao: revisar documentos antes de assinar.")
        self.store.select("7", {"42"})
        account = Account()
        scan_project(account, "7", {"id": 42, "name": "Empresa"}, self.store)
        hit = self.store.search("contratacao")[0]
        self.assertEqual(hit["title"], "Procedimento — Manual.txt")
        self.assertEqual(hit["url"], item["app_url"])
        scan_project(account, "7", {"id": 42, "name": "Empresa"}, self.store)
        self.assertEqual(len(calls), 1)
        item["updated_at"] = "2026-11-29"
        scan_project(account, "7", {"id": 42, "name": "Empresa"}, self.store)
        scan_project(account, "7", {"id": 42, "name": "Empresa"}, self.store)
        self.assertEqual(len(calls), 2)  # Metadata-only changes don't redownload forever.
        parent = self.store.read_sources(["7:document:9"], [])[0]
        self.assertIn("sem conteúdo textual importado", parent["excerpt"])
        self.assertIn("revisar documentos antes de assinar", parent["excerpt"])
        self.assertIn("Manual.txt", parent["excerpt"])
        self.assertEqual(len(parent["files"]), 2)
        Account.documents = FakeService()
        scan_project(account, "7", {"id": 42, "name": "Empresa"}, self.store)
        self.assertEqual(self.store.search("contratacao"), [])

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
