"""Authenticated Basecamp video streaming. No media files or signed URLs are stored."""
import fcntl
import json
import os
import re
import threading
import time
from contextlib import contextmanager
from urllib.parse import urlsplit, urlunsplit, urljoin

import httpx
from knowledge_store import decrypt

VIDEO_SLOTS = threading.BoundedSemaphore(8)
REDIRECTS = {301, 302, 303, 307, 308}


def api_download_url(value):
    url = urlsplit(value)
    if (url.scheme != "https" or url.hostname not in {"3.basecampapi.com", "storage.3.basecamp.com"}
            or url.port not in (None, 443) or url.username or url.password or not url.path.startswith("/")):
        raise ValueError("Origem de vídeo inválida")
    # Same origin rewrite as the official SDK: only the API receives the token.
    return urlunsplit(("https", "3.basecampapi.com", url.path, url.query, ""))


def signed_destination(value):
    url = urlsplit(value)
    host = url.hostname or ""
    if (url.scheme != "https" or url.port not in (None, 443) or url.username or url.password
            or not any(host == domain or host.endswith("." + domain)
                       for domain in ("basecamp.com", "basecampapi.com", "amazonaws.com", "cloudfront.net"))):
        raise ValueError("Destino de vídeo inválido")
    return value


def range_header(value):
    if not value:
        return None
    if len(value) > 80 or not re.fullmatch(r"bytes=(?:\d+-\d*|-\d+)", value):
        raise ValueError("Intervalo de vídeo inválido")
    first, last = value[6:].split("-")
    if (first and last and int(first) > int(last)) or (not first and int(last) == 0):
        raise ValueError("Intervalo de vídeo inválido")
    return value


def access_token(store):
    path = store.path.parent / "basecamp-token.enc"
    data = json.loads(decrypt(store.key, path.read_bytes()))
    if not data.get("expires_at") or data["expires_at"] > time.time() + 60:
        return data["access_token"]
    # Serialize token rotation with the existing daily importer. Never expose
    # the token to the player, URL, response headers or logs.
    with (store.path.parent / "sync.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        from basecamp_import import token_for
        owner = path.stat()
        try:
            return token_for(path, store.key)
        finally:
            if os.geteuid() == 0:
                os.chown(path, owner.st_uid, owner.st_gid)


@contextmanager
def video_response(store, metadata, requested_range=None):
    headers = {"User-Agent": "Alt-IA private Basecamp player", "Accept-Encoding": "identity"}
    selected = range_header(requested_range)
    if selected:
        headers["Range"] = selected
    origin = api_download_url(metadata["download_url"])
    response = None
    with httpx.Client(timeout=httpx.Timeout(25, read=30), follow_redirects=False) as client:
        try:
            request = client.build_request("GET", origin,
                headers={**headers, "Authorization": "Bearer " + access_token(store)})
            response = client.send(request, stream=True)
            if response.status_code in REDIRECTS:
                destination = signed_destination(urljoin(origin, response.headers.get("location", "")))
                response.close()
                # Separate client request: absolutely no Authorization on the signed hop.
                response = client.send(client.build_request("GET", destination, headers=headers), stream=True)
            if response.status_code not in {200, 206, 416}:
                raise ValueError("Vídeo temporariamente indisponível no Basecamp")
            if response.status_code != 416:
                mime = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if not (mime.startswith("video/") or mime in {"application/octet-stream", "binary/octet-stream"}):
                    raise ValueError("O Basecamp não retornou um vídeo")
            yield response
        finally:
            if response is not None:
                response.close()
