"""One-time Gmail send authorization for the local Alt-IA server."""

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

import requests
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from access_auth import DEFAULT_GOOGLE_CLIENT_ID, GMAIL_SEND_SCOPE


SENDER = "glaudson@altside.com"
REDIRECT_URI = "http://127.0.0.1:8765/callback"
SCOPES = ("openid", "email", GMAIL_SEND_SCOPE)


def authorize(client_secret_file, output_file):
    if os.path.exists(output_file):
        raise ValueError("O arquivo de token já existe. Revogue o token antigo antes de gerar outro.")
    with open(client_secret_file, encoding="utf-8") as source:
        oauth = json.load(source).get("web", {})
    client_id = oauth.get("client_id")
    client_secret = oauth.get("client_secret")
    if client_id != DEFAULT_GOOGLE_CLIENT_ID or not client_secret:
        raise ValueError("Use o JSON do cliente OAuth web configurado para a Alt-IA.")

    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    nonce = secrets.token_urlsafe(32)
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # The callback URL contains a short-lived OAuth code.

        def do_GET(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            if parsed.path != "/callback" or query.get("state") != [state]:
                self.send_error(400)
                return
            if "error" in query:
                result["error"] = query["error"][0]
            elif len(query.get("code", [])) == 1:
                result["code"] = query["code"][0]
            else:
                self.send_error(400)
                return
            body = b"Autorizacao recebida. Volte ao terminal da Alt-IA."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent select_account",
        "login_hint": SENDER,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    with HTTPServer(("127.0.0.1", 8765), Callback) as server:
        server.timeout = 2
        print("Entre com " + SENDER + " e autorize somente o envio de e-mails.")
        print("Abra este link no navegador da mesma máquina:\n" + url + "\n")
        deadline = time.monotonic() + 900
        while not result and time.monotonic() < deadline:
            server.handle_request()
    if "error" in result:
        raise ValueError("Autorização recusada: " + result["error"])
    if "code" not in result:
        raise TimeoutError("A autorização não foi concluída em quinze minutos.")

    response = requests.post("https://oauth2.googleapis.com/token", data={
        "code": result["code"],
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    }, timeout=20)
    response.raise_for_status()
    tokens = response.json()
    claims = id_token.verify_oauth2_token(
        tokens.get("id_token"), google_requests.Request(), client_id
    )
    if (str(claims.get("email", "")).lower() != SENDER or
            claims.get("email_verified") is not True or
            claims.get("hd") != "altside.com" or
            claims.get("nonce") != nonce):
        raise ValueError("A autorização precisa vir de " + SENDER + ".")
    if GMAIL_SEND_SCOPE not in str(tokens.get("scope", "")).split():
        raise ValueError("A permissão gmail.send não foi concedida.")
    refresh_token = tokens.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise ValueError("O Google não retornou um token renovável.")
    fd = os.open(output_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as destination:
        destination.write(refresh_token + "\n")
    print("Token salvo com permissão 0600 em " + output_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autoriza o envio dos códigos da Alt-IA pelo Gmail.")
    parser.add_argument("--client-secret", required=True, help="JSON baixado do cliente OAuth web")
    parser.add_argument("--output", required=True, help="Arquivo local fora do repositório para o token")
    arguments = parser.parse_args()
    try:
        authorize(arguments.client_secret, arguments.output)
    except (OSError, ValueError, TimeoutError, GoogleAuthError, requests.RequestException) as error:
        print("Falha: " + str(error), file=sys.stderr)
        sys.exit(1)
