import unittest

from dashboard.app import app
from dashboard.database import db
from dashboard.models import Patient, PatientAssignment, Role, User
from dashboard.services.authentication import hash_password


class PatientAssignmentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        db.session.rollback()
        db.drop_all()
        db.create_all()

        admin_role = Role(name="ADMIN")
        clinician_role = Role(name="CLINICIAN")
        patient_role = Role(name="PATIENT")
        patient = Patient(
            patient_id=1,
            first_name="Jordan",
            last_name="Test",
            diagnosis="Test diagnosis",
            affected_side="LEFT",
        )
        self.admin = User(
            display_name="Test Admin",
            email="admin@workflow.test",
            password_hash=hash_password("correct horse"),
            status="ACTIVE",
            roles=[admin_role],
        )
        self.clinician_one = User(
            display_name="Clinician One",
            email="clinician1@workflow.test",
            password_hash=hash_password("correct horse"),
            status="ACTIVE",
            roles=[clinician_role],
        )
        self.clinician_two = User(
            display_name="Clinician Two",
            email="clinician2@workflow.test",
            password_hash=hash_password("correct horse"),
            status="ACTIVE",
            roles=[Role(name="CLINICIAN")],
        )
        db.session.add_all([
            patient, self.admin, self.clinician_one, self.clinician_two,
            patient_role,
        ])
        db.session.commit()
        self.patient_id = patient.patient_id
        self.admin_id = self.admin.user_id
        self.clinician_one_id = self.clinician_one.user_id
        self.clinician_two_id = self.clinician_two.user_id

    def tearDown(self):
        db.session.rollback()
        db.drop_all()
        db.create_all()
        self.context.pop()

    @staticmethod
    def csrf(client):
        with client.session_transaction() as state:
            return state["revaliv_csrf_token"]

    def login(self, client, email):
        client.get("/login")
        return client.post("/login", data={
            "csrf_token": self.csrf(client),
            "email": email,
            "password": "correct horse",
        })

    def claim(self, client, *, filter_value="available"):
        return client.post(
            f"/patients/{self.patient_id}/assignment",
            data={
                "csrf_token": self.csrf(client),
                "action": "claim",
                "filter": filter_value,
            },
        )

    def test_clinician_claims_unassigned_patient_and_gets_clinical_access(self):
        clinician = app.test_client()
        self.login(clinician, "clinician1@workflow.test")

        directory = clinician.get("/patients?filter=available")
        self.assertEqual(directory.status_code, 200)
        self.assertIn("Claim patient", directory.get_data(as_text=True))

        response = self.claim(clinician)
        self.assertEqual(response.status_code, 302)
        assignment = PatientAssignment.query.filter_by(
            patient_id=self.patient_id,
            ended_at=None,
        ).one()
        self.assertEqual(assignment.clinician_user_id, self.clinician_one_id)
        self.assertEqual(
            clinician.get(f"/patients/{self.patient_id}").status_code,
            200,
        )

    def test_second_clinician_cannot_claim_or_view_assigned_patient(self):
        admin = app.test_client()
        self.login(admin, "admin@workflow.test")
        response = admin.post(
            f"/patients/{self.patient_id}/assignment",
            data={
                "csrf_token": self.csrf(admin),
                "action": "assign",
                "clinician_user_id": str(self.clinician_one_id),
                "filter": "all",
            },
        )
        self.assertEqual(response.status_code, 302)

        second = app.test_client()
        self.login(second, "clinician2@workflow.test")
        response = self.claim(second)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            second.get(f"/patients/{self.patient_id}").status_code,
            403,
        )
        self.assertEqual(
            PatientAssignment.query.filter_by(
                patient_id=self.patient_id,
                ended_at=None,
            ).count(),
            1,
        )

    def test_admin_reassignment_preserves_history_and_moves_access(self):
        admin = app.test_client()
        self.login(admin, "admin@workflow.test")
        first = admin.post(
            f"/patients/{self.patient_id}/assignment",
            data={
                "csrf_token": self.csrf(admin),
                "action": "assign",
                "clinician_user_id": str(self.clinician_one_id),
                "filter": "all",
            },
        )
        self.assertEqual(first.status_code, 302)

        first_clinician = app.test_client()
        self.login(first_clinician, "clinician1@workflow.test")
        second_clinician = app.test_client()
        self.login(second_clinician, "clinician2@workflow.test")

        response = admin.post(
            f"/patients/{self.patient_id}/assignment",
            data={
                "csrf_token": self.csrf(admin),
                "action": "assign",
                "clinician_user_id": str(self.clinician_two_id),
                "reason": "Coverage change",
                "filter": "all",
            },
        )
        self.assertEqual(response.status_code, 302)

        history = PatientAssignment.query.filter_by(
            patient_id=self.patient_id
        ).order_by(PatientAssignment.assigned_at.asc()).all()
        self.assertEqual(len(history), 2)
        self.assertIsNotNone(history[0].ended_at)
        self.assertEqual(history[0].end_reason, "Coverage change")
        self.assertEqual(history[0].ended_by_user_id, self.admin_id)
        self.assertIsNone(history[1].ended_at)
        self.assertEqual(history[1].clinician_user_id, self.clinician_two_id)
        self.assertEqual(
            first_clinician.get(f"/patients/{self.patient_id}").status_code,
            403,
        )
        self.assertEqual(
            second_clinician.get(f"/patients/{self.patient_id}").status_code,
            200,
        )

    def test_admin_revocation_removes_access_but_keeps_audit_record(self):
        admin = app.test_client()
        self.login(admin, "admin@workflow.test")
        self.assertEqual(admin.post(
            f"/patients/{self.patient_id}/assignment",
            data={
                "csrf_token": self.csrf(admin),
                "action": "assign",
                "clinician_user_id": str(self.clinician_one_id),
                "filter": "all",
            },
        ).status_code, 302)

        clinician = app.test_client()
        self.login(clinician, "clinician1@workflow.test")
        self.assertEqual(clinician.get(f"/patients/{self.patient_id}").status_code, 200)

        response = admin.post(
            f"/patients/{self.patient_id}/assignment",
            data={
                "csrf_token": self.csrf(admin),
                "action": "revoke",
                "reason": "Care ended",
                "filter": "all",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            clinician.get(f"/patients/{self.patient_id}").status_code,
            403,
        )
        history = PatientAssignment.query.filter_by(
            patient_id=self.patient_id
        ).one()
        self.assertIsNotNone(history.ended_at)
        self.assertEqual(history.end_reason, "Care ended")
        self.assertEqual(history.ended_by_user_id, self.admin_id)


if __name__ == "__main__":
    unittest.main()
