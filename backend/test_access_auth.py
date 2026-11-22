import base64
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
            "email": "Ana@altside.com", "email_verified": True, "hd": "altside.com"
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
        with self.assertRaises(AuthError):
            self.auth.complete(challenge, self.mail[0][1])
        self.auth.logout(session)
        self.assertIsNone(self.auth.email_for(session))

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
            raw = base64.urlsafe_b64decode(kwargs["json"]["raw"]).decode("utf-8")
            self.assertIn("glaudson@altside.com", raw)
            self.assertIn("ana@altside.com", raw)
            self.assertIn("123456", raw)


if __name__ == "__main__":
    unittest.main()
