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
        self.assertEqual(response.json["kids_runtime"], "inline")
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

    def test_browser_gzip_requests_do_not_break_streamed_static_assets(self):
        for path, marker in (
            ("/assets/vocabulary-data.js", b"EXTRA_VOCAB"),
            ("/kids/runtime-style", b".kids-shell"),
            ("/kids/runtime-app", b"KidsAPI"),
        ):
            response = self.client.get(path, headers={"Accept-Encoding": "gzip, deflate, br"})
            self.assertEqual(response.status_code, 200, path)
            self.assertIn(marker, response.get_data())
            response.close()

    def test_large_vocabulary_and_sentence_corpus(self):
        stats = self.client.get("/api/content/stats")
        self.assertEqual(stats.status_code, 200)
        self.assertEqual(stats.json["vocabulary"], 30000)
        self.assertEqual(stats.json["sentences"], 30000)
        self.assertGreater(stats.json["exam_counts"]["kaoyan"], 1000)
        self.assertGreater(stats.json["exam_counts"]["gre"], 3000)

        words = self.client.get("/api/content/vocabulary?q=analysis&limit=20")
        self.assertEqual(words.status_code, 200)
        self.assertGreater(words.json["pagination"]["total"], 0)
        self.assertTrue(words.json["items"][0]["word"])
        self.assertTrue(words.json["items"][0]["translation"])

        graduate_words = self.client.get(
            "/api/content/vocabulary?exam=kaoyan&level=2&limit=20"
        )
        self.assertEqual(graduate_words.status_code, 200)
        self.assertGreater(graduate_words.json["pagination"]["total"], 0)
        self.assertTrue(
            all("考研" in item["tags"] for item in graduate_words.json["items"])
        )

        sentences = self.client.get("/api/content/sentences?level=3&limit=20")
        self.assertEqual(sentences.status_code, 200)
        self.assertEqual(len(sentences.json["items"]), 20)
        self.assertTrue(sentences.json["items"][0]["english"])
        self.assertTrue(sentences.json["items"][0]["chinese"])
        self.assertIn("tatoeba.org", sentences.json["items"][0]["source_url"])

    def test_curriculum_catalog_and_answers_are_not_exposed_before_submission(self):
        catalog = self.client.get("/api/curriculum")
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(
            {stage["id"] for stage in catalog.json["stages"]}, set(server.CURRICULUM_ORDER)
        )
        for stage in catalog.json["stages"]:
            self.assertGreaterEqual(stage["unit_count"], 12)
            detail = self.client.get("/api/curriculum/" + stage["id"])
            self.assertEqual(detail.status_code, 200)
            unit_id = detail.json["units"][0]["id"]
            lesson = self.client.get("/api/curriculum/" + stage["id"] + "/" + unit_id)
            self.assertEqual(lesson.status_code, 200)
            self.assertGreaterEqual(len(lesson.json["unit"]["questions"]), 4)
            for question in lesson.json["unit"]["questions"]:
                self.assertNotIn("answer", question)
                self.assertNotIn("explanation", question)
        self.assertEqual(self.client.get("/api/curriculum/unknown").status_code, 404)
        self.assertEqual(self.client.get("/api/curriculum/junior?band=999").status_code, 400)
        self.assertEqual(self.client.get("/api/curriculum/progress").status_code, 401)
        self.assertEqual(self.client.get("/api/curriculum/review").status_code, 401)

    def test_secondary_and_university_modes_route_without_creating_child_profiles(self):
        registered = self.register(learning_stage="junior", age_band="12-13")
        self.assertEqual(registered.status_code, 200)
        self.assertEqual(registered.json["landing"], "/courses/junior")
        self.assertIsNone(registered.json["child_id"])
        headers = {"Authorization": "Bearer " + registered.json["token"]}
        for stage, age in (("senior", "16-17"), ("university", "18+")):
            response = self.client.put(
                "/api/learning-mode", json={"learning_stage": stage, "age_band": age}, headers=headers
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["landing"], "/courses/" + stage)
            self.assertIsNone(response.json["child_id"])
        conn = server.db()
        self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM child_profiles").fetchone()["n"], 0)
        conn.close()

    def test_curriculum_grading_progress_and_retry_are_scoped_to_the_user(self):
        registered = self.register()
        headers = {"Authorization": "Bearer " + registered.json["token"]}
        data_before = self.client.get("/api/data", headers=headers).json
        unit = server.load_curriculum("junior")["units"][0]
        path = "/api/curriculum/junior/" + unit["id"] + "/attempt"
        answers = {question["id"]: question["answer"] for question in unit["questions"]}
        self.assertEqual(self.client.post(path, json={"answers": answers}).status_code, 401)
        response = self.client.post(
            path, json={"answers": answers, "request_id": "first-complete-attempt"}, headers=headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["score"], 100)
        self.assertTrue(response.json["completed"])
        self.assertTrue(all(item["correct"] for item in response.json["feedback"]))
        repeated = self.client.post(
            path, json={"answers": answers, "request_id": "first-complete-attempt"}, headers=headers
        )
        self.assertEqual(repeated.json, response.json)
        progress = self.client.get("/api/curriculum/progress", headers=headers)
        self.assertEqual(progress.json["summary"]["completed"], 1)
        self.assertEqual(progress.json["summary"]["attempts"], 1)
        self.assertEqual(self.client.get("/api/data", headers=headers).json, data_before)

        other = self.register(email="second@example.com")
        other_headers = {"Authorization": "Bearer " + other.json["token"]}
        other_progress = self.client.get("/api/curriculum/progress", headers=other_headers)
        self.assertEqual(other_progress.json["units"], [])
        self.assertEqual(
            self.client.post(path, json={"answers": {"unknown": "a"}}, headers=headers).status_code, 400
        )

    def test_curriculum_grading_accepts_grammar_aliases_and_normalizes_input(self):
        registered = self.register()
        headers = {"Authorization": "Bearer " + registered.json["token"]}
        curriculum = server.load_curriculum("senior")
        unit = next(item for item in curriculum["units"] if item["id"] == "s-09")
        question = next(item for item in unit["questions"] if item["id"] == "q2")
        self.assertEqual(question["answer"], ["Although", "Though", "Even though"])
        path = "/api/curriculum/senior/" + unit["id"] + "/attempt"
        for alias in ["although", "  THOUGH.  ", "ＥＶＥＮ　ＴＨＯＵＧＨ。"]:
            response = self.client.post(
                path, json={"answers": {question["id"]: alias}}, headers=headers
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json["feedback"][0]["correct"], alias)
            self.assertFalse(response.json["completed"])
        incorrect = self.client.post(
            path, json={"answers": {question["id"]: "Because"}}, headers=headers
        )
        self.assertFalse(incorrect.json["feedback"][0]["correct"])
        self.assertEqual(incorrect.json["feedback"][0]["answer"], question["answer"])
        self.assertTrue(incorrect.json["feedback"][0]["explanation"])

    def test_curriculum_rejects_invalid_child_ids_without_database_errors(self):
        registered = self.register()
        headers = {"Authorization": "Bearer " + registered.json["token"]}
        for invalid_id in [True, "9223372036854775808", "9" * 100, "²", 0]:
            selection = self.client.put(
                "/api/learning-mode",
                json={"learning_stage": "primary", "child_id": invalid_id},
                headers=headers,
            )
            self.assertEqual(selection.status_code, 400, repr(invalid_id))
            progress = self.client.get(
                "/api/curriculum/progress", query_string={"child_id": invalid_id}, headers=headers
            )
            self.assertEqual(progress.status_code, 400, repr(invalid_id))

    def test_curriculum_schema_migration_is_repeatable_and_preserves_legacy_users(self):
        legacy_path = os.path.join(self.tmp.name, "legacy.db")
        with mock.patch.object(server, "DB", legacy_path):
            conn = server.db()
            conn.execute(
                "CREATE TABLE users(id INTEGER PRIMARY KEY,phone TEXT,email TEXT,nickname TEXT,"
                "password_hash TEXT,created_at TEXT,last_login TEXT)"
            )
            conn.execute("INSERT INTO users(id,email,nickname) VALUES(1,'legacy@example.com','旧账号')")
            conn.commit()
            conn.close()
            server.init_db()
            server.init_db()
            conn = server.db()
            legacy = conn.execute("SELECT * FROM users WHERE id=1").fetchone()
            self.assertEqual(legacy["email"], "legacy@example.com")
            self.assertEqual(legacy["learning_stage"], "general")
            self.assertIsNone(legacy["preferred_child_id"])
            tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"course_progress", "course_mistakes", "course_attempt_receipts"}.issubset(tables))
            conn.close()

    def test_curriculum_mistakes_require_ten_consecutive_correct_reviews(self):
        registered = self.register(learning_stage="primary", age_band="8-10")
        headers = {"Authorization": "Bearer " + registered.json["token"]}
        child_id = registered.json["child_id"]
        unit = server.load_curriculum("primary")["units"][0]
        question = unit["questions"][0]
        path = "/api/curriculum/primary/" + unit["id"] + "/attempt"

        def submit(answer):
            return self.client.post(
                path,
                json={"child_id": child_id, "answers": {question["id"]: answer}},
                headers=headers,
            )

        wrong = submit("definitely incorrect response")
        self.assertEqual(wrong.status_code, 200)
        self.assertFalse(wrong.json["completed"])
        self.assertFalse(wrong.json["feedback"][0]["correct"])
        self.assertTrue(wrong.json["feedback"][0]["explanation"])
        review_path = "/api/curriculum/review?stage=primary&child_id=" + str(child_id)
        review = self.client.get(review_path, headers=headers)
        self.assertEqual(len(review.json["items"]), 1)
        self.assertNotIn("answer", review.json["items"][0]["question"])
        correct_answer = question["answer"]
        for _ in range(9):
            submit(correct_answer)
        review = self.client.get(review_path, headers=headers)
        self.assertEqual(review.json["items"][0]["streak"], 9)
        submit("wrong again")
        review = self.client.get(review_path, headers=headers)
        self.assertEqual(review.json["items"][0]["streak"], 0)
        for _ in range(10):
            submit(correct_answer)
        self.assertEqual(self.client.get(review_path, headers=headers).json["items"], [])
        self.assertEqual(
            self.client.get("/api/curriculum/progress", headers=headers).json["units"], []
        )
        other = self.register(email="other-parent@example.com")
        other_headers = {"Authorization": "Bearer " + other.json["token"]}
        self.assertEqual(self.client.get(review_path, headers=other_headers).status_code, 404)
        self.assertEqual(
            self.client.post(
                path, json={"child_id": child_id, "answers": {question["id"]: correct_answer}}, headers=other_headers
            ).status_code,
            404,
        )

    def test_register_tab_has_working_visibility_contract(self):
        with open(server.HTML, "r", encoding="utf-8") as source:
            page = source.read()
        self.assertIn('class="auth-body is-hidden" id="authReg"', page)
        self.assertIn("classList.toggle('is-hidden',login)", page)
        self.assertIn("classList.toggle('is-hidden',!login)", page)
        self.assertNotIn(".auth-body.auth-reg{display:none}", page)

    def test_container_roles_are_http_isolated(self):
        server.APP_ROLE = "user"
        self.assertEqual(self.client.get("/login").status_code, 200)
        self.assertEqual(self.client.get("/app/home").status_code, 200)
        self.assertEqual(self.client.get("/kids").status_code, 200)
        self.assertEqual(self.client.get("/kids/kindergarten").status_code, 200)
        self.assertEqual(self.client.get("/kids/primary").status_code, 200)
        self.assertEqual(self.client.get("/api/curriculum").status_code, 200)
        self.assertEqual(self.client.get("/api/content/stats").status_code, 200)
        vocabulary_asset = self.client.get("/assets/vocabulary-data.js")
        self.assertEqual(vocabulary_asset.status_code, 200)
        self.assertTrue(vocabulary_asset.content_type.startswith("application/javascript"))
        self.assertIn("EXTRA_VOCAB", vocabulary_asset.get_data(as_text=True))
        adult_page = self.client.get("/app/vocabulary").get_data(as_text=True)
        self.assertIn('/assets/vocabulary-data.js?v=1.4.0', adult_page)
        kids_page = self.client.get("/kids").get_data(as_text=True)
        self.assertIn('data-kids-inline="style"', kids_page)
        self.assertIn('data-kids-inline="runtime"', kids_page)
        self.assertIn(".kids-shell", kids_page)
        self.assertIn("window.KidsAPI", kids_page)
        self.assertIn("switchToAdult", kids_page)
        self.assertIn("deleteProfileModal", kids_page)
        self.assertIn("recordAttempt", kids_page)
        self.assertNotIn('/kids/runtime-style?v=', kids_page)
        self.assertNotIn('/kids/runtime-app?v=', kids_page)
        kindergarten_page = self.client.get("/kids/kindergarten").get_data(as_text=True)
        self.assertIn("cartoon-feature", kindergarten_page)
        self.assertIn("playCartoonScene", kindergarten_page)
        self.assertIn("wrongPreview", kindergarten_page)
        primary_page = self.client.get("/kids/primary").get_data(as_text=True)
        self.assertIn("wrongPreview", primary_page)
        self.assertIn("playCurrent(this)", primary_page)
        kids_style = self.client.get("/kids/runtime-style")
        kids_app = self.client.get("/kids/runtime-app")
        self.assertEqual(kids_style.status_code, 200)
        self.assertEqual(kids_app.status_code, 200)
        self.assertTrue(kids_style.content_type.startswith("text/css"))
        self.assertIn("KidsAPI", kids_app.get_data(as_text=True))
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
        self.assertEqual(self.client.get("/kids/runtime-style").status_code, 404)
        self.assertEqual(self.client.get("/assets/vocabulary-data.js").status_code, 404)
        self.assertEqual(self.client.get("/api/content/stats").status_code, 404)
        self.assertEqual(self.client.get("/api/curriculum").status_code, 404)
        self.assertEqual(self.client.get("/courses").status_code, 404)
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

    def test_admin_can_change_password_and_hash_is_persistent(self):
        with mock.patch.object(server, "ADMIN_PASSWORD", "initial-admin-123"):
            login = self.client.post(
                "/api/admin/login", json={"password": "initial-admin-123"}
            )
            self.assertEqual(login.status_code, 200)
            headers = {"Authorization": "Bearer " + login.json["token"]}
            changed = self.client.post(
                "/api/admin/password",
                json={
                    "current_password": "initial-admin-123",
                    "new_password": "new-admin-password-456",
                },
                headers=headers,
            )
            self.assertEqual(changed.status_code, 200)
            old_login = self.client.post(
                "/api/admin/login", json={"password": "initial-admin-123"}
            )
            new_login = self.client.post(
                "/api/admin/login", json={"password": "new-admin-password-456"}
            )
        self.assertEqual(old_login.status_code, 401)
        self.assertEqual(new_login.status_code, 200)
        conn = server.db()
        stored = conn.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key='admin_password_hash'"
        ).fetchone()["setting_value"]
        conn.close()
        self.assertNotIn("new-admin-password-456", stored)

    def test_admin_password_can_be_recovered_without_old_password(self):
        old_token = server.make_admin_token()
        server.save_admin_password("recovered-admin-password-789")
        with mock.patch.object(server, "ADMIN_PASSWORD", "obsolete-env-password"):
            recovered = self.client.post(
                "/api/admin/login", json={"password": "recovered-admin-password-789"}
            )
        self.assertEqual(recovered.status_code, 200)
        conn = server.db()
        old_session = conn.execute(
            "SELECT 1 FROM admin_tokens WHERE token=?", (old_token,)
        ).fetchone()
        conn.close()
        self.assertIsNone(old_session)

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

        switched = self.client.put(
            "/api/learning-mode",
            json={"learning_stage": "general", "age_band": "13+"},
            headers=headers,
        )
        self.assertEqual(switched.status_code, 200)
        self.assertEqual(switched.json["landing"], "/app/home")
        self.assertEqual(switched.json["user"]["learning_stage"], "general")
        me_after_switch = self.client.get("/api/me", headers=headers)
        self.assertEqual(me_after_switch.json["landing"], "/app/home")
        self.assertEqual(me_after_switch.json["user"]["learning_stage"], "general")

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

        registered = self.register(email="other@example.com")
        invalid_switch = self.client.put(
            "/api/learning-mode",
            json={"learning_stage": "general", "age_band": "4-5"},
            headers={"Authorization": "Bearer " + registered.json["token"]},
        )
        self.assertEqual(invalid_switch.status_code, 400)

    def test_learning_mode_selects_owned_child_without_mutating_another_profile(self):
        registered = self.register(learning_stage="primary", age_band="6-8")
        headers = {"Authorization": "Bearer " + registered.json["token"]}
        first_id = registered.json["child_id"]
        created = self.client.post(
            "/api/children",
            json={
                "nickname": "姐姐", "avatar": "fox", "age_band": "10-12",
                "grade_band": "g5-6", "track": "primary", "daily_limit": 15,
            },
            headers=headers,
        )
        self.assertEqual(created.status_code, 201)
        second_id = created.json["child"]["id"]
        selected = self.client.put(
            "/api/learning-mode",
            json={"learning_stage": "primary", "child_id": second_id},
            headers=headers,
        )
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(selected.json["child_id"], second_id)
        self.assertEqual(selected.json["user"]["age_band"], "10-12")
        me = self.client.get("/api/me", headers=headers)
        self.assertEqual(me.json["child_id"], second_id)
        children = self.client.get("/api/children", headers=headers).json["children"]
        age_by_id = {child["id"]: child["age_band"] for child in children}
        self.assertEqual(age_by_id, {first_id: "6-8", second_id: "10-12"})

        wrong_age = self.client.put(
            "/api/learning-mode",
            json={"learning_stage": "primary", "child_id": second_id, "age_band": "6-8"},
            headers=headers,
        )
        self.assertEqual(wrong_age.status_code, 400)
        wrong_track = self.client.put(
            "/api/learning-mode",
            json={"learning_stage": "kindergarten", "child_id": second_id},
            headers=headers,
        )
        self.assertEqual(wrong_track.status_code, 400)
        other = self.register(email="unrelated@example.com")
        other_headers = {"Authorization": "Bearer " + other.json["token"]}
        self.assertEqual(
            self.client.put(
                "/api/learning-mode", json={"learning_stage": "primary", "child_id": second_id}, headers=other_headers
            ).status_code,
            404,
        )
        self.assertEqual(self.client.delete("/api/children/" + str(second_id), headers=headers).status_code, 200)
        me_after_delete = self.client.get("/api/me", headers=headers)
        self.assertEqual(me_after_delete.json["child_id"], first_id)
        remaining = self.client.get("/api/children", headers=headers).json["children"]
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["age_band"], "6-8")

    def test_user_login_bootstrap_endpoints_and_page_are_available(self):
        registered = self.register(learning_stage="general", age_band="13+")
        headers = {"Authorization": "Bearer " + registered.json["token"]}
        self.assertEqual(self.client.get("/api/me", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/data", headers=headers).status_code, 200)
        page = self.client.get("/app/home")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn('id="appLoading"', html)
        self.assertIn('id="bootError"', html)
        self.assertIn("retryBootstrap()", html)
        self.assertIn('class="adult-cinema"', html)
        self.assertIn("checkGram", html)
        self.assertIn("recordAdultAttempt", html)
        self.assertIn("heat-grid", html)
        self.assertIn("-webkit-fill-available", html)
        self.assertIn("overflow-x:hidden", html)

    def test_password_and_progress_validation(self):
        self.assertEqual(self.register(password="short").status_code, 400)
        registered = self.register()
        token = registered.json["token"]
        headers = {"Authorization": "Bearer " + token}

        invalid = self.client.put(
            "/api/data", json={"data": "[]"}, headers=headers
        )
        self.assertEqual(invalid.status_code, 400)

        payload = {
            "studyDays": {"2026-11-03": 3},
            "wrongBook": {
                "grammar|g1": {
                    "type": "grammar",
                    "id": "g1",
                    "streak": 0,
                    "payload": {"q": "She ___ ready.", "answer": "is"},
                }
            },
        }
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

    def test_deleting_last_active_child_switches_account_to_general(self):
        registered = self.register(
            learning_stage="kindergarten", age_band="4-5", nickname="小星星"
        )
        headers = {"Authorization": "Bearer " + registered.json["token"]}
        child_id = registered.json["child_id"]
        deleted = self.client.delete(f"/api/children/{child_id}", headers=headers)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json["remaining"], 0)
        self.assertTrue(deleted.json["switched_to_general"])
        self.assertEqual(deleted.json["landing"], "/app/home")

        me = self.client.get("/api/me", headers=headers)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json["user"]["learning_stage"], "general")
        self.assertEqual(me.json["landing"], "/app/home")
        children = self.client.get("/api/children", headers=headers)
        self.assertEqual(children.json["children"], [])


if __name__ == "__main__":
    unittest.main()
