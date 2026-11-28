import base64
from email import policy
from email.parser import BytesParser
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from access_auth import AuthError, AuthService, cookie_value


class AuthServiceTests(unittest.TestCase):
    def setUp(self):
        self.current = 1000
        self.mail = []
        self.claims = {
            "email": "Ana@altside.com", "email_verified": True, "hd": "altside.com",
            "name": "Ana Silva", "picture": "https://lh3.googleusercontent.com/a/profile-picture"
        }
        self.auth = AuthService(
            "test.apps.googleusercontent.com", "altside.com", "smtp.example.com",
            587, "noreply@altside.com", verifier=lambda _: self.claims,
            sender=lambda email, code: self.mail.append((email, code)),
            now=lambda: self.current,
        )

    def test_google_then_code_then_session_and_logout(self):
        challenge, email = self.auth.begin("google-token")
        self.assertEqual(email, "ana@altside.com")
        self.assertEqual(self.mail[0][0], email)
        self.assertIsNone(self.auth.email_for(challenge))
        session, signed_in = self.auth.complete(challenge, self.mail[0][1])
        self.assertEqual(signed_in, email)
        self.assertEqual(self.auth.email_for(session), email)
        self.assertEqual(self.auth.profile_for(session), {
            "email": email, "name": "Ana Silva",
            "picture": "https://lh3.googleusercontent.com/a/profile-picture",
        })
        with self.assertRaises(AuthError):
            self.auth.complete(challenge, self.mail[0][1])
        self.auth.logout(session)
        self.assertIsNone(self.auth.email_for(session))

    def test_profile_falls_back_and_rejects_external_picture(self):
        self.claims["name"] = " "
        self.claims["picture"] = "https://example.com/avatar.png"
        challenge, _ = self.auth.begin("google-token")
        session, _ = self.auth.complete(challenge, self.mail[0][1])
        self.assertEqual(self.auth.profile_for(session), {
            "email": "ana@altside.com", "name": "ana", "picture": "",
        })

    def test_session_survives_server_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(directory, "sessions.sqlite3")
            def make_service():
                return AuthService(
                    "test.apps.googleusercontent.com", "altside.com", "smtp.example.com",
                    587, "noreply@altside.com", verifier=lambda _: self.claims,
                    sender=lambda email, code: self.mail.append((email, code)),
                    now=lambda: self.current, session_db_path=database_path,
                )
            first = make_service()
            challenge, _ = first.begin("google-token")
            session, _ = first.complete(challenge, self.mail[-1][1])
            second = make_service()
            self.assertEqual(second.profile_for(session)["name"], "Ana Silva")
            self.assertEqual(os.stat(database_path).st_mode & 0o777, 0o600)
            second.logout(session)
            self.assertIsNone(first.profile_for(session))

    def test_rejects_non_workspace_and_unverified_accounts(self):
        for claims in (
            {"email": "ana@altside.com", "email_verified": True},
            {"email": "ana@altside.com", "email_verified": False, "hd": "altside.com"},
            {"email": "ana@gmail.com", "email_verified": True, "hd": "gmail.com"},
        ):
            self.claims = claims
            with self.assertRaises(AuthError):
                self.auth.begin("google-token")
        self.assertEqual(self.mail, [])

    def test_additional_domain_requires_verified_email_and_code(self):
        self.auth.additional_domains = frozenset({"criptomaniacos.io"})
        self.claims = {
            "email": "Guilherme@criptomaniacos.io", "email_verified": True,
            "name": "Guilherme Assis",
        }
        challenge, email = self.auth.begin("google-token")
        self.assertEqual(email, "guilherme@criptomaniacos.io")
        self.assertEqual(self.mail[-1][0], email)
        session, _ = self.auth.complete(challenge, self.mail[-1][1])
        self.assertEqual(self.auth.profile_for(session)["email"], email)

    def test_additional_domain_does_not_allow_other_addresses(self):
        self.auth.additional_domains = frozenset({"criptomaniacos.io"})
        for claims in (
            {"email": "ana@criptomaniacos.io.evil", "email_verified": True},
            {"email": "ana@outro.io", "email_verified": True},
            {"email": "ana@criptomaniacos.io", "email_verified": False},
            {"email": "ana@altside.com", "email_verified": True},
        ):
            self.claims = claims
            with self.assertRaises(AuthError):
                self.auth.begin("google-token")
        self.assertEqual(self.mail, [])

    def test_code_expires_and_five_attempts_lock(self):
        challenge, _ = self.auth.begin("google-token")
        for _ in range(5):
            with self.assertRaises(AuthError):
                self.auth.complete(challenge, "999999" if self.mail[0][1] != "999999" else "888888")
        with self.assertRaises(AuthError):
            self.auth.complete(challenge, self.mail[0][1])
        self.current += 61
        challenge, _ = self.auth.begin("google-token")
        self.current += 601
        with self.assertRaises(AuthError):
            self.auth.complete(challenge, self.mail[-1][1])

    def test_throttle_and_cookie_parse(self):
        self.auth.begin("google-token")
        with self.assertRaises(AuthError):
            self.auth.begin("google-token")
        self.assertEqual(cookie_value("alt_ia_session=abc; other=def", "alt_ia_session"), "abc")
        self.assertIsNone(cookie_value("", "alt_ia_session"))
        self.assertEqual(cookie_value("broken={json}; alt_ia_session=abc; other=def", "alt_ia_session"), "abc")
        self.assertEqual(cookie_value("other=" + "x" * 5000 + "; alt_ia_session=abc", "alt_ia_session"), "abc")
        self.assertIsNone(cookie_value("alt_ia_session=bad value", "alt_ia_session"))

    def test_gmail_sender_uses_only_send_endpoint_and_private_files(self):
        with tempfile.TemporaryDirectory() as directory:
            oauth_path = os.path.join(directory, "oauth.json")
            token_path = os.path.join(directory, "refresh-token")
            with open(oauth_path, "w", encoding="utf-8") as file:
                json.dump({"web": {"client_id": "test.apps.googleusercontent.com",
                                   "client_secret": "private-secret"}}, file)
            with open(token_path, "w", encoding="utf-8") as file:
                file.write("private-refresh-token\n")
            auth = AuthService(
                "test.apps.googleusercontent.com", "altside.com", "", 587,
                "Alt-IA <glaudson@altside.com>", mail_provider="gmail_api",
                gmail_client_secret_file=oauth_path,
                gmail_refresh_token_file=token_path,
            )
            mock_session = MagicMock()
            with patch("access_auth.AuthorizedSession") as session_factory:
                session_factory.return_value.__enter__.return_value = mock_session
                auth._send_email("ana@altside.com", "123456")
            args, kwargs = mock_session.post.call_args
            self.assertEqual(args[0], "https://gmail.googleapis.com/gmail/v1/users/me/messages/send")
            raw = base64.urlsafe_b64decode(kwargs["json"]["raw"])
            message = BytesParser(policy=policy.default).parsebytes(raw)
            self.assertIn("glaudson@altside.com", message["From"])
            self.assertEqual(message["To"], "ana@altside.com")
            self.assertIn("123456", message.get_body(preferencelist=("plain",)).get_content())
            html = message.get_body(preferencelist=("html",)).get_content()
            self.assertIn("Confirme seu e-mail", html)
            self.assertIn("expira em 10 minutos", html)
            self.assertEqual(html.count('color:#25202d'), 6)
            for digit in "123456":
                self.assertIn(f">{digit}</div>", html)
            self.assertIn("cid:alt-ia-mascots", html)
            related = [part for part in message.walk() if part.get_content_type() == "image/png"]
            self.assertEqual(len(related), 2)

    def test_login_client_can_differ_from_gmail_sender_client(self):
        with tempfile.TemporaryDirectory() as directory:
            oauth_path = os.path.join(directory, "oauth.json")
            token_path = os.path.join(directory, "refresh-token")
            with open(oauth_path, "w", encoding="utf-8") as file:
                json.dump({"web": {"client_id": "sender.apps.googleusercontent.com",
                                   "client_secret": "private-secret"}}, file)
            with open(token_path, "w", encoding="utf-8") as file:
                file.write("private-refresh-token\n")
            auth = AuthService(
                "login.apps.googleusercontent.com", "altside.com", "", 587,
                "Alt-IA <glaudson@altside.com>", mail_provider="gmail_api",
                gmail_client_secret_file=oauth_path,
                gmail_refresh_token_file=token_path,
                gmail_client_id="sender.apps.googleusercontent.com",
            )
            self.assertEqual(auth.client_id, "login.apps.googleusercontent.com")
            self.assertEqual(auth.gmail_client_id, "sender.apps.googleusercontent.com")
            with patch("access_auth.AuthorizedSession") as session_factory:
                auth._send_email("ana@altside.com", "123456")
            self.assertEqual(session_factory.call_args.args[0].client_id,
                             "sender.apps.googleusercontent.com")


if __name__ == "__main__":
    unittest.main()
