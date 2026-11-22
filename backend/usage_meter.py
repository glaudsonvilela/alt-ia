"""Count only model tokens reported by the provider for the current account request."""

import threading
import sqlite3


_request = threading.local()
_writer = None


def configure(writer):
    global _writer
    _writer = writer


def for_account(email):
    _request.email = email


def record(response):
    usage = response.get("usage") if isinstance(response, dict) else None
    if not isinstance(usage, dict) or not _writer or not getattr(_request, "email", None):
        return
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    if type(prompt) is int and type(completion) is int:
        try:
            _writer(_request.email, prompt, completion)
        except (OSError, sqlite3.Error):
            pass  # A temporary counter failure must not discard a valid answer.
