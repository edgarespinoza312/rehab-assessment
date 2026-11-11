"""Tests for audit-preserving assessment corrections."""
import unittest
from datetime import datetime
from flask import Flask
from dashboard.database import db
from dashboard.models import AssessmentCorrectionEvent, AssessmentRecord, Patient, Role, User
from dashboard.services.assessment_corrections import (
    CorrectionWorkflowError,
    effective_assessment_values,
    request_assessment_correction,
    review_assessment_correction,
    verify_correction_event_chain,
)


class AssessmentCorrectionWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask("assessment-correction-tests")
        self.app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", SQLALCHEMY_TRACK_MODIFICATIONS=False)
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        role = Role(name="CLINICIAN")
        self.requester = User(display_name="Requester", email="requester@example.test", status="ACTIVE", roles=[role])
        self.reviewer = User(display_name="Reviewer", email="reviewer@example.test", status="ACTIVE", roles=[role])
        patient = Patient(first_name="Historical", last_name="Record", diagnosis="Test-only", affected_side="LEFT")
        db.session.add_all([role, self.requester, self.reviewer, patient])
        db.session.flush()
        record = AssessmentRecord(patient_id=patient.patient_id, exercise="Bicep Curl", repetitions=8,
                                  average_score=78.5, best_score=90.0, worst_score=60.0,
                                  trend="Stable", feedback='["Original feedback"]',
                                  created_at=datetime(2026, 1, 1, 12, 0, 0))
        db.session.add(record)
        db.session.commit()
        self.assessment_id = record.assessment_id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def request(self, value=82.0):
        return request_assessment_correction(
            self.assessment_id, self.requester.user_id, field_name="average_score",
            proposed_value=value,
            reason="A transcription error was confirmed against the source record.",
            evidence_reference="source-review-123",
        )

    def test_accepted_correction_is_overlay_only(self):
        record = db.session.get(AssessmentRecord, self.assessment_id)
        before = record.average_score
        item = self.request()
        self.assertTrue(verify_correction_event_chain(item.correction_id))
        with self.assertRaisesRegex(CorrectionWorkflowError, "cannot approve"):
            review_assessment_correction(item.correction_id, self.requester.user_id,
                                         decision="accept", rationale="Independent review.")
        result = review_assessment_correction(item.correction_id, self.reviewer.user_id,
                                              decision="accept",
                                              rationale="Source confirms the corrected score.")
        self.assertEqual(result.status, "accepted")
        self.assertEqual(record.average_score, before)
        values = effective_assessment_values(self.assessment_id)
        self.assertEqual(values["average_score"], 82.0)
        self.assertEqual(len(values["effective_corrections"]), 1)

    def test_invalid_and_conflicting_corrections_are_rejected(self):
        self.request()
        with self.assertRaisesRegex(CorrectionWorkflowError, "already exists"):
            self.request(85.0)
        for value in (float("nan"), float("inf"), -1.0, 101.0, True):
            with self.subTest(value=value):
                with self.assertRaises(CorrectionWorkflowError):
                    request_assessment_correction(
                        self.assessment_id, self.requester.user_id,
                        field_name="average_score", proposed_value=value,
                        reason="The invalid score proposal must be blocked.",
                    )

    def test_source_change_makes_pending_correction_stale(self):
        item = self.request()
        record = db.session.get(AssessmentRecord, self.assessment_id)
        record.average_score = 77.0
        db.session.commit()
        result = review_assessment_correction(item.correction_id, self.reviewer.user_id,
                                              decision="accept",
                                              rationale="Source changed after the request.")
        self.assertEqual(result.status, "stale")
        self.assertEqual(effective_assessment_values(self.assessment_id)["average_score"], 77.0)

    def test_rejected_correction_does_not_change_effective_values(self):
        item = self.request()
        review_assessment_correction(item.correction_id, self.reviewer.user_id,
                                     decision="reject",
                                     rationale="Evidence does not support the correction.")
        values = effective_assessment_values(self.assessment_id)
        self.assertEqual(values["average_score"], 78.5)
        self.assertEqual(values["effective_corrections"], [])

    def test_tampered_event_chain_blocks_review(self):
        item = self.request()
        event = AssessmentCorrectionEvent.query.filter_by(correction_id=item.correction_id).one()
        event.detail = "changed after commit"
        db.session.commit()
        self.assertFalse(verify_correction_event_chain(item.correction_id))
        with self.assertRaisesRegex(CorrectionWorkflowError, "integrity"):
            review_assessment_correction(item.correction_id, self.reviewer.user_id,
                                         decision="reject",
                                         rationale="Attempted review after audit corruption.")
