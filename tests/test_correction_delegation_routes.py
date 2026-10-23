"""Route-level coverage for delegated assessment-correction review."""
import unittest
from datetime import datetime

from dashboard.app import app
from dashboard.database import db
from dashboard.models import AssessmentRecord, Patient, PatientAssignment, Role, User
from dashboard.services.authentication import hash_password


class CorrectionDelegationRouteTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        db.session.rollback()
        db.drop_all()
        db.create_all()

        clinician_role = Role(name="CLINICIAN")
        self.patient = Patient(first_name="Correction", last_name="Patient")
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
        self.other = User(
            display_name="Unrelated Clinician",
            email="other@example.test",
            password_hash=hash_password("correct horse"),
            roles=[clinician_role],
        )
        db.session.add_all([
            clinician_role, self.patient, self.owner, self.reviewer, self.other,
        ])
        db.session.flush()
        db.session.add(PatientAssignment(
            patient_id=self.patient.patient_id,
            clinician_user_id=self.owner.user_id,
            assigned_by_user_id=self.owner.user_id,
        ))
        record = AssessmentRecord(
            patient_id=self.patient.patient_id,
            exercise="Bicep Curl",
            repetitions=8,
            average_score=78.5,
            best_score=90.0,
            worst_score=60.0,
            trend="Stable",
            feedback='["Original feedback"]',
            created_at=datetime(2026, 1, 1, 12, 0, 0),
        )
        db.session.add(record)
        db.session.commit()
        self.assessment_id = record.assessment_id
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
        response = self.client.post("/login", data={
            "csrf_token": self._csrf(),
            "email": email,
            "password": "correct horse",
            "role": "CLINICIAN",
        })
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))

    def test_correction_delegation_allows_review_but_not_general_record_access(self):
        self._login("owner@example.test")
        created = self.client.post(
            f"/api/assessments/{self.assessment_id}/corrections",
            json={
                "field_name": "average_score",
                "proposed_value": 82.0,
                "reason": "A transcription error was confirmed against the source record.",
                "evidence_reference": "source-review-123",
            },
            headers={"X-CSRF-Token": self._csrf()},
        )
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True))
        correction_id = created.get_json()["correction_id"]

        grant = self.client.post(
            f"/api/patients/{self.patient.patient_id}/review-delegations",
            json={
                "reviewer_user_id": self.reviewer.user_id,
                "scope": "assessment_correction",
                "reason": "Independent assessment correction review is required.",
            },
            headers={"X-CSRF-Token": self._csrf()},
        )
        self.assertEqual(grant.status_code, 201, grant.get_data(as_text=True))

        self.client.post("/logout", data={"csrf_token": self._csrf()})
        self._login("reviewer@example.test")
        detail = self.client.get(f"/api/assessment-corrections/{correction_id}")
        self.assertEqual(detail.status_code, 200, detail.get_data(as_text=True))
        review = self.client.post(
            f"/api/assessment-corrections/{correction_id}/review",
            json={
                "decision": "accept",
                "rationale": "The source record supports the proposed correction.",
            },
            headers={"X-CSRF-Token": self._csrf()},
        )
        self.assertEqual(review.status_code, 200, review.get_data(as_text=True))
        self.assertEqual(review.get_json()["status"], "accepted")

        # Delegation is specific to correction review and does not expose
        # the patient's general chart or correction-creation endpoint.
        self.assertEqual(
            self.client.get(f"/patients/{self.patient.patient_id}").status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                f"/api/patients/{self.patient.patient_id}/progression"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                f"/api/assessments/{self.assessment_id}/corrections"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"/api/assessments/{self.assessment_id}/corrections",
                json={
                    "field_name": "average_score",
                    "proposed_value": 81.0,
                    "reason": "Reviewer cannot originate a separate correction request.",
                    "evidence_reference": "unrelated",
                },
                headers={"X-CSRF-Token": self._csrf()},
            ).status_code,
            403,
        )

        self.client.post("/logout", data={"csrf_token": self._csrf()})
        self._login("other@example.test")
        self.assertEqual(
            self.client.get(f"/api/assessment-corrections/{correction_id}").status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"/api/assessment-corrections/{correction_id}/review",
                json={
                    "decision": "reject",
                    "rationale": "An unrelated clinician must not review this correction.",
                },
                headers={"X-CSRF-Token": self._csrf()},
            ).status_code,
            403,
        )


    def test_revoked_assessment_correction_delegation_denies_detail_and_review(self):
        self._login("owner@example.test")
        created = self.client.post(
            f"/api/assessments/{self.assessment_id}/corrections",
            json={
                "field_name": "average_score",
                "proposed_value": 82.0,
                "reason": "A transcription error was confirmed against the source record.",
                "evidence_reference": "source-review-revocation-123",
            },
            headers={"X-CSRF-Token": self._csrf()},
        )
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True))
        correction_id = created.get_json()["correction_id"]

        grant = self.client.post(
            f"/api/patients/{self.patient.patient_id}/review-delegations",
            json={
                "reviewer_user_id": self.reviewer.user_id,
                "scope": "assessment_correction",
                "reason": "Independent review is required before reconciliation.",
            },
            headers={"X-CSRF-Token": self._csrf()},
        )
        self.assertEqual(grant.status_code, 201, grant.get_data(as_text=True))
        delegation_id = grant.get_json()["delegation_id"]

        self.client.post("/logout", data={"csrf_token": self._csrf()})
        self._login("reviewer@example.test")
        self.assertEqual(
            self.client.get(f"/api/assessment-corrections/{correction_id}").status_code,
            200,
        )

        self.client.post("/logout", data={"csrf_token": self._csrf()})
        self._login("owner@example.test")
        revoked = self.client.post(
            f"/api/patient-review-delegations/{delegation_id}/revoke",
            json={"reason": "Independent review is no longer required."},
            headers={"X-CSRF-Token": self._csrf()},
        )
        self.assertEqual(revoked.status_code, 200, revoked.get_data(as_text=True))
        self.assertIsNotNone(revoked.get_json()["revoked_at"])

        self.client.post("/logout", data={"csrf_token": self._csrf()})
        self._login("reviewer@example.test")
        detail = self.client.get(f"/api/assessment-corrections/{correction_id}")
        self.assertEqual(detail.status_code, 403, detail.get_data(as_text=True))
        review = self.client.post(
            f"/api/assessment-corrections/{correction_id}/review",
            json={
                "decision": "accept",
                "rationale": "The source record supports the proposed correction.",
            },
            headers={"X-CSRF-Token": self._csrf()},
        )
        self.assertEqual(review.status_code, 403, review.get_data(as_text=True))

        # The pending correction itself remains available to the assigned
        # clinician; revocation removes delegated authorization, not history.
        self.client.post("/logout", data={"csrf_token": self._csrf()})
        self._login("owner@example.test")
        owner_detail = self.client.get(
            f"/api/assessment-corrections/{correction_id}"
        )
        self.assertEqual(owner_detail.status_code, 200, owner_detail.get_data(as_text=True))
        self.assertEqual(owner_detail.get_json()["status"], "pending")

if __name__ == "__main__":
    unittest.main()
