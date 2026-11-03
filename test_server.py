import json
import os
import tempfile
import unittest
from unittest import mock

import server


class ServerApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_db = server.DB
        server.DB = os.path.join(self.tmp.name, "test.db")
        server.init_db()
        server.app.config.update(TESTING=True)
        self.client = server.app.test_client()

    def tearDown(self):
        server.DB = self.original_db
        self.tmp.cleanup()

    def register(self, **overrides):
        payload = {
            "email": "Learner@Example.com",
            "password": "safe-pass-123",
            "nickname": "学习者",
        }
        payload.update(overrides)
        with mock.patch.object(server, "SITE_BASE_URL", ""):
            return self.client.post("/api/register", json=payload)

    def test_health_and_security_headers(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "ok")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_cors_only_allows_configured_origin(self):
        with mock.patch.object(server, "CORS_ORIGINS", {"https://study.example.com"}):
            allowed = self.client.get(
                "/api/health", headers={"Origin": "https://study.example.com"}
            )
            denied = self.client.get(
                "/api/health", headers={"Origin": "https://evil.example"}
            )
        self.assertEqual(
            allowed.headers.get("Access-Control-Allow-Origin"),
            "https://study.example.com",
        )
        self.assertNotIn("Access-Control-Allow-Origin", denied.headers)

    def test_admin_is_disabled_without_configured_password(self):
        with mock.patch.object(server, "ADMIN_PASSWORD", ""):
            response = self.client.post("/api/admin/login", json={"password": "admin123"})
        self.assertEqual(response.status_code, 503)

    def test_register_login_and_email_normalization(self):
        response = self.register()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["user"]["email"], "learner@example.com")

        login = self.client.post(
            "/api/login",
            json={"identifier": "LEARNER@EXAMPLE.COM", "password": "safe-pass-123"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.json["token"])

    def test_password_and_progress_validation(self):
        self.assertEqual(self.register(password="short").status_code, 400)
        registered = self.register()
        token = registered.json["token"]
        headers = {"Authorization": "Bearer " + token}

        invalid = self.client.put(
            "/api/data", json={"data": "[]"}, headers=headers
        )
        self.assertEqual(invalid.status_code, 400)

        payload = {"studyDays": {"2026-11-03": 3}}
        saved = self.client.put(
            "/api/data", json={"data": json.dumps(payload)}, headers=headers
        )
        self.assertEqual(saved.status_code, 200)
        loaded = self.client.get("/api/data", headers=headers)
        self.assertEqual(json.loads(loaded.json["data"]), payload)

    def test_bind_rejects_empty_and_short_password(self):
        token = self.register().json["token"]
        headers = {"Authorization": "Bearer " + token}
        empty = self.client.post("/api/bind", json={}, headers=headers)
        short = self.client.post(
            "/api/bind", json={"password": "123456"}, headers=headers
        )
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(short.status_code, 400)

    def test_tts_rejects_invalid_voice_before_synthesis(self):
        response = self.client.get(
            "/api/tts", query_string={"text": "hello", "voice": "../../bad"}
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
