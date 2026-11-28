"""Encrypted, whole-file SQLite knowledge snapshot and source retrieval.

The SQLite database and its FTS index exist only in process memory. The file on
disk is an AES-GCM ciphertext; replacing it is atomic, so API workers can read
the last complete snapshot while an import is running.
"""

import hashlib
import json
import os
import re
import secrets
import sqlite3
import tempfile
import threading
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
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".altia-", dir=target.parent)
    try:
        os.fchmod(fd, 0o600)
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
        self.db.execute("DELETE FROM chunks WHERE source_key=?", (key,))
        self.db.execute("DELETE FROM sources WHERE source_key=?", (key,))

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
            prior = self.db.execute("SELECT digest FROM sources WHERE source_key=?", (key,)).fetchone()
            if prior and prior[0] == digest:
                self.db.execute("UPDATE sources SET updated_at=?,url=?,project_name=?,kind=? WHERE source_key=?",
                                (source["updated_at"], source["url"], source["project_name"], source["kind"], key))
                return False
            self._delete(key)
            if not body:
                return False
            self.db.execute("INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?)", (
                key, str(source["account_id"]), str(source["project_id"]), source["project_name"],
                source["title"], source["url"], source["kind"], source["updated_at"], digest,
            ))
            self.db.executemany("INSERT INTO chunks(source_key,ordinal,title,body) VALUES (?,?,?,?)", [
                (key, number, source["title"], chunk) for number, chunk in enumerate(chunk_text(body))
            ])
            return True

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
                children = self.db.execute(
                    "SELECT source_key,title FROM sources WHERE kind='attachment' AND substr(source_key,1,?)=? ORDER BY title",
                    (len(prefix), prefix)).fetchall()
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
                                          "total_passages": count} for doc_key, (title, count) in totals.items()]})
                if budget < 1400:
                    break
        return output

    def count(self):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
