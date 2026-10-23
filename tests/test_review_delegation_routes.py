"""Route-level tests for patient-scoped independent-review delegation."""
import unittest

from dashboard.app import app
from dashboard.database import db
from dashboard.models import Patient, PatientAssignment, Role, User
from dashboard.services.authentication import hash_password


class ReviewDelegationRouteTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        db.session.rollback()
        db.drop_all()
        db.create_all()

        clinician_role = Role(name="CLINICIAN")
        patient_role = Role(name="PATIENT")
        self.patient_one = Patient(first_name="One", last_name="Patient")
        self.patient_two = Patient(first_name="Two", last_name="Patient")
        self.owner = User(
            display_name="Assigned Clinician",
            email="owner@example.test",
            password_hash=hash_password("correct horse"),
            roles=[clinician_role],
        )
        self.reviewer = User(
            display_name="Independent Reviewer",
            email="reviewer@example.test",
            password_hash=hash_password("correct horse"),
            roles=[clinician_role],
        )
        self.patient_user = User(
            display_name="Patient One",
            email="patient@example.test",
            password_hash=hash_password("correct horse"),
            patient=self.patient_one,
            roles=[patient_role],
        )
        db.session.add_all([
            clinician_role, patient_role, self.patient_one, self.patient_two,
            self.owner, self.reviewer, self.patient_user,
        ])
        db.session.flush()
        db.session.add_all([
            PatientAssignment(
                patient_id=self.patient_one.patient_id,
                clinician_user_id=self.owner.user_id,
                assigned_by_user_id=self.owner.user_id,
            ),
            PatientAssignment(
                patient_id=self.patient_two.patient_id,
                clinician_user_id=self.owner.user_id,
                assigned_by_user_id=self.owner.user_id,
            ),
        ])
        db.session.commit()
        self.client = app.test_client()

    def tearDown(self):
        db.session.rollback()
        db.drop_all()
        db.create_all()
        self.context.pop()

    def _csrf(self):
        self.client.get("/login")
        with self.client.session_transaction() as session:
            return session["revaliv_csrf_token"]

    def _login(self, email):
        token = self._csrf()
        response = self.client.post("/login", data={
            "csrf_token": token,
            "email": email,
            "password": "correct horse",
            "role": "CLINICIAN" if email != "patient@example.test" else "PATIENT",
        })
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))

    def _create_plan(self, patient_id, name):
        response = self.client.post(
            "/workout/plans",
            json={
                "name": name,
                "patient_id": patient_id,
                "exercises": [{
                    "position": 0,
                    "exercise_id": "bicep_curl",
                    "side": "left",
                    "target_repetitions": 3,
                }],
            },
            headers={"X-CSRF-Token": self._csrf()},
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()["plan_id"]

    def test_delegation_allows_only_scoped_review_not_general_patient_access(self):
        self._login("owner@example.test")
        plan_one_id = self._create_plan(
            self.patient_one.patient_id, "Delegated patient-one plan"
        )
        plan_two_id = self._create_plan(
            self.patient_two.patient_id, "Non-delegated patient-two plan"
        )
        grant_response = self.client.post(
            f"/api/patients/{self.patient_one.patient_id}/review-delegations",
            json={
                "reviewer_user_id": self.reviewer.user_id,
                "scope": "plan_approval",
                "reason": "Independent review is required for this plan.",
            },
            headers={"X-CSRF-Token": self._csrf()},
        )
        self.assertEqual(
            grant_response.status_code, 201, grant_response.get_data(as_text=True)
        )

        self.client.post("/logout", data={"csrf_token": self._csrf()})
        self._login("reviewer@example.test")

        self.assertEqual(
            self.client.get(f"/review/workout-plans/{plan_one_id}").status_code,
            200,
        )
        self.assertEqual(
            self.client.get(f"/review/workout-plans/{plan_two_id}").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f"/patients/{self.patient_one.patient_id}").status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                f"/api/patients/{self.patient_one.patient_id}/progression"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                f"/api/patients/{self.patient_one.patient_id}/review-delegations"
            ).status_code,
            403,
        )

        activation = self.client.post(
            "/workout/start",
            json={"plan_id": plan_one_id, "patient_id": self.patient_one.patient_id},
            headers={"X-CSRF-Token": self._csrf()},
        )
        self.assertEqual(activation.status_code, 403)


if __name__ == "__main__":
    unittest.main()
