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
                SELECT s.title,s.url,s.project_name,c.body,bm25(chunks_fts,3.0,1.0) score
                FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.rowid
                JOIN sources s ON s.source_key=c.source_key
                WHERE chunks_fts MATCH ? ORDER BY score LIMIT ?
            """, (expression, limit * 3)).fetchall()
        output, seen = [], set()
        for title, url, project, body, score in rows:
            if url in seen:
                continue
            seen.add(url)
            output.append({"title": title, "url": url, "project": project, "excerpt": body, "score": score})
            if len(output) >= limit:
                break
        return output

    def research(self, query, limit=7):
        """Collect distinct, substantive documents for a broad company strategy question."""
        normalized = search_terms(query)
        company = "altside" in unicodedata.normalize("NFKD", query.lower())
        if not (company and normalized == ["estrategia"]):
            return self.search(query, limit=limit)
        sources, seen, themes = [], set(), set()
        for facet, quota in (("filosofia", 1), ("processo research", 1), ("estrategia", 5)):
            added = 0
            for item in self.search(facet, limit=30):
                title = unicodedata.normalize("NFKD", item["title"].lower())
                title = "".join(char for char in title if not unicodedata.combining(char))
                words = WORD.findall(title)
                theme = words[0][:4] if words else title[:4]
                if (item["url"] in seen or title.endswith(".pdf") or "pastas" in title
                        or "calendario" in title or "objetivos e metas" in title
                        or len(item["excerpt"]) < (250 if facet == "estrategia" else 150)
                        or (facet == "estrategia" and theme in themes)):
                    continue
                sources.append(item)
                seen.add(item["url"])
                themes.add(theme)
                added += 1
                if added == quota or len(sources) == limit:
                    break
            if len(sources) == limit:
                break
        return sources or self.search(query, limit=limit)

    def count(self):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
