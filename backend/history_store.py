"""Private, account-scoped conversation history with encrypted records."""

import json
import re
import sqlite3
import threading
import time
from pathlib import Path

from cryptography.fernet import Fernet


CONVERSATION_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


class HistoryStore:
    def __init__(self, database_path, key_file, now=None):
        self.database_path = database_path
        self.cipher = Fernet(Path(key_file).read_bytes().strip())
        self.now = now or time.time
        self.lock = threading.Lock()
        with sqlite3.connect(database_path, timeout=5) as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS conversation_history ("
                "email TEXT NOT NULL, id TEXT NOT NULL, updated_at INTEGER NOT NULL, "
                "deleted INTEGER NOT NULL, payload BLOB, PRIMARY KEY(email, id))"
            )

    def list_for(self, email):
        with self.lock, sqlite3.connect(self.database_path, timeout=5) as database:
            rows = database.execute(
                "SELECT id, updated_at, deleted, payload FROM conversation_history "
                "WHERE email = ? ORDER BY updated_at DESC LIMIT 250", (email,)
            ).fetchall()
        conversations = []
        deleted = []
        for conversation_id, updated_at, is_deleted, payload in rows:
            if is_deleted:
                deleted.append({"id": conversation_id, "updatedAt": updated_at})
            else:
                conversations.append(json.loads(self.cipher.decrypt(payload)))
        return {"conversations": conversations, "deleted": deleted}

    def save_for(self, email, conversations):
        if not isinstance(conversations, list) or len(conversations) > 30:
            raise ValueError("Lote de conversas inválido.")
        clean = []
        for conversation in conversations:
            if not isinstance(conversation, dict):
                raise ValueError("Conversa inválida.")
            identifier = conversation.get("id")
            updated_at = conversation.get("updatedAt")
            messages = conversation.get("messages")
            if (not isinstance(identifier, str) or not CONVERSATION_ID.fullmatch(identifier)
                    or type(updated_at) is not int or updated_at < 0
                    or not isinstance(messages, list) or len(messages) > 100
                    or any(not isinstance(message, dict) or message.get("role") not in ("user", "ai")
                           or not isinstance(message.get("text"), str) for message in messages)):
                raise ValueError("Conversa inválida.")
            encoded = json.dumps(conversation, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(encoded) > 250_000:
                raise ValueError("Conversa muito grande para sincronizar.")
            clean.append((identifier, updated_at, self.cipher.encrypt(encoded)))
        with self.lock, sqlite3.connect(self.database_path, timeout=5) as database:
            for identifier, updated_at, encrypted in clean:
                database.execute(
                    "INSERT INTO conversation_history VALUES (?, ?, ?, 0, ?) "
                    "ON CONFLICT(email, id) DO UPDATE SET updated_at=excluded.updated_at, "
                    "deleted=0, payload=excluded.payload "
                    "WHERE excluded.updated_at > conversation_history.updated_at",
                    (email, identifier, updated_at, encrypted),
                )
        return {"saved": len(clean)}

    def delete_for(self, email, identifier):
        if not isinstance(identifier, str) or not CONVERSATION_ID.fullmatch(identifier):
            raise ValueError("Conversa inválida.")
        with self.lock, sqlite3.connect(self.database_path, timeout=5) as database:
            row = database.execute(
                "SELECT updated_at FROM conversation_history WHERE email=? AND id=?",
                (email, identifier),
            ).fetchone()
            updated_at = max(int(self.now() * 1000), (row[0] + 1) if row else 0)
            database.execute(
                "INSERT INTO conversation_history VALUES (?, ?, ?, 1, NULL) "
                "ON CONFLICT(email, id) DO UPDATE SET updated_at=excluded.updated_at, "
                "deleted=1, payload=NULL",
                (email, identifier, updated_at),
            )
        return {"id": identifier, "updatedAt": updated_at}
