import hashlib
import os
import tempfile
import unittest
from email import policy
from email.parser import BytesParser
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import bcrypt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db
from app.main import app
from app.models import PasswordReset, User
from app.csrf import CSRF_COOKIE


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        def database():
            yield self.db
        app.dependency_overrides[get_db] = database
        self.client = TestClient(app)
        self.password = "secret123"
        self.user = User(id=10, name="Existing", email="existing@example.test", password=bcrypt.hashpw(self.password.encode(), bcrypt.gensalt()).decode())
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def test_registration_validates_and_creates_session(self):
        invalid = self.client.post("/api/auth/register", data={"name": "", "email": "bad", "password": "short", "password_confirmation": "other"})
        self.assertEqual(invalid.status_code, 422)
        response = self.client.post("/api/auth/register", data={"name": "New User", "email": "new@example.test", "password": "secret123", "password_confirmation": "secret123"}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        created = self.db.query(User).filter_by(email="new@example.test").one()
        self.assertNotEqual(created.password, "secret123")
        self.client.cookies.clear()
        duplicate = self.client.post("/api/auth/register", data={"name": "Again", "email": "new@example.test", "password": "secret123", "password_confirmation": "secret123"})
        self.assertEqual(duplicate.status_code, 422)

    def test_remember_me_cookie_is_revoked_by_logout(self):
        response = self.client.post("/api/auth/login", data={"email": self.user.email, "password": self.password, "remember": "true"}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        cookie = response.cookies.get("typography_remember")
        self.assertTrue(cookie)
        self.client.cookies.clear()
        self.client.cookies.set("typography_remember", cookie)
        session = self.client.get("/api/session")
        self.assertEqual(session.json()["authenticated"], True)
        token = self.client.get("/api/csrf-token").json()["token"]
        logout = self.client.post("/api/auth/logout", headers={"X-CSRF-Token": token}, follow_redirects=False)
        self.assertEqual(logout.status_code, 303)
        self.assertIsNone(self.db.get(User, self.user.id).remember_token)

    def test_password_reset_is_single_use_and_expires(self):
        with tempfile.TemporaryDirectory() as directory, patch("app.main.RESET_MAIL_DIR", Path(directory)), patch("app.main.RESET_MAIL_MODE", "file"):
            requested = self.client.post("/api/password/email", data={"email": self.user.email})
            self.assertEqual(requested.status_code, 200)
            mail = BytesParser(policy=policy.default).parsebytes(next(Path(directory).iterdir()).read_bytes())
            token = mail.get_content().split("/password/reset/", 1)[1].strip()
            response = self.client.post("/api/password/reset", data={"email": self.user.email, "token": token, "password": "newsecret", "password_confirmation": "newsecret"}, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertTrue(bcrypt.checkpw(b"newsecret", self.db.get(User, self.user.id).password.encode()))
            reused = self.client.post("/api/password/reset", data={"email": self.user.email, "token": token, "password": "again123", "password_confirmation": "again123"})
            self.assertEqual(reused.status_code, 422)

            self.client.post("/api/password/email", data={"email": self.user.email})
            reset = self.db.get(PasswordReset, self.user.email)
            reset.created_at = datetime.utcnow() - timedelta(minutes=61)
            self.db.commit()
            expired_mail = BytesParser(policy=policy.default).parsebytes(next(Path(directory).iterdir()).read_bytes())
            expired_token = expired_mail.get_content().split("/password/reset/", 1)[1].strip()
            expired = self.client.post("/api/password/reset", data={"email": self.user.email, "token": expired_token, "password": "expired1", "password_confirmation": "expired1"})
            self.assertEqual(expired.status_code, 422)

    def test_csrf_token_is_cookie_bound_for_browser_mutations(self):
        token_response = self.client.get("/api/csrf-token")
        self.assertEqual(token_response.status_code, 200)
        token = token_response.json()["token"]
        self.assertEqual(token_response.cookies.get("typography_csrf"), token)

        missing = self.client.post("/api/auth/login", data={"email": self.user.email, "password": self.password})
        self.assertEqual(missing.status_code, 419)

        valid = self.client.post(
            "/api/auth/login",
            data={"email": self.user.email, "password": self.password},
            headers={"X-CSRF-Token": token},
            follow_redirects=False,
        )
        self.assertEqual(valid.status_code, 303)

        rejected = self.client.post("/api/auth/logout", headers={"X-CSRF-Token": "wrong-token"}, follow_redirects=False)
        self.assertEqual(rejected.status_code, 419)


if __name__ == "__main__":
    unittest.main()