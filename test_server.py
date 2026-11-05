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
        self.original_role = server.APP_ROLE
        server.APP_ROLE = "all"
        server.DB = os.path.join(self.tmp.name, "test.db")
        server.init_db()
        server.ANALYTICS_CACHE.clear()
        server.app.config.update(TESTING=True)
        self.client = server.app.test_client()

    def tearDown(self):
        server.DB = self.original_db
        server.APP_ROLE = self.original_role
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
        self.assertEqual(response.json["version"], server.APP_VERSION)
        self.assertEqual(response.json["build"], server.APP_BUILD)
        self.assertEqual(response.headers["X-App-Version"], server.APP_VERSION)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_user_and_admin_login_have_separate_routes(self):
        login = self.client.get("/login", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.headers.get("Content-Encoding"), "gzip")
        self.assertIn("no-store", login.headers.get("Cache-Control", ""))
        self.assertNotIn("ETag", login.headers)
        self.assertEqual(self.client.get("/register").status_code, 200)
        legacy = self.client.get("/admin")
        self.assertEqual(legacy.status_code, 302)
        self.assertTrue(legacy.headers["Location"].endswith("/admin/login"))
        self.assertEqual(self.client.get("/admin/login").status_code, 200)
        self.assertEqual(self.client.get("/admin/dashboard").status_code, 200)

    def test_container_roles_are_http_isolated(self):
        server.APP_ROLE = "user"
        self.assertEqual(self.client.get("/login").status_code, 200)
        self.assertEqual(self.client.get("/app/home").status_code, 200)
        self.assertEqual(self.client.get("/kids").status_code, 200)
        self.assertEqual(self.client.get("/kids/kindergarten").status_code, 200)
        self.assertEqual(self.client.get("/kids/primary").status_code, 200)
        self.assertEqual(self.client.get("/admin/login").status_code, 404)
        self.assertEqual(self.client.post("/api/admin/login", json={}).status_code, 404)

        server.APP_ROLE = "admin"
        root = self.client.get("/")
        self.assertEqual(root.status_code, 302)
        self.assertTrue(root.headers["Location"].endswith("/admin/login"))
        self.assertEqual(self.client.get("/admin/login").status_code, 200)
        self.assertEqual(self.client.get("/login").status_code, 404)
        self.assertEqual(self.client.get("/app/home").status_code, 404)
        self.assertEqual(self.client.get("/kids").status_code, 404)
        self.assertEqual(self.client.get("/api/children").status_code, 404)
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json["role"], "admin")

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

    def test_admin_analytics_and_user_details(self):
        registered = self.register()
        user_token = registered.json["token"]
        today = server.local_today().isoformat()
        progress = {
            "studyDays": {today: 3},
            "mastered": {"hello": True, "world": True},
        }
        saved = self.client.put(
            "/api/data",
            json={"data": json.dumps(progress)},
            headers={"Authorization": "Bearer " + user_token},
        )
        self.assertEqual(saved.status_code, 200)

        admin_token = server.make_admin_token()
        headers = {"Authorization": "Bearer " + admin_token}
        analytics = self.client.get("/api/admin/analytics?days=30", headers=headers)
        self.assertEqual(analytics.status_code, 200)
        self.assertEqual(analytics.json["metrics"]["total_users"], 1)
        self.assertEqual(analytics.json["metrics"]["dau"], 1)
        self.assertEqual(analytics.json["metrics"]["learning_dau"], 1)
        self.assertEqual(analytics.json["metrics"]["total_mastered_words"], 2)
        self.assertEqual(analytics.json["sources"]["web"], 1)
        self.assertEqual(len(analytics.json["trend"]), 30)

        users = self.client.get("/api/admin/users", headers=headers)
        self.assertEqual(users.status_code, 200)
        self.assertEqual(users.json["pagination"]["total"], 1)
        self.assertEqual(users.json["users"][0]["source"], "web")
        self.assertTrue(users.json["users"][0]["active_today"])
        self.assertEqual(users.json["users"][0]["last_active"], today)

        conn = server.db()
        activity_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(user_activity)")
        }
        conn.close()
        self.assertNotIn("ip", activity_columns)
        self.assertNotIn("user_agent", activity_columns)

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

    def test_unified_login_routes_by_age_and_creates_child_profile(self):
        registered = self.register(
            learning_stage="kindergarten", age_band="4-5", nickname="小星星"
        )
        self.assertEqual(registered.status_code, 200)
        self.assertEqual(registered.json["landing"], "/kids/kindergarten")
        self.assertEqual(registered.json["user"]["learning_stage"], "kindergarten")
        self.assertTrue(registered.json["child_id"])
        first_child_id = registered.json["child_id"]

        headers = {"Authorization": "Bearer " + registered.json["token"]}
        me = self.client.get("/api/me", headers=headers)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json["landing"], "/kids/kindergarten")
        self.assertEqual(me.json["child_id"], first_child_id)

        login = self.client.post(
            "/api/login",
            json={
                "identifier": "learner@example.com",
                "password": "safe-pass-123",
                "learning_stage": "primary",
                "age_band": "8-10",
            },
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json["landing"], "/kids/primary")
        self.assertEqual(login.json["user"]["age_band"], "8-10")
        self.assertNotEqual(login.json["child_id"], first_child_id)

        conn = server.db()
        rows = conn.execute(
            "SELECT track,age_band FROM child_profiles ORDER BY id"
        ).fetchall()
        conn.close()
        self.assertEqual(
            [(row["track"], row["age_band"]) for row in rows],
            [("kindergarten", "4-5"), ("primary", "8-10")],
        )

    def test_unified_login_rejects_mismatched_age_stage(self):
        response = self.register(learning_stage="primary", age_band="4-5")
        self.assertEqual(response.status_code, 400)
        self.assertIn("匹配", response.json["error"])

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

    def test_child_profiles_progress_events_and_admin_metrics(self):
        token = self.register().json["token"]
        headers = {"Authorization": "Bearer " + token}
        created = self.client.post(
            "/api/children",
            json={
                "nickname": "小星星",
                "avatar": "fox",
                "age_band": "4-5",
                "grade_band": "k2",
                "track": "kindergarten",
                "daily_limit": 15,
            },
            headers=headers,
        )
        self.assertEqual(created.status_code, 201)
        child_id = created.json["child"]["id"]

        listed = self.client.get("/api/children", headers=headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json["children"][0]["nickname"], "小星星")

        progress = {
            "kindergarten": {
                "completed": ["k-hello"],
                "stars": 3,
                "stickers": ["👋"],
            },
            "activityDays": {server.local_today().isoformat(): 1},
        }
        saved = self.client.put(
            f"/api/children/{child_id}/progress",
            json={"progress": progress},
            headers=headers,
        )
        self.assertEqual(saved.status_code, 200)
        loaded = self.client.get(
            f"/api/children/{child_id}/progress", headers=headers
        )
        self.assertEqual(loaded.json["progress"]["kindergarten"]["stars"], 3)

        event = self.client.post(
            f"/api/children/{child_id}/events",
            json={
                "event_type": "lesson_complete",
                "module": "k-hello",
                "score": 100,
                "duration_seconds": 75,
                "metadata": {"word": "hello"},
            },
            headers=headers,
        )
        self.assertEqual(event.status_code, 201)

        admin_headers = {"Authorization": "Bearer " + server.make_admin_token()}
        analytics = self.client.get(
            "/api/admin/analytics", headers=admin_headers
        )
        self.assertEqual(analytics.status_code, 200)
        self.assertEqual(analytics.json["children"]["total_profiles"], 1)
        self.assertEqual(analytics.json["children"]["tracks"]["kindergarten"], 1)
        self.assertEqual(analytics.json["children"]["active_today"], 1)
        self.assertEqual(analytics.json["children"]["completed_activities"], 1)
        self.assertEqual(analytics.json["children"]["average_score"], 100)

    def test_child_profile_rejects_wrong_age_track(self):
        token = self.register().json["token"]
        response = self.client.post(
            "/api/children",
            json={
                "nickname": "小朋友",
                "avatar": "bear",
                "age_band": "10-12",
                "grade_band": "g5-6",
                "track": "kindergarten",
                "daily_limit": 15,
            },
            headers={"Authorization": "Bearer " + token},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
