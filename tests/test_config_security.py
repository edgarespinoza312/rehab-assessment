import re
import unittest

from flask import Flask, request

from dashboard.config import Config, resolve_security_settings, resolve_unvalidated_exercise_setting


class ConfigSecurityTests(unittest.TestCase):
    def test_request_body_limit_rejects_oversized_posts(self):
        app = Flask(__name__)
        app.config.from_object(Config)

        @app.route("/submit", methods=["POST"])
        def submit():
            return str(len(request.get_data()))

        response = app.test_client().post(
            "/submit",
            data=b"x" * (Config.MAX_CONTENT_LENGTH + 1),
        )
        self.assertEqual(response.status_code, 413)

    def test_development_uses_ephemeral_secret_and_http_compatible_cookies(self):
        secret, secure_cookies = resolve_security_settings({
            "REVALIV_ENV": "development",
        })
        self.assertRegex(secret, re.compile(r"^[0-9a-f]{64}$"))
        self.assertFalse(secure_cookies)

    def test_development_can_explicitly_enable_secure_cookies(self):
        secret, secure_cookies = resolve_security_settings({
            "REVALIV_ENV": "development",
            "REVALIV_SECRET_KEY": "local-test-secret",
            "REVALIV_SECURE_COOKIES": "1",
        })
        self.assertEqual(secret, "local-test-secret")
        self.assertTrue(secure_cookies)

    def test_production_requires_configured_secret_and_defaults_secure_cookies_on(self):
        with self.assertRaisesRegex(RuntimeError, "REVALIV_SECRET_KEY"):
            resolve_security_settings({"REVALIV_ENV": "production"})

        secret, secure_cookies = resolve_security_settings({
            "REVALIV_ENV": "production",
            "REVALIV_SECRET_KEY": "persistent-production-secret",
        })
        self.assertEqual(secret, "persistent-production-secret")
        self.assertTrue(secure_cookies)

    def test_unvalidated_exercise_mode_is_opt_in(self):
        self.assertFalse(resolve_unvalidated_exercise_setting({"REVALIV_ENV": "development"}))
        self.assertTrue(resolve_unvalidated_exercise_setting({
            "REVALIV_ENV": "development",
            "REVALIV_ENABLE_UNVALIDATED_EXERCISES": "1",
        }))

    def test_production_cannot_enable_unvalidated_exercises(self):
        with self.assertRaisesRegex(RuntimeError, "must remain disabled in production"):
            resolve_unvalidated_exercise_setting({
                "REVALIV_ENV": "production",
                "REVALIV_ENABLE_UNVALIDATED_EXERCISES": "1",
            })
        self.assertFalse(resolve_unvalidated_exercise_setting({
            "REVALIV_ENV": "production",
            "REVALIV_ENABLE_UNVALIDATED_EXERCISES": "0",
        }))

    def test_production_rejects_explicitly_disabled_secure_cookies(self):
        with self.assertRaisesRegex(RuntimeError, "REVALIV_SECURE_COOKIES"):
            resolve_security_settings({
                "REVALIV_ENV": "production",
                "REVALIV_SECRET_KEY": "persistent-production-secret",
                "REVALIV_SECURE_COOKIES": "0",
            })


if __name__ == "__main__":
    unittest.main()
