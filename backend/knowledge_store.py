"""Encrypted, whole-file SQLite knowledge snapshot and source retrieval.

The SQLite database and its FTS index exist only in process memory. The file on
disk is an AES-GCM ciphertext; replacing it is atomic, so API workers can read
the last complete snapshot while an import is running.
"""

import hashlib
import fcntl
import json
import os
import re
import secrets
import sqlite3
import tempfile
import threading
import time
from collections import OrderedDict
import unicodedata
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


MAGIC = b"ALTIA-KB-1\0"
WORD = re.compile(r"[^\W_]{3,}", re.UNICODE)
STOP = {"para", "como", "qual", "quais", "sobre", "mais", "essa", "esse", "isso", "uma", "com", "que", "dos", "das", "por", "the", "and", "sao", "sua", "suas", "principais", "quero", "saber", "fale", "explique", "mostre", "descreva", "resuma", "resumo", "liste", "lista", "conte", "empresa"}


def search_terms(query):
    plain = unicodedata.normalize("NFKD", query.lower())
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    terms = list(dict.fromkeys(word[:-1] if word.endswith("s") and len(word) > 5 else word
                               for word in WORD.findall(plain) if word not in STOP))[:16]
    focused = [word for word in terms if word not in {"altside", "altia"}]
    return focused or terms


def load_key(path):
    key = Path(path).read_bytes()
    if len(key) != 32:
        raise ValueError("A chave da base deve conter exatamente 32 bytes")
    return key


def private_write(path, data):
    target = Path(path)
    # API and worker may use different UIDs. Atomic replacement must retain
    # the private directory's owner; otherwise a root API strands the worker.
    missing = []
    parent = target.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    owner = parent.stat()
    for directory in reversed(missing):
        directory.mkdir(mode=0o700, exist_ok=True)
        if os.geteuid() == 0:
            os.chown(directory, owner.st_uid, owner.st_gid)
    owner = target.parent.stat()
    fd, temporary = tempfile.mkstemp(prefix=".altia-", dir=target.parent)
    try:
        os.fchmod(fd, 0o600)
        if os.geteuid() == 0:
            os.fchown(fd, owner.st_uid, owner.st_gid)
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def encrypt(key, plaintext):
    nonce = secrets.token_bytes(12)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, plaintext, MAGIC)


def decrypt(key, ciphertext):
    if not ciphertext.startswith(MAGIC) or len(ciphertext) < len(MAGIC) + 29:
        raise ValueError("Arquivo criptografado inválido")
    nonce = ciphertext[len(MAGIC):len(MAGIC) + 12]
    return AESGCM(key).decrypt(nonce, ciphertext[len(MAGIC) + 12:], MAGIC)


def chunk_text(text, size=1400, overlap=180):
    # Never merge different pages/time intervals into an unlabeled passage.
    # Repeat the origin on long pages so later chunks retain their provenance.
    boundaries = list(re.finditer(r'(?m)^\[(?:Página \d+/\d+|Vídeo \d{2}:\d{2}:\d{2}[^\]\n]*)\]', text))
    if boundaries:
        output = chunk_text(text[:boundaries[0].start()], size, overlap)
        for index, match in enumerate(boundaries):
            end = boundaries[index+1].start() if index+1 < len(boundaries) else len(text)
            label = match.group(0)
            parts = chunk_text(text[match.end():end], max(300,size-len(label)-1), overlap)
            output.extend(label+' '+part for part in (parts or ['']))
        return output
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + size // 2, end)
            if boundary > start:
                end = boundary
        chunks.append(text[start:end].strip())
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


class KnowledgeStore:
    def __init__(self, path, key_file):
        self.path = Path(path)
        self.key = load_key(key_file)
        self.lock = threading.RLock()
        self.pdf_cache = OrderedDict()
        self.signature = None
        self.db = None
        self._reload(force=True)

    def _reload(self, force=False):
        with self.lock:
            try:
                stat = self.path.stat()
                signature = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
            except FileNotFoundError:
                signature = None
            if not force and signature == self.signature:
                return
            # ThreadingHTTPServer handles each request in a different thread.
            # The lock below serializes access to this shared connection.
            db = sqlite3.connect(":memory:", check_same_thread=False)
            if signature is not None:
                db.deserialize(decrypt(self.key, self.path.read_bytes()))
            else:
                db.executescript("""
                    CREATE TABLE sources (
                        source_key TEXT PRIMARY KEY, account_id TEXT NOT NULL,
                        project_id TEXT NOT NULL, project_name TEXT NOT NULL,
                        title TEXT NOT NULL, url TEXT NOT NULL, kind TEXT NOT NULL,
                        updated_at TEXT NOT NULL, digest TEXT NOT NULL
                    );
                    CREATE TABLE chunks (
                        id INTEGER PRIMARY KEY, source_key TEXT NOT NULL REFERENCES sources(source_key),
                        ordinal INTEGER NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL
                    );
                    CREATE VIRTUAL TABLE chunks_fts USING fts5(
                        title, body, content='chunks', content_rowid='id',
                        tokenize='unicode61 remove_diacritics 2'
                    );
                    CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
                        INSERT INTO chunks_fts(rowid,title,body) VALUES(new.id,new.title,new.body);
                    END;
                    CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
                        INSERT INTO chunks_fts(chunks_fts,rowid,title,body)
                        VALUES('delete',old.id,old.title,old.body);
                    END;
                    CREATE TABLE selection (
                        account_id TEXT NOT NULL, project_id TEXT NOT NULL,
                        PRIMARY KEY(account_id,project_id)
                    );
                """)
            old = self.db
            db.execute("""CREATE TABLE IF NOT EXISTS document_files (
                id TEXT PRIMARY KEY, source_key TEXT NOT NULL UNIQUE, filename TEXT NOT NULL,
                digest TEXT NOT NULL, mime TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS video_files (
                id TEXT PRIMARY KEY, source_key TEXT NOT NULL UNIQUE, filename TEXT NOT NULL,
                download_url TEXT NOT NULL, mime TEXT NOT NULL, byte_size INTEGER NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS remote_pdf_files (
                id TEXT PRIMARY KEY, source_key TEXT NOT NULL UNIQUE, filename TEXT NOT NULL,
                download_url TEXT NOT NULL, byte_size INTEGER NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS content_jobs (
                source_key TEXT PRIMARY KEY, revision TEXT NOT NULL, payload TEXT NOT NULL,
                status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                detail TEXT NOT NULL DEFAULT '', progress TEXT NOT NULL DEFAULT '{}'
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS extraction_cache (
                digest TEXT PRIMARY KEY, body TEXT NOT NULL
            )""")
            db.execute('CREATE TABLE IF NOT EXISTS source_links (child_key TEXT PRIMARY KEY, parent_key TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS chunks_source_ordinal ON chunks(source_key,ordinal)')
            db.execute('CREATE INDEX IF NOT EXISTS links_parent ON source_links(parent_key)')
            db.execute('CREATE TABLE IF NOT EXISTS video_previews (source_key TEXT PRIMARY KEY, url TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS content_priority (source_key TEXT PRIMARY KEY, requested_at REAL NOT NULL)')
            self.db = db
            self.signature = signature
            if old is not None:
                old.close()

    def save(self):
        with self.lock:
            private_write(self.path, encrypt(self.key, self.db.serialize()))
            stat = self.path.stat()
            self.signature = (stat.st_ino, stat.st_mtime_ns, stat.st_size)

    def select(self, account_id, project_ids):
        with self.lock, self.db:
            self.db.execute("DELETE FROM selection WHERE account_id=?", (str(account_id),))
            self.db.executemany("INSERT INTO selection VALUES (?,?)", [(str(account_id), str(i)) for i in project_ids])
            selected = {str(i) for i in project_ids}
            stale = [row[0] for row in self.db.execute("SELECT source_key FROM sources WHERE account_id=? AND project_id NOT IN (SELECT project_id FROM selection WHERE account_id=?)", (str(account_id), str(account_id)))]
            for key in stale:
                self._delete(key)
        self.save()

    def selected(self, account_id):
        with self.lock:
            return {row[0] for row in self.db.execute("SELECT project_id FROM selection WHERE account_id=?", (str(account_id),))}

    def _delete(self, key):
        self.video_text_path(key).unlink(missing_ok=True)
        self.db.execute('DELETE FROM content_priority WHERE source_key=?', (key,))
        self.db.execute('DELETE FROM remote_pdf_files WHERE source_key=?', (key,))
        self.db.execute('DELETE FROM source_links WHERE child_key=?', (key,))
        self.db.execute("DELETE FROM content_jobs WHERE source_key=?", (key,))
        self.db.execute("DELETE FROM video_files WHERE source_key=?", (key,))
        self.db.execute('DELETE FROM video_previews WHERE source_key=?', (key,))
        self.db.execute("DELETE FROM document_files WHERE source_key=?", (key,))
        self.db.execute("DELETE FROM chunks WHERE source_key=?", (key,))
        self.db.execute("DELETE FROM sources WHERE source_key=?", (key,))

    def has_pdf(self, key):
        with self.lock:
            row = self.db.execute("SELECT digest FROM document_files WHERE source_key=?", (key,)).fetchone()
            return bool(row and (self.path.parent / "documents" / (row[0] + ".enc")).is_file())

    def put_pdf(self, key, filename, body):
        if not body.startswith(b"%PDF-") or len(body) > 32 * 1024 * 1024:
            raise ValueError("PDF inválido ou muito grande")
        identifier = hashlib.sha256(key.encode()).hexdigest()
        digest = hashlib.sha256(body).hexdigest()
        target = self.path.parent / "documents" / (digest + ".enc")
        with self.lock, self.db:
            if not self.db.execute("SELECT 1 FROM sources WHERE source_key=?", (key,)).fetchone():
                return
            if not target.exists():
                private_write(target, encrypt(self.key, body))
            self.db.execute('DELETE FROM remote_pdf_files WHERE source_key=?', (key,))
            self.db.execute("INSERT OR REPLACE INTO document_files VALUES (?,?,?,?,?)",
                            (identifier, key, filename[:240], digest, "application/pdf"))

    def documents_for(self, keys):
        self._reload()
        output, seen = [], set()
        with self.lock:
            for key in keys:
                prefix = key + ":attachment:"
                rows = self.db.execute("""SELECT f.id,s.title,f.filename FROM document_files f
                    JOIN sources s ON s.source_key=f.source_key
                    WHERE f.source_key=? OR substr(f.source_key,1,?)=?
                    UNION SELECT f.id,s.title,f.filename FROM remote_pdf_files f
                    JOIN sources s ON s.source_key=f.source_key
                    WHERE f.source_key=? OR substr(f.source_key,1,?)=? ORDER BY title""",
                    (key, len(prefix), prefix, key, len(prefix), prefix)).fetchall()
                for identifier, title, filename in rows:
                    if identifier not in seen:
                        seen.add(identifier)
                        output.append({"id": identifier, "title": title, "filename": filename, "kind": "pdf"})
            for key in keys:
                prefix = key + ":attachment:"
                rows = self.db.execute("""SELECT f.id,s.title,f.filename FROM video_files f
                    JOIN sources s ON s.source_key=f.source_key
                    WHERE f.source_key=? OR substr(f.source_key,1,?)=? ORDER BY s.title""",
                    (key, len(prefix), prefix)).fetchall()
                for identifier, title, filename in rows:
                    if identifier not in seen:
                        seen.add(identifier)
                        output.append({"id": identifier, "title": title, "filename": filename, "kind": "video"})
        return output

    def get_pdf(self, identifier):
        if not re.fullmatch(r"[a-f0-9]{64}", identifier):
            return None
        self._reload()
        with self.lock:
            row = self.db.execute("""SELECT f.filename,f.digest FROM document_files f
                JOIN sources s ON s.source_key=f.source_key WHERE f.id=?""", (identifier,)).fetchone()
        if not row or not re.fullmatch(r"[a-f0-9]{64}", row[1]):
            return None
        # Range requests often read the same file several times. Decrypt once,
        # retain at most 64 MiB for two minutes, and validate source access above
        # on every request (including cache hits).
        with self.lock:
            now = time.monotonic()
            for digest, (expires, _) in list(self.pdf_cache.items()):
                if expires <= now:
                    del self.pdf_cache[digest]
            cached = self.pdf_cache.get(row[1])
            if cached:
                self.pdf_cache.move_to_end(row[1])
                return row[0], cached[1]
            try:
                body = decrypt(self.key, (self.path.parent / "documents" / (row[1] + ".enc")).read_bytes())
            except FileNotFoundError:
                return None
            if hashlib.sha256(body).hexdigest() != row[1]:
                raise ValueError("PDF inconsistente")
            self.pdf_cache[row[1]] = (now + 120, body)
            while sum(len(item[1]) for item in self.pdf_cache.values()) > 64 * 1024 * 1024:
                self.pdf_cache.popitem(last=False)
            return row[0], body

    def put_video(self, key, filename, download_url, mime, byte_size):
        from knowledge_video import api_download_url
        api_download_url(download_url)  # Reject non-Basecamp destinations before persistence.
        identifier = hashlib.sha256(("video:" + key).encode()).hexdigest()
        with self.lock, self.db:
            if self.db.execute("SELECT 1 FROM sources WHERE source_key=?", (key,)).fetchone():
                self.db.execute("INSERT OR REPLACE INTO video_files VALUES (?,?,?,?,?,?)",
                    (identifier, key, filename[:240], download_url, mime, max(0, int(byte_size or 0))))

    def put_video_preview(self, key, url):
        from knowledge_preview import preview_origin
        preview_origin(url)
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO video_previews VALUES (?,?)', (key,url))

    def get_video_preview(self, identifier):
        if not isinstance(identifier,str) or not re.fullmatch(r'[a-f0-9]{64}',identifier):
            return None
        self._reload()
        with self.lock:
            row = self.db.execute('SELECT p.url FROM video_previews p JOIN video_files f ON f.source_key=p.source_key JOIN sources s ON s.source_key=f.source_key WHERE f.id=?', (identifier,)).fetchone()
        return row[0] if row else None

    def put_remote_pdf(self, key, filename, download_url, byte_size):
        from knowledge_video import api_download_url
        api_download_url(download_url)
        identifier = hashlib.sha256(key.encode()).hexdigest()
        with self.lock, self.db:
            if self.db.execute('SELECT 1 FROM sources WHERE source_key=?',(key,)).fetchone():
                self.db.execute('DELETE FROM document_files WHERE source_key=?', (key,))
                self.db.execute('INSERT OR REPLACE INTO remote_pdf_files VALUES (?,?,?,?,?)',
                    (identifier,key,filename[:240],download_url,max(0,int(byte_size or 0))))

    def get_remote_pdf(self, identifier):
        if not isinstance(identifier,str) or not re.fullmatch(r'[a-f0-9]{64}',identifier):
            return None
        self._reload()
        with self.lock:
            row = self.db.execute('SELECT f.download_url,f.byte_size FROM remote_pdf_files f JOIN sources s ON s.source_key=f.source_key WHERE f.id=?',(identifier,)).fetchone()
        return {'download_url':row[0],'byte_size':row[1],'mime':'application/pdf'} if row else None

    def get_video(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{64}", identifier):
            return None
        self._reload()
        with self.lock:
            row = self.db.execute("""SELECT f.download_url,f.mime,f.byte_size FROM video_files f
                JOIN sources s ON s.source_key=f.source_key WHERE f.id=?""", (identifier,)).fetchone()
        return dict(zip(("download_url", "mime", "byte_size"), row)) if row else None

    def document_context(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{64}", identifier):
            return None
        self._reload()
        with self.lock:
            row = self.db.execute("""SELECT s.source_key,s.title FROM
                (SELECT id,source_key FROM document_files UNION ALL SELECT id,source_key FROM video_files
                 UNION ALL SELECT id,source_key FROM remote_pdf_files) f
                JOIN sources s ON s.source_key=f.source_key WHERE f.id=?""", (identifier,)).fetchone()
        return {"source_id": row[0], "title": row[1]} if row else None

    def unchanged(self, key, updated_at):
        if not updated_at:
            return False
        with self.lock:
            row = self.db.execute("SELECT updated_at FROM sources WHERE source_key=?", (key,)).fetchone()
            return bool(row and row[0] == updated_at)

    def upsert(self, source):
        key = source["key"]
        body = source["body"].strip()
        digest = hashlib.sha256((source["title"] + "\0" + body).encode()).hexdigest()
        with self.lock, self.db:
            if source.get('parent_key'):
                self.db.execute('INSERT OR REPLACE INTO source_links VALUES (?,?)', (key, source['parent_key']))
            prior = self.db.execute("SELECT digest FROM sources WHERE source_key=?", (key,)).fetchone()
            if prior and prior[0] == digest:
                self.db.execute("UPDATE sources SET updated_at=?,url=?,project_name=?,kind=? WHERE source_key=?",
                                (source["updated_at"], source["url"], source["project_name"], source["kind"], key))
                return False
            # Updating extracted text must preserve its PDF/player identity and
            # pending extraction job. Actual removal/revocation uses _delete.
            self.db.execute("DELETE FROM chunks WHERE source_key=?", (key,))
            self.db.execute("DELETE FROM sources WHERE source_key=?", (key,))
            if not body:
                self._delete(key)
                return False
            self.db.execute("INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?)", (
                key, str(source["account_id"]), str(source["project_id"]), source["project_name"],
                source["title"], source["url"], source["kind"], source["updated_at"], digest,
            ))
            self.db.executemany("INSERT INTO chunks(source_key,ordinal,title,body) VALUES (?,?,?,?)", [
                (key, number, source["title"], chunk) for number, chunk in enumerate(chunk_text(body))
            ])
            return True

    def enqueue_content(self, key, revision, payload):
        with self.lock, self.db:
            prior = self.db.execute("SELECT revision FROM content_jobs WHERE source_key=?", (key,)).fetchone()
            if prior and prior[0] == revision:
                return
            self.db.execute("""INSERT OR REPLACE INTO content_jobs
                (source_key,revision,payload,status) VALUES (?,?,?,'pending')""",
                (key, revision, json.dumps(payload, ensure_ascii=False)))

    def content_status(self, key):
        with self.lock:
            row = self.db.execute("SELECT status,detail FROM content_jobs WHERE source_key=?", (key,)).fetchone()
            return {"status": row[0], "detail": row[1]} if row else None

    def video_text_path(self, key):
        return self.path.parent / 'video-text' / (hashlib.sha256(key.encode()).hexdigest() + '.txt.enc')

    def write_video_text(self, key, title, body):
        private_write(self.video_text_path(key), encrypt(self.key, (title + '\n\n' + body).encode('utf-8')))

    def prioritize_content(self, keys):
        """Queue requested sources and their attachments without running extraction in chat."""
        if not keys:
            return
        with self.lock, (self.path.parent / 'sync.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self._reload(force=True)
            changed = False
            with self.db:
                for key in keys[:14]:
                    rows = self.db.execute('''SELECT j.source_key FROM content_jobs j
                        WHERE (j.source_key=? OR j.source_key IN (SELECT child_key FROM source_links WHERE parent_key=?))
                        AND j.status IN ('pending','processing','retry')''', (key,key)).fetchall()
                    for (source_key,) in rows:
                        self.db.execute('INSERT OR REPLACE INTO content_priority VALUES (?,?)', (source_key,time.time()))
                        changed = True
            if changed:
                self.save()

    def discussion_parents(self, keys):
        with self.lock:
            return list(dict.fromkeys(row[0] for key in keys for row in self.db.execute(
                'SELECT l.parent_key FROM source_links l JOIN sources s ON s.source_key=l.parent_key WHERE l.child_key=?', (key,))))

    def extraction_cached(self, digest):
        with self.lock:
            row = self.db.execute("SELECT body FROM extraction_cache WHERE digest=?", (digest,)).fetchone()
            return row[0] if row else None

    def cache_extraction(self, digest, body):
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO extraction_cache VALUES (?,?)", (digest, body))

    def prune_project(self, account_id, project_id, seen):
        with self.lock, self.db:
            keys = [row[0] for row in self.db.execute(
                "SELECT source_key FROM sources WHERE account_id=? AND project_id=?", (str(account_id), str(project_id))
            )]
            for key in keys:
                if key not in seen:
                    self._delete(key)

    def search(self, query, limit=5):
        self._reload()
        terms = search_terms(query)
        if not terms:
            return []
        expression = " OR ".join('"' + term + '"*' if len(term) >= 6 else '"' + term + '"' for term in terms)
        with self.lock:
            rows = self.db.execute("""
                SELECT s.source_key,s.title,s.url,s.project_name,c.body,bm25(chunks_fts,3.0,1.0) score
                FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.rowid
                JOIN sources s ON s.source_key=c.source_key
                WHERE chunks_fts MATCH ? ORDER BY score LIMIT ?
            """, (expression, limit * 3)).fetchall()
        output, seen = [], set()
        for key, title, url, project, body, score in rows:
            if key in seen:
                continue
            seen.add(key)
            output.append({"key": key, "title": title, "url": url, "project": project, "excerpt": body, "score": score})
            if len(output) >= limit:
                break
        return output

    def catalog(self):
        """Every indexed source, including books and short/link-only records."""
        self._reload()
        with self.lock:
            rows = self.db.execute("""
                SELECT s.source_key,s.title,s.project_name,s.kind,s.updated_at,
                       substr(c.body,1,220),
                       (SELECT count(*) FROM chunks x WHERE x.source_key=s.source_key)
                FROM sources s JOIN chunks c ON c.source_key=s.source_key AND c.ordinal=0
                ORDER BY s.project_id,s.title,s.source_key
            """).fetchall()
        return [{**dict(zip(("id", "title", "project", "kind", "updated_at", "preview", "chunks"), row)),
                 "parent_id": row[0].rsplit(":attachment:", 1)[0] if row[3] == "attachment" else None}
                for row in rows]

    def read_sources(self, keys, queries, limit=14, budget=48000):
        """Read short sources fully and query-relevant passages of longer ones.

        Ordinal labels and coverage keep excerpts from masquerading as complete
        documents. Reading a record also opens its indexed inline attachments;
        the model need not guess that a short parent has a substantive PDF child.
        """
        self._reload()
        output = []
        terms = list(dict.fromkeys(term for query in queries for term in search_terms(query)))[:40]
        expression = " OR ".join('"' + term + '"*' for term in terms)
        keys = list(dict.fromkeys(keys))[:limit]
        with self.lock:
            for index, key in enumerate(keys):
                source = self.db.execute(
                    "SELECT title,url,project_name,updated_at,kind FROM sources WHERE source_key=?", (key,)
                ).fetchone()
                if not source:
                    continue
                prefix = key + ":attachment:"
                children = self.db.execute("""SELECT source_key,title FROM sources
                    WHERE (kind='attachment' AND substr(source_key,1,?)=?)
                    OR source_key IN (SELECT child_key FROM source_links WHERE parent_key=?)
                    ORDER BY CASE WHEN kind='attachment' THEN 0 ELSE 1 END,updated_at,title""",
                    (len(prefix), prefix, key)).fetchall()
                rows, priority, ranked, locations, totals = [], [], [], {}, {}
                for doc_key, title in [(key, source[0]), *children]:
                    chunks = self.db.execute("SELECT ordinal,body FROM chunks WHERE source_key=? ORDER BY ordinal", (doc_key,)).fetchall()
                    totals[doc_key] = (title, len(chunks))
                    for ordinal, body in chunks:
                        locations[(doc_key, ordinal)] = len(rows)
                        rows.append((doc_key, ordinal, f"[arquivo: {title[:220]}; trecho {ordinal + 1}/{len(chunks)}] {body}"))
                    hits = self.db.execute("""
                        SELECT c.ordinal,bm25(chunks_fts) score FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.rowid
                        WHERE chunks_fts MATCH ? AND c.source_key=? ORDER BY score LIMIT 8
                    """, (expression, doc_key)).fetchall() if expression else []
                    if chunks:
                        priority.append(locations[(doc_key, hits[0][0] if hits else 0)])
                    ranked.extend((score, locations[(doc_key, ordinal)]) for ordinal, score in hits)
                allowance = min(budget, 8000, max(1500, budget // max(1, len(keys) - index)))
                if sum(len(row[2]) + 1 for row in rows) <= allowance:
                    chosen = rows
                else:
                    priority += [index for _, index in sorted(ranked)]
                    priority += [locations[(rows[n][0], rows[n][1] + delta)] for n in list(priority)
                                 for delta in (-1, 1) if (rows[n][0], rows[n][1] + delta) in locations]
                    selected, size = set(), 0
                    for position in priority:
                        if position not in selected:
                            length = len(rows[position][2]) + 1
                            if size + length <= allowance:
                                selected.add(position)
                                size += length
                    chosen = [rows[n] for n in sorted(selected)]
                if not chosen:
                    continue
                excerpt = "\n".join(body for _, _, body in chosen)
                budget -= len(excerpt)
                output.append({"key": key, "title": source[0], "url": source[1], "project": source[2],
                               "updated_at": source[3], "kind": source[4], "excerpt": excerpt,
                               "coverage": "complete" if len(chosen) == len(rows) else "partial",
                               "files": [{"title": title, "passages_read": sum(row[0] == doc_key for row in chosen),
                                          "total_passages": count, "extraction": self.content_status(doc_key)}
                                         for doc_key, (title, count) in totals.items()]})
                if budget < 1400:
                    break
        return output

    def count(self):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
