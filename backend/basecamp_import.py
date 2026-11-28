"""Read-only Basecamp importer. Run with: python basecamp_import.py --help."""

import argparse
import io
import json
import logging
import os
import re
import sys
import time
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from basecamp import Client
from basecamp.oauth import discover_from_resource, perform_device_login, refresh_token
from pypdf.errors import PyPdfError
from knowledge_store import KnowledgeStore, decrypt, encrypt, load_key, private_write

TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".html", ".htm", ".pdf", ".docx"}
MAX_ATTACHMENT_BYTES = 32 * 1024 * 1024
# Malformed PDF diagnostics can contain document bytes. Coverage is reported
# with counts below instead of writing parser internals to synchronization logs.
logging.getLogger("pypdf").addHandler(logging.NullHandler())
logging.getLogger("pypdf").propagate = False


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_text(value):
    parser = PlainText()
    parser.feed(value or "")
    return re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()


def extract_upload(filename, body):
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md", ".csv", ".json", ".yaml", ".yml"}:
        return body.decode("utf-8-sig", errors="replace")
    if suffix in {".html", ".htm"}:
        return html_text(body.decode("utf-8-sig", errors="replace"))
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(body))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
        uri = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        return "\n".join("".join(node.text or "" for node in para.iter(uri + "t"))
                         for para in root.iter(uri + "p"))
    return ""


def source_record(item, kind, account_id, project):
    return {
        "key": f"{account_id}:{kind}:{item['id']}",
        "account_id": str(account_id), "project_id": str(project["id"]),
        "project_name": project["name"], "title": item.get("title") or item.get("filename") or kind,
        "url": item.get("app_url") or "", "updated_at": item.get("updated_at") or "",
        "kind": kind, "body": "",
    }


def import_rich_content(account, item, record, store, seen, stats):
    """Index inline files as sources, retaining their parent/project provenance.

    Use the SDK's authenticated download hop and credential-free redirect.
    Browser preview URLs are not downloadable PDFs and must not be indexed.
    """
    record["body"] = html_text(item.get("content"))
    unavailable = []
    for attachment in item.get("content_attachments") or []:
        filename = attachment.get("filename") or "anexo"
        attachment_id = attachment.get("id")
        if not attachment_id:
            continue
        key = f"{record['key']}:attachment:{attachment_id}"
        seen.add(key)
        stats["examined"] += 1
        supported = Path(filename).suffix.lower() in TEXT_SUFFIXES
        too_large = int(attachment.get("byte_size") or 0) > MAX_ATTACHMENT_BYTES
        if not supported or too_large or not attachment.get("download_url"):
            unavailable.append(filename)
            stats["skipped"] += 1
            # Remove stale extracted text if an attachment changed format.
            store.upsert({**record, "key": key, "body": ""})
            continue
        is_pdf = Path(filename).suffix.lower() == ".pdf"
        unchanged = store.unchanged(key, record["updated_at"])
        if unchanged and (not is_pdf or store.has_pdf(key)):
            continue
        download = account.download_url(attachment["download_url"])
        if len(download.body) > MAX_ATTACHMENT_BYTES:
            unavailable.append(filename)
            stats["skipped"] += 1
            store.upsert({**record, "key": key, "body": ""})
            continue
        if unchanged and is_pdf:
            store.put_pdf(key, filename, download.body)
            continue
        try:
            content = extract_upload(filename, download.body)
        except (ValueError, zipfile.BadZipFile, KeyError, PyPdfError):
            content = ""
        if not content.strip():
            unavailable.append(filename)
            stats["skipped"] += 1
        stats["updated"] += int(store.upsert({**record, "key": key, "kind": "attachment",
            "title": f"{record['title']} — {filename}",
            "body": content or ("PDF disponível para leitura, sem texto extraível." if is_pdf else "")}))
        if is_pdf:
            store.put_pdf(key, filename, download.body)
    if unavailable:
        record["body"] += "\n[Anexos mencionados, sem conteúdo textual importado: " + "; ".join(unavailable) + "]"
    seen.add(record["key"])
    stats["examined"] += 1
    stats["updated"] += int(store.upsert(record))


def scan_project(account, account_id, project, store):
    details = account.projects.get(project_id=int(project["id"]))
    dock = details.get("dock") or []
    vaults = [int(item["id"]) for item in dock if item.get("name") == "vault" and item.get("enabled", True)]
    boards = [int(item["id"]) for item in dock if item.get("name") == "message_board" and item.get("enabled", True)]
    seen, stats = set(), {"updated": 0, "skipped": 0, "examined": 0}
    visited = set()
    while vaults:
        vault_id = vaults.pop()
        if vault_id in visited:
            continue
        visited.add(vault_id)
        for folder in account.vaults.list(vault_id=vault_id):
            vaults.append(int(folder["id"]))
        for item in account.documents.list(vault_id=vault_id):
            record = source_record(item, "document", account_id, project)
            if not item.get("content") or ("<bc-attachment" in item["content"] and "content_attachments" not in item):
                item = account.documents.get(document_id=int(item["id"]))
            import_rich_content(account, item, record, store, seen, stats)
        for item in account.uploads.list(vault_id=vault_id):
            record = source_record(item, "upload", account_id, project)
            seen.add(record["key"])
            stats["examined"] += 1
            filename = item.get("filename") or record["title"]
            is_pdf = Path(filename).suffix.lower() == ".pdf"
            unchanged = store.unchanged(record["key"], record["updated_at"])
            if unchanged and (not is_pdf or store.has_pdf(record["key"])):
                continue
            if Path(filename).suffix.lower() not in TEXT_SUFFIXES:
                record["body"] = html_text(item.get("description"))
                stats["skipped"] += 1
                stats["updated"] += int(store.upsert(record))
                continue
            download = account.uploads.download(upload_id=int(item["id"]))
            if unchanged and is_pdf:
                store.put_pdf(record["key"], filename, download.body)
                continue
            try:
                content = extract_upload(filename, download.body)
            except (ValueError, zipfile.BadZipFile, KeyError, PyPdfError):
                content = ""
            record["body"] = (html_text(item.get("description")) + "\n\n" + content).strip()
            if not content.strip():
                stats["skipped"] += 1
            if is_pdf and not record["body"]:
                record["body"] = "PDF disponível para leitura, sem texto extraível."
            stats["updated"] += int(store.upsert(record))
            if is_pdf:
                store.put_pdf(record["key"], filename, download.body)
    for board_id in boards:
        for item in account.messages.list(board_id=board_id):
            record = source_record(item, "message", account_id, project)
            if not item.get("content") or ("<bc-attachment" in item["content"] and "content_attachments" not in item):
                item = account.messages.get(message_id=int(item["id"]))
            import_rich_content(account, item, record, store, seen, stats)
    store.prune_project(account_id, project["id"], seen)
    return stats


def state_paths(directory):
    directory = Path(directory).expanduser()
    return directory / "knowledge.key", directory / "knowledge.enc", directory / "basecamp-token.enc"


def save_token(path, key, data):
    private_write(path, encrypt(key, json.dumps(data, separators=(",", ":")).encode("utf-8")))


def token_for(path, key):
    data = json.loads(decrypt(key, Path(path).read_bytes()))
    if data.get("expires_at") and time.time() + 300 >= data["expires_at"]:
        discovery = discover_from_resource("https://3.basecampapi.com")
        if discovery.kind != "selected":
            raise RuntimeError("Não consegui descobrir o servidor de autorização do Basecamp")
        fresh = refresh_token(discovery.selected_config().token_endpoint, data["refresh_token"],
                              client_id="basecamp-cli", resource=data.get("resource"))
        data = {"access_token": fresh.access_token, "refresh_token": fresh.refresh_token or data["refresh_token"],
                "expires_at": fresh.expires_at, "resource": fresh.resource or data.get("resource")}
        save_token(path, key, data)
    return data["access_token"]


def accounts(access_token):
    # The Python SDK's authorization.get() is fixed to legacy Launchpad. A
    # device token is issued by Basecamp itself, whose API root serves this
    # account discovery document for both modern and legacy tokens.
    request = urllib.request.Request("https://3.basecampapi.com/authorization.json", headers={
        "Authorization": f"Bearer {access_token}", "User-Agent": "Alt-IA Basecamp importer (glaudson@altside.com)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return [item for item in payload.get("accounts", []) if item.get("product") == "bc3"]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Basecamp → base de conhecimento criptografada da Alt-IA")
    parser.add_argument("--state-dir", default=os.environ.get("ALT_IA_KNOWLEDGE_DIR", "~/.config/alt-ia/knowledge"))
    parser.add_argument("--key-file", default=os.environ.get("ALT_IA_KNOWLEDGE_KEY_FILE"),
                        help="Caminho separado da chave de 32 bytes")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "authorize", "accounts", "list", "select", "sync", "status"):
        item = sub.add_parser(command)
        if command in {"list", "select", "sync"}:
            item.add_argument("--account", required=True, help="ID da conta Basecamp")
        if command == "select":
            item.add_argument("projects", nargs="+", help="IDs dos projetos autorizados para esta base")
    args = parser.parse_args(argv)
    default_key, db_path, token_path = state_paths(args.state_dir)
    key_path = Path(args.key_file) if args.key_file else default_key
    if args.command == "init":
        if not key_path.exists():
            private_write(key_path, os.urandom(32))
        if not db_path.exists():
            KnowledgeStore(db_path, key_path).save()
        print(f"Base iniciada em {db_path}; chave separada em {key_path}")
        return 0
    key = load_key(key_path)
    store = KnowledgeStore(db_path, key_path)
    if args.command == "status":
        print(f"Fontes: {store.count()}; autorização Basecamp: {'presente' if token_path.exists() else 'ausente'}")
        return 0
    if args.command == "authorize":
        discovery = discover_from_resource("https://3.basecampapi.com")
        if discovery.kind != "selected":
            raise RuntimeError("O servidor Basecamp não ofereceu autorização por dispositivo")
        def show(auth):
            print(f"Abra {auth.verification_uri} e digite o código {auth.user_code}", flush=True)
        token = perform_device_login(discovery.selected_config(), "basecamp-cli", scope="read", display=show)
        if not token.refresh_token:
            raise RuntimeError("O Basecamp não forneceu renovação; autorização não salva")
        save_token(token_path, key, {"access_token": token.access_token, "refresh_token": token.refresh_token,
                                     "expires_at": token.expires_at, "resource": token.resource})
        print("Autorização de leitura salva e criptografada.")
        return 0
    if not token_path.exists():
        raise RuntimeError("Autorize primeiro com o comando authorize")
    access_token = token_for(token_path, key)
    with Client(access_token=access_token) as client:
        matching = {str(item["id"]): item for item in accounts(access_token)}
        if args.command == "accounts":
            for item in matching.values():
                print(item["id"], item["name"])
            return 0
        if args.account not in matching:
            raise RuntimeError("Conta Basecamp não encontrada na autorização")
        account = client.for_account(args.account)
        projects = {str(item["id"]): item for item in account.projects.list()}
        if args.command == "list":
            for project in projects.values():
                print(project["id"], project["name"])
            return 0
        if args.command == "select":
            chosen = set(args.projects)
            if not chosen <= projects.keys():
                raise RuntimeError("Um ou mais projetos não estão acessíveis nessa conta")
            store.select(args.account, chosen)
            print(f"Projetos selecionados: {len(chosen)}")
            return 0
        selected = store.selected(args.account)
        if not selected:
            raise RuntimeError("Escolha projetos com select antes de sincronizar")
        totals = {"updated": 0, "skipped": 0, "examined": 0}
        for identifier in sorted(selected):
            if identifier not in projects:
                store.prune_project(args.account, identifier, set())
                continue
            stats = scan_project(account, args.account, projects[identifier], store)
            for key_name in totals:
                totals[key_name] += stats[key_name]
            print(f"{projects[identifier]['name']}: {stats['examined']} itens, {stats['updated']} atualizados, {stats['skipped']} sem texto", flush=True)
        store.save()
        print(f"Sincronização concluída: {store.count()} fontes; {totals['skipped']} arquivos sem texto pesquisável.")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"Falha: {error}", file=sys.stderr)
        sys.exit(1)
