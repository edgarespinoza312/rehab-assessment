import unittest

from dashboard.app import app
from dashboard.database import db
from dashboard.models import Patient, Role, User
from dashboard.services.authentication import hash_password


class Phase7FAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        db.session.rollback()
        db.drop_all()
        db.create_all()
        db.session.add_all([
            Role(name="PATIENT"),
            Role(name="CLINICIAN"),
            Role(name="ADMIN"),
            Patient(patient_id=1, first_name="Existing", last_name="Patient"),
        ])
        db.session.flush()
        admin_role = Role.query.filter_by(name="ADMIN").one()
        clinician_role = Role.query.filter_by(name="CLINICIAN").one()
        db.session.add_all([
            User(
                display_name="Admin",
                email="admin@example.test",
                password_hash=hash_password("correct horse"),
                roles=[admin_role],
            ),
            User(
                display_name="Clinician",
                email="clinician@example.test",
                password_hash=hash_password("correct horse"),
                roles=[clinician_role],
            ),
        ])
        db.session.commit()

    def tearDown(self):
        db.session.rollback()
        db.drop_all()
        db.create_all()
        self.context.pop()

    @staticmethod
    def csrf(client):
        with client.session_transaction() as state:
            return state["revaliv_csrf_token"]

    def login(self, client, email, role=None):
        client.get("/login")
        data = {
            "csrf_token": self.csrf(client),
            "email": email,
            "password": "correct horse",
        }
        if role is not None:
            data["role"] = role
        return client.post("/login", data=data)

    def test_login_ui_removes_role_selector_and_links_registration(self):
        response = self.client.get("/login") if hasattr(self, "client") else app.test_client().get("/login")
        html = response.get_data(as_text=True)
        self.assertNotIn('name="role"', html)
        self.assertIn("Welcome back", html)
        self.assertIn("/register", html)

    def test_patient_registration_creates_linked_patient_and_logs_in(self):
        client = app.test_client()
        client.get("/register")
        response = client.post("/register", data={
            "csrf_token": self.csrf(client),
            "display_name": "New Patient",
            "email": "NEW@example.test",
            "password": "safe password",
            "confirm_password": "safe password",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/patient")
        user = User.query.filter_by(email="new@example.test").one()
        self.assertEqual([role.name for role in user.roles], ["PATIENT"])
        self.assertIsNotNone(user.patient_id)
        self.assertEqual(client.get("/patient").status_code, 200)

    def test_registration_rejects_duplicate_invalid_and_mismatched_input(self):
        client = app.test_client()
        client.get("/register")
        base = {
            "csrf_token": self.csrf(client),
            "display_name": "New Patient",
            "email": "admin@example.test",
            "password": "safe password",
            "confirm_password": "safe password",
        }
        self.assertEqual(client.post("/register", data=base).status_code, 400)
        base["email"] = "not-an-email"
        self.assertEqual(client.post("/register", data=base).status_code, 400)
        base["email"] = "new@example.test"
        base["confirm_password"] = "different"
        self.assertEqual(client.post("/register", data=base).status_code, 400)

    def test_registration_requires_csrf(self):
        client = app.test_client()
        client.get("/register")
        response = client.post("/register", data={
            "display_name": "No Token",
            "email": "none@example.test",
            "password": "safe password",
            "confirm_password": "safe password",
        })
        self.assertEqual(response.status_code, 400)

    def test_only_admin_can_manage_accounts(self):
        anonymous = app.test_client()
        self.assertEqual(anonymous.get("/admin/accounts").status_code, 302)

        clinician = app.test_client()
        self.assertEqual(self.login(clinician, "clinician@example.test", "CLINICIAN").status_code, 302)
        self.assertEqual(clinician.get("/admin/accounts").status_code, 403)

        admin = app.test_client()
        self.assertEqual(self.login(admin, "admin@example.test", "ADMIN").status_code, 302)
        self.assertEqual(admin.get("/admin/accounts").status_code, 200)

    def test_operator_cannot_be_provisioned_until_its_policy_is_defined(self):
        admin = app.test_client()
        self.login(admin, "admin@example.test", "ADMIN")
        html = admin.get("/admin/accounts").get_data(as_text=True)
        self.assertNotIn('<option value="OPERATOR">', html)
        response = admin.post("/admin/accounts", data={
            "csrf_token": self.csrf(admin),
            "display_name": "Unsupported Operator",
            "email": "operator-new@example.test",
            "password": "safe password",
            "role": "OPERATOR",
            "patient_id": "0",
        })
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(User.query.filter_by(email="operator-new@example.test").first())

    def test_admin_can_create_and_disable_account_without_client_role_elevation(self):
        client = app.test_client()
        self.login(client, "admin@example.test", "ADMIN")
        response = client.post("/admin/accounts", data={
            "csrf_token": self.csrf(client),
            "display_name": "Provisioned Clinician",
            "email": "provisioned@example.test",
            "password": "safe password",
            "role": "CLINICIAN",
            "patient_id": "0",
        })
        self.assertEqual(response.status_code, 302)
        user = User.query.filter_by(email="provisioned@example.test").one()
        self.assertEqual([role.name for role in user.roles], ["CLINICIAN"])

        response = client.post(
            f"/admin/accounts/{user.user_id}/disable",
            data={"csrf_token": self.csrf(client)},
        )
        self.assertEqual(response.status_code, 302)
        db.session.refresh(user)
        self.assertEqual(user.status, "DISABLED")

    def test_disabled_account_cannot_login(self):
        user = User.query.filter_by(email="clinician@example.test").one()
        user.status = "DISABLED"
        db.session.commit()
        client = app.test_client()
        client.get("/login")
        response = self.login(client, "clinician@example.test", "CLINICIAN")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
