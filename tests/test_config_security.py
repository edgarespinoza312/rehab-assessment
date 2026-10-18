import re
import unittest

from dashboard.config import resolve_security_settings


class ConfigSecurityTests(unittest.TestCase):
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

    def test_production_rejects_explicitly_disabled_secure_cookies(self):
        with self.assertRaisesRegex(RuntimeError, "REVALIV_SECURE_COOKIES"):
            resolve_security_settings({
                "REVALIV_ENV": "production",
                "REVALIV_SECRET_KEY": "persistent-production-secret",
                "REVALIV_SECURE_COOKIES": "0",
            })


if __name__ == "__main__":
    unittest.main()
