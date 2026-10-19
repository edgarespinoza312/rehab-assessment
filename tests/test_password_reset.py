import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from dashboard.app import app
from dashboard.database import db
from dashboard.models import Patient, Role, User
from dashboard.services.authentication import hash_password, verify_password
from dashboard.services.password_reset import generate_password_reset_token


class PasswordResetTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        db.session.rollback()
        db.drop_all()
        db.create_all()
        patient_role = Role(name="PATIENT")
        self.user = User(
            display_name="Reset Test Patient",
            email="reset-patient@example.test",
            password_hash=hash_password("original password"),
            status="ACTIVE",
            roles=[patient_role],
        )
        db.session.add(self.user)
        db.session.commit()
        self.user_id = self.user.user_id
        self.client = app.test_client()

    def tearDown(self):
        db.session.rollback()
        db.drop_all()
        db.create_all()
        self.context.pop()

    def csrf(self):
        self.client.get("/forgot-password")
        with self.client.session_transaction() as state:
            return state["revaliv_csrf_token"]

    def submit_reset_request(self, email, csrf_token):
        return self.client.post(
            "/forgot-password",
            data={"csrf_token": csrf_token, "email": email},
        )

    def test_login_page_links_to_forgot_password(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/forgot-password", response.get_data(as_text=True))

    def test_reset_request_response_does_not_reveal_account_existence(self):
        token = self.csrf()
        with patch("dashboard.app.send_password_reset_email") as send_email:
            known = self.submit_reset_request("RESET-PATIENT@example.test", token)
            send_email.assert_called_once()
            reset_url = send_email.call_args.args[1]
            unknown = self.submit_reset_request("unknown@example.test", token)
            send_email.assert_called_once()

        self.assertEqual(known.status_code, 200)
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(known.get_data(as_text=True), unknown.get_data(as_text=True))
        self.assertIn("If an active account uses that email address", known.get_data(as_text=True))
        self.assertNotIn("reset-patient@example.test", known.get_data(as_text=True))
        self.assertIn("/reset-password/", urlsplit(reset_url).path)

    def test_request_requires_csrf(self):
        response = self.client.post(
            "/forgot-password",
            data={"email": "reset-patient@example.test"},
        )
        self.assertEqual(response.status_code, 400)

    def test_valid_token_resets_password_and_becomes_unusable(self):
        csrf = self.csrf()
        with patch("dashboard.app.send_password_reset_email") as send_email:
            response = self.submit_reset_request("reset-patient@example.test", csrf)
        self.assertEqual(response.status_code, 200)
        reset_url = send_email.call_args.args[1]
        reset_path = urlsplit(reset_url).path

        form = self.client.get(reset_path)
        self.assertEqual(form.status_code, 200)
        self.assertIn("Choose a new password", form.get_data(as_text=True))
        with self.client.session_transaction() as state:
            reset_csrf = state["revaliv_csrf_token"]
        update = self.client.post(reset_path, data={
            "csrf_token": reset_csrf,
            "password": "new secure password",
            "confirm_password": "new secure password",
        })
        self.assertEqual(update.status_code, 302)
        self.assertIn("password_reset=success", update.location)

        db.session.expire_all()
        user = db.session.get(User, self.user_id)
        self.assertTrue(verify_password(user, "new secure password"))
        self.assertFalse(verify_password(user, "original password"))
        self.assertEqual(self.client.get(reset_path).status_code, 400)

        login_csrf = self.csrf()
        login = self.client.post("/login", data={
            "csrf_token": login_csrf,
            "email": "reset-patient@example.test",
            "password": "new secure password",
        })
        self.assertEqual(login.status_code, 302)

    def test_password_reset_invalidates_sessions_and_releases_all_runtimes(self):
        patient = Patient(first_name="Reset", last_name="Patient")
        self.user.patient = patient
        db.session.add(patient)
        db.session.commit()

        clients = [self.client, app.test_client()]
        runtime_ids = []
        for client in clients:
            client.get("/login")
            with client.session_transaction() as state:
                csrf = state["revaliv_csrf_token"]
            response = client.post("/login", data={
                "csrf_token": csrf,
                "email": "reset-patient@example.test",
                "password": "original password",
                "role": "PATIENT",
            })
            self.assertEqual(response.status_code, 302)
            self.assertEqual(client.get("/patient").status_code, 200)

            with client.session_transaction() as state:
                assessment_csrf = state["revaliv_csrf_token"]
            started = client.post("/assessment", data={
                "csrf_token": assessment_csrf,
                "exercise": "LEFT_BICEP_CURL",
                "patient_id": patient.patient_id,
            })
            self.assertEqual(started.status_code, 302)
            with client.session_transaction() as state:
                runtime_id = state[RUNTIME_SESSION_KEY]
            self.assertIsNotNone(runtime_registry.get(runtime_id))
            runtime_ids.append(runtime_id)

        with patch("dashboard.app.send_password_reset_email") as send_email:
            response = self.submit_reset_request(
                "reset-patient@example.test",
                self.csrf(),
            )
        self.assertEqual(response.status_code, 200)
        reset_path = urlsplit(send_email.call_args.args[1]).path
        self.assertEqual(self.client.get(reset_path).status_code, 200)
        with self.client.session_transaction() as state:
            reset_csrf = state["revaliv_csrf_token"]
        response = self.client.post(reset_path, data={
            "csrf_token": reset_csrf,
            "password": "updated secure password",
            "confirm_password": "updated secure password",
        })
        self.assertEqual(response.status_code, 302)

        # Password reset clears the resetting session, invalidates every
        # session on its next request, and tears down active runtime contexts
        # so an already-open video stream cannot outlive revoked credentials.
        self.assertEqual(self.client.get("/patient").status_code, 302)
        self.assertEqual(clients[1].get("/patient").status_code, 302)
        for runtime_id in runtime_ids:
            self.assertIsNone(runtime_registry.get(runtime_id))

    def test_invalid_and_expired_tokens_are_rejected(self):
        bad_link = self.client.get("/reset-password/not-a-valid-token")
        self.assertEqual(bad_link.status_code, 400)
        self.assertIn("invalid or expired", bad_link.get_data(as_text=True))

        token = generate_password_reset_token(self.user)
        original_max_age = app.config["PASSWORD_RESET_TOKEN_MAX_AGE"]
        try:
            app.config["PASSWORD_RESET_TOKEN_MAX_AGE"] = -1
            expired = self.client.get(f"/reset-password/{token}")
            self.assertEqual(expired.status_code, 400)
        finally:
            app.config["PASSWORD_RESET_TOKEN_MAX_AGE"] = original_max_age

    def test_password_mismatch_does_not_change_password(self):
        csrf = self.csrf()
        with patch("dashboard.app.send_password_reset_email") as send_email:
            self.submit_reset_request("reset-patient@example.test", csrf)
        reset_path = urlsplit(send_email.call_args.args[1]).path
        self.client.get(reset_path)
        with self.client.session_transaction() as state:
            reset_csrf = state["revaliv_csrf_token"]
        response = self.client.post(reset_path, data={
            "csrf_token": reset_csrf,
            "password": "new secure password",
            "confirm_password": "does not match",
        })
        self.assertEqual(response.status_code, 400)
        db.session.expire_all()
        user = db.session.get(User, self.user_id)
        self.assertTrue(verify_password(user, "original password"))

    def test_disabled_accounts_do_not_receive_reset_email(self):
        self.user.status = "DISABLED"
        db.session.commit()
        csrf = self.csrf()
        with patch("dashboard.app.send_password_reset_email") as send_email:
            response = self.submit_reset_request("reset-patient@example.test", csrf)
        self.assertEqual(response.status_code, 200)
        send_email.assert_not_called()


if __name__ == "__main__":
    unittest.main()
