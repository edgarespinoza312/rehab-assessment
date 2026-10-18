import unittest

from dashboard.app import app
from dashboard.database import db
from dashboard.models import Patient, Role, User
from dashboard.services.authentication import hash_password


class Phase7GPatientUxTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        db.session.rollback()
        db.drop_all()
        db.create_all()
        patient_role = Role(name="PATIENT")
        clinician_role = Role(name="CLINICIAN")
        db.session.add_all([patient_role, clinician_role])
        patient = Patient(patient_id=1, first_name="Pat", last_name="User")
        user = User(
            display_name="Pat User",
            email="patient@example.test",
            password_hash=hash_password("correct horse"),
            patient=patient,
            roles=[patient_role],
        )
        clinician = User(
            display_name="Clinician",
            email="clinician@example.test",
            password_hash=hash_password("correct horse"),
            roles=[clinician_role],
        )
        db.session.add_all([patient, user, clinician])
        db.session.commit()

    def tearDown(self):
        db.session.rollback()
        db.drop_all()
        db.create_all()
        self.context.pop()

    def _csrf(self, client):
        with client.session_transaction() as state:
            return state["revaliv_csrf_token"]

    def _login(self, client, email="patient@example.test"):
        client.get("/login")
        response = client.post("/login", data={
            "csrf_token": self._csrf(client),
            "email": email,
            "password": "correct horse",
        })
        self.assertEqual(response.status_code, 302)

    def test_patient_home_and_results_have_application_navigation(self):
        client = app.test_client()
        self._login(client)
        home = client.get("/patient")
        html = home.get_data(as_text=True)
        self.assertIn("Start Exercise", html)
        self.assertIn("My Results", html)
        self.assertIn("My Progress", html)
        self.assertIn("patient-action-primary", html)

        results = client.get("/patient/results")
        results_html = results.get_data(as_text=True)
        self.assertIn("Back to Patient Home", results_html)
        self.assertIn("/patient/progress", results_html)

    def test_login_has_secondary_clinician_access_without_role_field(self):
        client = app.test_client()
        html = client.get("/login").get_data(as_text=True)
        self.assertIn("Clinician sign in", html)
        self.assertNotIn('name="role"', html)
        self.assertNotIn('name="patient_id"', html)

    def test_workout_builder_exposes_accessible_resistance_help(self):
        client = app.test_client()
        self._login(client)
        self.assertEqual(client.get("/workout/builder").status_code, 200)
        builder_js = client.get("/static/js/workout_builder.js").get_data(as_text=True)
        self.assertIn("numerical amount of resistance", builder_js)
        self.assertIn("aria-describedby", builder_js)
        self.assertIn("aria-expanded", builder_js)

    def test_assessment_page_has_finish_cancel_and_safe_exit_controls(self):
        client = app.test_client()
        self._login(client)
        response = client.post("/assessment", data={
            "csrf_token": self._csrf(client),
            "exercise": "LEFT_BICEP_CURL",
            "patient_id": 1,
        })
        self.assertEqual(response.status_code, 302)
        html = client.get("/assessment?patient_id=1").get_data(as_text=True)
        self.assertIn("Finish Assessment", html)
        self.assertIn("Cancel Assessment", html)
        self.assertIn('href="/patient"', html)

    def test_patient_can_cancel_assessment_and_returns_home(self):
        client = app.test_client()
        self._login(client)
        client.post("/assessment", data={
            "csrf_token": self._csrf(client),
            "exercise": "LEFT_BICEP_CURL",
            "patient_id": 1,
        })
        response = client.post(
            "/discard",
            data={"csrf_token": self._csrf(client)},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/patient"))

    def test_clinician_sign_in_still_uses_server_role(self):
        client = app.test_client()
        client.get("/login")
        response = client.post("/login", data={
            "csrf_token": self._csrf(client),
            "email": "clinician@example.test",
            "password": "correct horse",
            "role": "PATIENT",
        })
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
