"""Short-lived, tamper-evident context for follow-up price calculations."""

import base64
import binascii
import hashlib
import hmac
import json
import time
import zlib


MAX_AGE = 7 * 24 * 60 * 60


def issue(basis, secret):
    body = json.dumps({"at": int(time.time()), "basis": basis}, separators=(",", ":"), ensure_ascii=False).encode()
    packed = base64.urlsafe_b64encode(zlib.compress(body, 9)).rstrip(b"=")
    digest = hmac.new(secret, packed, hashlib.sha256).hexdigest().encode()
    return (packed + b"." + digest).decode()


def verify(token, secret):
    if not isinstance(token, str) or len(token) > 12000:
        return None
    try:
        packed, digest = token.encode().rsplit(b".", 1)
        if not hmac.compare_digest(hmac.new(secret, packed, hashlib.sha256).hexdigest().encode(), digest):
            return None
        decompressor = zlib.decompressobj()
        body = decompressor.decompress(base64.urlsafe_b64decode(packed + b"=" * (-len(packed) % 4)), 32001)
        if len(body) > 32000 or not decompressor.eof:
            return None
        data = json.loads(body)
        age = int(time.time()) - data["at"]
        return data["basis"] if 0 <= age <= MAX_AGE and isinstance(data["basis"], dict) else None
    except (ValueError, KeyError, TypeError, zlib.error, binascii.Error):
        return None
