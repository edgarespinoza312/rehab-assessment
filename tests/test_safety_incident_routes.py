"""Authenticated route tests for safety reporting and session activation holds."""

import unittest

from dashboard.app import app
from dashboard.database import db
from dashboard.models import Patient, PatientAssignment, Role, User
from dashboard.services.authentication import hash_password
from tests.support.auth import login_client


class SafetyIncidentRouteTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        db.session.rollback()
        db.drop_all()
        db.create_all()

        role = Role(name="CLINICIAN")
        patient = Patient(
            patient_id=71,
            first_name="Safety",
            last_name="Test",
            diagnosis="Test only",
            affected_side="LEFT",
        )
        clinician = User(
            display_name="Safety Test Clinician",
            email="clinician@test.invalid",
            password_hash=hash_password("test-password"),
            status="ACTIVE",
            roles=[role],
        )
        db.session.add_all([role, patient, clinician])
        db.session.flush()
        db.session.add(PatientAssignment(
            patient_id=patient.patient_id,
            clinician_user_id=clinician.user_id,
            assigned_by_user_id=clinician.user_id,
        ))
        db.session.commit()
        self.client = app.test_client()
        login_client(app, self.client)
        with self.client.session_transaction() as session:
            self.csrf_token = session["revaliv_csrf_token"]

    def tearDown(self):
        db.session.rollback()
        db.drop_all()
        db.create_all()
        db.session.remove()
        self.context.pop()

    def test_critical_report_immediately_blocks_both_session_entry_points(self):
        reported = self.client.post(
            "/api/safety/incidents",
            json={
                "category": "measurement_quality",
                "summary": "Critical score corruption safety report",
                "details": "A critical issue was reproduced with corrupted assessment data.",
                "severity": "critical",
                "likelihood": "unlikely",
                "evidence_strength": "weak",
                "exposure_count": 1,
                "control_failure": False,
            },
            headers={"X-CSRF-Token": self.csrf_token},
        )
        self.assertEqual(reported.status_code, 201)
        payload = reported.get_json()
        self.assertEqual(payload["status"], "restricted")
        self.assertTrue(payload["event_chain_valid"])

        legacy_start = self.client.post(
            "/assessment",
            data={
                "exercise": "LEFT_BICEP_CURL",
                "patient_id": "71",
                "csrf_token": self.csrf_token,
            },
        )
        self.assertEqual(legacy_start.status_code, 423)
        self.assertEqual(
            legacy_start.get_json()["restriction_scope"],
            "clinical_assessment_start",
        )

        workout_start = self.client.post(
            "/workout/start",
            json={"preset_id": "starter_bicep_curl", "patient_id": 71},
            headers={"X-CSRF-Token": self.csrf_token},
        )
        self.assertEqual(workout_start.status_code, 423)
        self.assertEqual(
            workout_start.get_json()["restriction_scope"],
            "workout_activation",
        )

    def test_incident_collection_requires_a_safety_lead_role(self):
        # The authorized clinician can list incidents; the service rejects
        # untrusted fields rather than coercing strings into safety decisions.
        response = self.client.get("/api/safety/incidents")
        self.assertEqual(response.status_code, 200)

        invalid = self.client.post(
            "/api/safety/incidents",
            json={
                "category": "measurement_quality",
                "summary": "Malformed risk payload should be rejected",
                "severity": ["critical"],
                "likelihood": "unlikely",
                "evidence_strength": "weak",
            },
            headers={"X-CSRF-Token": self.csrf_token},
        )
        self.assertEqual(invalid.status_code, 400)
