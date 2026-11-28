"""Read-only Basecamp importer. Run with: python basecamp_import.py --help."""

import argparse
import io
import hashlib
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

TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".html", ".htm", ".pdf", ".docx", ".pptx", ".xlsx"}
VISUAL_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tiff", ".bmp", ".pdf", ".docx", ".pptx", ".xlsx"}
EXTRACTION_VERSION = 'multimodal-1'
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
    if suffix in {".docx", ".pptx", ".xlsx"}:
        from knowledge_extract import office_text
        return office_text(body, suffix)
    return ""


def queue_file(item, record, store, filename):
    suffix = Path(filename).suffix.lower()
    if suffix not in VISUAL_SUFFIXES and not str(item.get("content_type", "")).startswith("video/") \
            and suffix not in {".mp4", ".m4v", ".mov", ".webm"}:
        return
    if not item.get("download_url"):
        return
    from knowledge_video import api_download_url
    api_download_url(item["download_url"])
    revision = hashlib.sha256((EXTRACTION_VERSION + record["updated_at"] + filename
                              + str(item.get("byte_size", 0))).encode()).hexdigest()
    store.enqueue_content(record["key"], revision, {"record": record, "filename": filename,
        "download_url": item["download_url"], "mime": item.get("content_type", ""),
        "byte_size": int(item.get("byte_size") or 0)})


def import_file(account, item, record, store, stats):
    filename = item.get("filename") or record["title"]
    if import_video(item, record, store):
        queue_file(item, record, store, filename)
        return
    suffix = Path(filename).suffix.lower()
    queue_file(item, record, store, filename)
    if suffix == '.pdf' and int(item.get('byte_size') or 0) > MAX_ATTACHMENT_BYTES and item.get('download_url'):
        previous = store.db.execute('SELECT body FROM chunks WHERE source_key=? ORDER BY ordinal LIMIT 1',(record['key'],)).fetchone()
        placeholder = previous and ('Arquivo ainda sem extração de conteúdo' in previous[0]
                                    or previous[0].startswith('Arquivo excede o limite'))
        if placeholder or not store.unchanged(record['key'], record['updated_at']):
            store.upsert({**record,'body':'PDF disponível pela API; extração do documento grande em segundo plano.'})
        store.put_remote_pdf(record['key'],filename,item['download_url'],item.get('byte_size',0))
        return
    if store.unchanged(record["key"], record["updated_at"]) and (suffix != ".pdf" or store.has_pdf(record["key"])):
        return
    if suffix not in TEXT_SUFFIXES or int(item.get("byte_size") or 0) > MAX_ATTACHMENT_BYTES:
        record["body"] = html_text(item.get("description")) + (
            "\nLeitura visual pendente; o conteúdo da imagem ainda não foi extraído." if suffix in VISUAL_SUFFIXES else
            "\nArquivo ainda sem extração de conteúdo: formato ou tamanho não suportado.")
        stats["skipped"] += 1
        stats["updated"] += int(store.upsert(record))
        return
    download = account.download_url(item["download_url"]) if item.get("download_url") else account.uploads.download(upload_id=int(item["id"]))
    if suffix == '.pdf' and store.unchanged(record['key'], record['updated_at']) and len(download.body) <= MAX_ATTACHMENT_BYTES:
        store.put_pdf(record['key'], filename, download.body)
        return
    if len(download.body) > MAX_ATTACHMENT_BYTES:
        record["body"] = "Arquivo excede o limite de extração de 32 MiB; conteúdo não lido."
        stats["skipped"] += 1
    else:
        try:
            content = extract_upload(filename, download.body)
        except (ValueError, zipfile.BadZipFile, KeyError, PyPdfError):
            content = ""
        record["body"] = (html_text(item.get("description")) + "\n" + content).strip() or "Leitura de conteúdo pendente."
    stats["updated"] += int(store.upsert(record))
    if suffix == ".pdf" and len(download.body) <= MAX_ATTACHMENT_BYTES:
        store.put_pdf(record["key"], filename, download.body)


def source_record(item, kind, account_id, project):
    parent = item.get('parent') or {}
    parent_kind = {'Message': 'message', 'Document': 'document', 'Kanban::Card': 'card',
                   'Todo': 'todo', 'Upload': 'upload', 'Question::Answer': 'checkin'}.get(parent.get('type'))
    return {
        "key": f"{account_id}:{kind}:{item['id']}",
        "account_id": str(account_id), "project_id": str(project["id"]),
        "project_name": project["name"], "title": item.get("title") or item.get("filename") or kind,
        "url": item.get("app_url") or "", "updated_at": item.get("updated_at") or "",
        "kind": kind, "body": "",
        'parent_key': f"{account_id}:{parent_kind}:{parent['id']}" if parent_kind and parent.get('id') else '',
    }


def import_rich_content(account, item, record, store, seen, stats):
    """Index inline files as sources, retaining their parent/project provenance.

    Use the SDK's authenticated download hop and credential-free redirect.
    Browser preview URLs are not downloadable PDFs and must not be indexed.
    """
    record["body"] = html_text(item.get("content") or item.get('description'))
    provenance = []
    if item.get('created_at'):
        provenance.append('Publicado em ' + item['created_at'])
    if (item.get('creator') or {}).get('name'):
        provenance.append('Autor: ' + item['creator']['name'])
    if (item.get('parent') or {}).get('title'):
        provenance.append('Discussão/pergunta: ' + item['parent']['title'])
    if provenance:
        record['body'] = '[' + '; '.join(provenance) + ']\n' + record['body']
    if item.get('status') == 'archived':
        record['body'] = '[Registro arquivado; não assumir vigência atual]\n' + record['body']
    unavailable = []
    for attachment in (item.get("content_attachments") or []) + (item.get('description_attachments') or []):
        filename = attachment.get("filename") or "anexo"
        attachment_id = attachment.get("id")
        if not attachment_id:
            continue
        key = f"{record['key']}:attachment:{attachment_id}"
        seen.add(key)
        stats["examined"] += 1
        import_file(account, attachment, {**record, "key": key, "kind": "attachment",
            "parent_key": record['key'], "title": f"{record['title']} — {filename}"}, store, stats)
    if unavailable:
        record["body"] += "\n[Anexos mencionados, sem conteúdo textual importado: " + "; ".join(unavailable) + "]"
    seen.add(record["key"])
    stats["examined"] += 1
    stats["updated"] += int(store.upsert(record))


def import_video(item, record, store):
    suffix = Path(item.get("filename") or record["title"]).suffix.lower()
    mime = str(item.get("content_type") or "").lower().split(";", 1)[0]
    if not mime.startswith("video/") and suffix not in {".mp4", ".m4v", ".webm", ".mov"}:
        return False
    if not item.get("download_url"):
        return False
    if not re.fullmatch(r"video/[a-z0-9.+-]+", mime):
        mime = {".webm": "video/webm", ".mov": "video/quicktime"}.get(suffix, "video/mp4")
    description = html_text(item.get("description"))
    record["body"] = (description + "\nVídeo disponível no player da Alt-IA. "
                      "Título e descrição são metadados; vídeo sem transcrição indexada.")
    if not store.unchanged(record["key"], record["updated_at"]):
        store.upsert(record)
    store.put_video(record["key"], item.get("filename") or record["title"], item["download_url"],
                    mime or {".webm": "video/webm", ".mov": "video/quicktime"}.get(suffix, "video/mp4"),
                    item.get("byte_size", 0))
    return True


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
            import_file(account, item, record, store, stats)
    for board_id in boards:
        for item in account.messages.list(board_id=board_id):
            record = source_record(item, "message", account_id, project)
            if not item.get("content") or ("<bc-attachment" in item["content"] and "content_attachments" not in item):
                item = account.messages.get(message_id=int(item["id"]))
            import_rich_content(account, item, record, store, seen, stats)
    # Flat recordings catch archived files and attachments in discussions,
    # cards and check-in answers which are absent from the document vault.
    if hasattr(account, 'recordings'):
        kinds = [('Document', 'document'), ('Upload', 'upload'), ('Message', 'message'),
                 ('Comment', 'comment'), ('Kanban::Card', 'card'), ('Todo', 'todo'),
                 ('Question::Answer', 'checkin'), ('Schedule::Entry', 'schedule')]
        for api_kind, kind in kinds:
            for status in ('active', 'archived'):
                items = account.recordings.list(type=api_kind, bucket=str(project['id']), status=status)
                if getattr(getattr(items, 'meta', None), 'truncated', False):
                    raise RuntimeError('Paginação incompleta; nenhuma remoção será aplicada ao projeto')
                for item in items:
                    record = source_record(item, kind, account_id, project)
                    if record['key'] in seen:
                        continue
                    if kind == 'upload':
                        seen.add(record['key']); stats['examined'] += 1
                        import_file(account, item, record, store, stats)
                    else:
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
        print('Extrações:', dict(store.db.execute('SELECT status,count(*) FROM content_jobs GROUP BY status')))
        print('Tipos:', dict(store.db.execute('SELECT kind,count(*) FROM sources GROUP BY kind')))
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
        print(f"Sincronização concluída: {store.count()} fontes; {totals['skipped']} arquivos ignorados nesta passagem; consulte status para extrações pendentes.")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"Falha: {error}", file=sys.stderr)
        sys.exit(1)
