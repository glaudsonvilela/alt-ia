"""Google Workspace identity plus an emailed code for Alt-IA."""

import hashlib
import hmac
import base64
import json
import os
import secrets
import smtplib
import ssl
import threading
import time
from email.message import EmailMessage
from http.cookies import SimpleCookie

from google.auth.transport import requests as google_requests
from google.auth.transport.requests import AuthorizedSession
from google.auth.exceptions import GoogleAuthError
from google.oauth2.credentials import Credentials
from google.oauth2 import id_token
from requests.exceptions import RequestException


DEFAULT_GOOGLE_CLIENT_ID = "802613256116-h6vv32v9egbdk29gqf558j03mqcmiup9.apps.googleusercontent.com"
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


class AuthError(Exception):
    pass


class AuthService:
    def __init__(self, client_id, domain, smtp_host, smtp_port, smtp_from,
                 smtp_user="", smtp_password_file="", smtp_mode="starttls",
                 verifier=None, sender=None, now=None, mail_provider="smtp",
                 gmail_client_secret_file="", gmail_refresh_token_file=""):
        if not client_id or not smtp_from:
            raise ValueError("Configure Google Client ID e remetente antes de iniciar a Alt-IA.")
        if mail_provider not in ("smtp", "gmail_api"):
            raise ValueError("Método de envio inválido.")
        if smtp_mode not in ("starttls", "ssl"):
            raise ValueError("Modo SMTP inválido.")
        if not domain or "@" in domain or "." not in domain:
            raise ValueError("Domínio corporativo inválido.")
        if mail_provider == "smtp" and not smtp_host:
            raise ValueError("Configure o host SMTP.")
        if mail_provider == "smtp" and smtp_user and not smtp_password_file:
            raise ValueError("Informe um arquivo local com a senha SMTP.")
        if mail_provider == "smtp" and smtp_user:
            try:
                with open(smtp_password_file, encoding="utf-8") as secret_file:
                    if not secret_file.read().strip():
                        raise ValueError("Arquivo da senha SMTP vazio.")
            except OSError:
                raise ValueError("Arquivo da senha SMTP indisponível.") from None
        if mail_provider == "gmail_api":
            if not gmail_client_secret_file or not gmail_refresh_token_file:
                raise ValueError("Configure os arquivos OAuth do Gmail.")
            try:
                with open(gmail_client_secret_file, encoding="utf-8") as file:
                    oauth = json.load(file).get("web", {})
                if oauth.get("client_id") != client_id or not oauth.get("client_secret"):
                    raise ValueError("O cliente OAuth do Gmail não corresponde ao login.")
                with open(gmail_refresh_token_file, encoding="utf-8") as file:
                    if not file.read().strip():
                        raise ValueError("Token de envio do Gmail vazio.")
            except (OSError, json.JSONDecodeError):
                raise ValueError("Arquivos OAuth do Gmail indisponíveis.") from None
        self.client_id = client_id
        self.domain = domain.lower()
        self.smtp_host = smtp_host
        self.smtp_port = int(smtp_port)
        self.smtp_from = smtp_from
        self.smtp_user = smtp_user
        self.smtp_password_file = smtp_password_file
        self.smtp_mode = smtp_mode
        self.mail_provider = mail_provider
        self.gmail_client_secret_file = gmail_client_secret_file
        self.gmail_refresh_token_file = gmail_refresh_token_file
        self.verifier = verifier or self._verify_google
        self.sender = sender or self._send_email
        self.now = now or time.time
        self.lock = threading.Lock()
        self.challenges = {}
        self.sessions = {}
        self.last_email = {}

    @classmethod
    def from_environment(cls):
        if os.environ.get("ALT_IA_AUTH_REQUIRED", "1") == "0":
            return None  # Explicit local-development escape hatch only.
        return cls(
            os.environ.get("ALT_IA_GOOGLE_CLIENT_ID", DEFAULT_GOOGLE_CLIENT_ID),
            os.environ.get("ALT_IA_ALLOWED_EMAIL_DOMAIN", "altside.com"),
            os.environ.get("ALT_IA_SMTP_HOST", "smtp.gmail.com"),
            os.environ.get("ALT_IA_SMTP_PORT", "587"),
            os.environ.get("ALT_IA_SMTP_FROM", "Alt-IA <glaudson@altside.com>"),
            os.environ.get("ALT_IA_SMTP_USER", "glaudson@altside.com"),
            os.environ.get("ALT_IA_SMTP_PASSWORD_FILE", ""),
            os.environ.get("ALT_IA_SMTP_MODE", "starttls"),
            mail_provider=os.environ.get("ALT_IA_MAIL_PROVIDER", "gmail_api"),
            gmail_client_secret_file=os.environ.get("ALT_IA_GMAIL_CLIENT_SECRET_FILE", ""),
            gmail_refresh_token_file=os.environ.get("ALT_IA_GMAIL_REFRESH_TOKEN_FILE", ""),
        )

    def _verify_google(self, credential):
        return id_token.verify_oauth2_token(
            credential, google_requests.Request(), self.client_id
        )

    def _send_email(self, email, code):
        message = EmailMessage()
        message["From"] = self.smtp_from
        message["To"] = email
        message["Subject"] = "Seu código de acesso à Alt-IA"
        message.set_content(
            f"Seu código de acesso à Alt-IA é {code}.\n"
            "Ele expira em 10 minutos. Se você não pediu acesso, ignore esta mensagem.\n"
        )
        if self.mail_provider == "gmail_api":
            with open(self.gmail_client_secret_file, encoding="utf-8") as file:
                oauth = json.load(file)["web"]
            with open(self.gmail_refresh_token_file, encoding="utf-8") as file:
                refresh_token = file.read().strip()
            credentials = Credentials(
                token=None, refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.client_id, client_secret=oauth["client_secret"],
                scopes=[GMAIL_SEND_SCOPE],
            )
            try:
                with AuthorizedSession(credentials) as session:
                    response = session.post(
                        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                        json={"raw": base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")},
                        timeout=15,
                    )
                    response.raise_for_status()
            except (GoogleAuthError, RequestException) as error:
                raise OSError("Envio via Gmail indisponível.") from error
            return
        context = ssl.create_default_context()
        if self.smtp_mode == "ssl":
            client = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=12, context=context)
        else:
            client = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=12)
        with client:
            if self.smtp_mode == "starttls":
                client.starttls(context=context)
            if self.smtp_user:
                with open(self.smtp_password_file, encoding="utf-8") as secret_file:
                    client.login(self.smtp_user, secret_file.read().strip())
            client.send_message(message)

    @staticmethod
    def _digest(value):
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _prune(self, current):
        self.challenges = {k: v for k, v in self.challenges.items() if v[2] > current}
        self.sessions = {k: v for k, v in self.sessions.items() if v[1] > current}
        self.last_email = {k: v for k, v in self.last_email.items() if v > current - 60}

    def begin(self, credential):
        if not isinstance(credential, str) or not 0 < len(credential) < 8192:
            raise AuthError("Identidade Google inválida.")
        try:
            claims = self.verifier(credential)
        except (ValueError, TypeError, OSError, GoogleAuthError):
            raise AuthError("Não foi possível verificar a conta Google.") from None
        email = claims.get("email")
        if (claims.get("email_verified") is not True or
                claims.get("hd") != self.domain or
                not isinstance(email, str) or
                not email.lower().endswith("@" + self.domain) or
                len(email) > 254):
            raise AuthError("Use sua conta Google corporativa @" + self.domain + ".")
        email = email.lower()
        current = self.now()
        with self.lock:
            self._prune(current)
            if current - self.last_email.get(email, 0) < 60:
                raise AuthError("Aguarde um pouco antes de pedir outro código.")
            self.last_email[email] = current
        challenge = secrets.token_urlsafe(32)
        code = f"{secrets.randbelow(1000000):06d}"
        code_hash = self._digest(challenge + ":" + code)
        try:
            self.sender(email, code)
        except (OSError, smtplib.SMTPException):
            raise AuthError("Não foi possível enviar o código. Tente novamente depois.") from None
        with self.lock:
            self.challenges = {
                key: record for key, record in self.challenges.items() if record[0] != email
            }
            self.challenges[self._digest(challenge)] = [email, code_hash, current + 600, 0]
        return challenge, email

    def complete(self, challenge, code):
        if not isinstance(challenge, str) or not isinstance(code, str) or not code.isascii() or not code.isdigit() or len(code) != 6:
            raise AuthError("Código inválido ou expirado.")
        key = self._digest(challenge)
        current = self.now()
        with self.lock:
            record = self.challenges.get(key)
            if not record or record[2] <= current:
                raise AuthError("Código inválido ou expirado.")
            record[3] += 1
            if record[3] >= 5:
                self.challenges.pop(key, None)
            if not hmac.compare_digest(record[1], self._digest(challenge + ":" + code)):
                raise AuthError("Código inválido ou expirado.")
            self.challenges.pop(key, None)
            session = secrets.token_urlsafe(32)
            self.sessions[self._digest(session)] = (record[0], current + 12 * 3600)
        return session, record[0]

    def email_for(self, session):
        if not isinstance(session, str):
            return None
        with self.lock:
            record = self.sessions.get(self._digest(session))
            if record and record[1] > self.now():
                return record[0]
        return None

    def logout(self, session):
        if isinstance(session, str):
            with self.lock:
                self.sessions.pop(self._digest(session), None)


def cookie_value(header, name):
    if not header or len(header) > 4096:
        return None
    try:
        cookie = SimpleCookie()
        cookie.load(header)
        return cookie[name].value if name in cookie else None
    except Exception:
        return None
