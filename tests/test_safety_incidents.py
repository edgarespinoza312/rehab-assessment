"""Tests for risk-based safety incident and corrective-action governance."""

import unittest
from datetime import datetime, timedelta

from flask import Flask

from dashboard.database import db
from dashboard.models import Role, User, SafetyIncidentEvent, SafetyCorrectiveAction
from dashboard.services.safety_incidents import (
    SafetyRestrictionError,
    SafetyWorkflowError,
    active_safety_restrictions,
    assert_safety_scope_allowed,
    close_safety_incident,
    create_corrective_action,
    record_independent_safety_review,
    reopen_safety_incident,
    report_safety_incident,
    triage_safety_incident,
    update_corrective_action,
    verify_safety_event_chain,
)


class SafetyIncidentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(f"safety-test-{id(self)}")
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI="sqlite://",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        clinician_role = Role(name="CLINICIAN")
        admin_role = Role(name="ADMIN")
        operator_role = Role(name="OPERATOR")
        self.reporter = User(
            display_name="Reporter",
            email=f"reporter-{id(self)}@example.test",
            status="ACTIVE",
            roles=[clinician_role],
        )
        self.owner = User(
            display_name="Investigation Owner",
            email=f"owner-{id(self)}@example.test",
            status="ACTIVE",
            roles=[operator_role],
        )
        self.reviewer = User(
            display_name="Independent Reviewer",
            email=f"reviewer-{id(self)}@example.test",
            status="ACTIVE",
            roles=[clinician_role],
        )
        self.closer = User(
            display_name="Independent Closer",
            email=f"closer-{id(self)}@example.test",
            status="ACTIVE",
            roles=[admin_role],
        )
        db.session.add_all([
            clinician_role, admin_role, operator_role,
            self.reporter, self.owner, self.reviewer, self.closer,
        ])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _report(self, **overrides):
        values = {
            "category": "measurement_quality",
            "summary": "Assessment reported an implausible movement score",
            "details": "A user reported a score inconsistent with the observed movement.",
            "severity": "low",
            "likelihood": "possible",
            "evidence_strength": "moderate",
            "exposure_count": 1,
            "control_failure": False,
        }
        values.update(overrides)
        return report_safety_incident(self.reporter.user_id, **values)

    def test_critical_incident_applies_default_precautionary_restrictions(self):
        incident = self._report(
            severity="critical",
            likelihood="unlikely",
            evidence_strength="weak",
        )
        self.assertEqual(incident.priority_tier, "critical")
        self.assertEqual(incident.status, "restricted")
        self.assertIn("workout_activation", incident.restriction_scopes)
        self.assertIn("clinical_assessment_start", incident.restriction_scopes)
        self.assertLessEqual(
            incident.response_due_at - incident.reported_at,
            timedelta(hours=1, seconds=1),
        )
        self.assertTrue(verify_safety_event_chain(incident.incident_id))
        with self.assertRaises(SafetyRestrictionError):
            assert_safety_scope_allowed("workout_activation")

    def test_serious_incident_with_control_failure_is_critical_priority(self):
        incident = self._report(severity="serious", control_failure=True)
        self.assertEqual(incident.priority_tier, "critical")
        self.assertEqual(incident.status, "restricted")

    def test_untrusted_report_payloads_fail_closed(self):
        with self.assertRaises(SafetyWorkflowError):
            self._report(severity=["critical"])
        with self.assertRaises(SafetyWorkflowError):
            self._report(exposure_count=True)
        with self.assertRaises(SafetyWorkflowError):
            self._report(control_failure="yes")
        with self.assertRaises(SafetyWorkflowError):
            self._report(likelihood="impossible")

    def test_hash_chain_detects_tampering_and_blocks_triage(self):
        incident = self._report()
        event = SafetyIncidentEvent.query.filter_by(
            incident_id=incident.incident_id
        ).one()
        event.detail = "tampered"
        db.session.commit()

        self.assertFalse(verify_safety_event_chain(incident.incident_id))
        with self.assertRaisesRegex(SafetyWorkflowError, "integrity verification"):
            triage_safety_incident(
                incident.incident_id,
                self.closer.user_id,
                owner_user_id=self.owner.user_id,
            )

    def test_restriction_state_corruption_fails_closed(self):
        incident = self._report()
        incident.restriction_scopes = "[invalid"
        db.session.commit()
        with self.assertRaises(SafetyRestrictionError):
            assert_safety_scope_allowed("data_export")

    def test_independent_review_cannot_be_reporter_or_owner(self):
        incident = self._report()
        triage_safety_incident(
            incident.incident_id,
            self.closer.user_id,
            owner_user_id=self.owner.user_id,
        )
        with self.assertRaisesRegex(SafetyWorkflowError, "independent reviewer"):
            record_independent_safety_review(
                incident.incident_id,
                self.reporter.user_id,
                "I am reviewing my own report.",
            )
        with self.assertRaisesRegex(SafetyWorkflowError, "independent reviewer"):
            record_independent_safety_review(
                incident.incident_id,
                self.owner.user_id,
                "I am the assigned investigation owner.",
            )

    def test_closure_requires_independent_review_and_verified_actions(self):
        incident = self._report(
            severity="serious",
            control_failure=True,
        )
        triage_safety_incident(
            incident.incident_id,
            self.closer.user_id,
            owner_user_id=self.owner.user_id,
            root_cause_status="unknown",
            root_cause_notes="Available evidence cannot yet support a unique root cause.",
        )
        with self.assertRaisesRegex(SafetyWorkflowError, "independent review"):
            close_safety_incident(
                incident.incident_id,
                self.closer.user_id,
                rationale="Close the incident pending review.",
                root_cause_status="unknown",
                root_cause_notes="Root cause remains unknown after investigation.",
                external_board_reference="BOARD-2026-01",
            )

        action = create_corrective_action(
            incident.incident_id,
            self.reporter.user_id,
            title="Add score-range validation",
            description="Prevent non-finite score data from entering persistence.",
            owner_user_id=self.owner.user_id,
            due_at=datetime.utcnow() + timedelta(days=1),
        )
        update_corrective_action(
            incident.incident_id,
            action.action_id,
            self.owner.user_id,
            status="completed",
            evidence="The score validation patch was deployed to the test branch.",
        )
        with self.assertRaisesRegex(SafetyWorkflowError, "independently verified"):
            close_safety_incident(
                incident.incident_id,
                self.closer.user_id,
                rationale="Close without verifying the corrective action.",
                root_cause_status="unknown",
                root_cause_notes="Root cause remains unknown after investigation.",
                external_board_reference="BOARD-2026-01",
            )

        update_corrective_action(
            incident.incident_id,
            action.action_id,
            self.closer.user_id,
            status="verified",
            effectiveness_result="Regression evidence shows the invalid score is rejected.",
        )
        record_independent_safety_review(
            incident.incident_id,
            self.reviewer.user_id,
            "Independently reviewed evidence and corrective-action effectiveness.",
        )
        with self.assertRaisesRegex(SafetyWorkflowError, "external independent-board"):
            close_safety_incident(
                incident.incident_id,
                self.closer.user_id,
                rationale="Close after the evidence and action were reviewed.",
                root_cause_status="unknown",
                root_cause_notes="The exact root cause could not be determined from available evidence.",
            )

        closed = close_safety_incident(
            incident.incident_id,
            self.closer.user_id,
            rationale="Close after action effectiveness and independent review were recorded.",
            root_cause_status="unknown",
            root_cause_notes="The exact root cause could not be determined from available evidence.",
            external_board_reference="BOARD-CASE-2026-01",
        )
        self.assertEqual(closed.status, "closed")
        self.assertTrue(verify_safety_event_chain(incident.incident_id))
        # A closed case no longer actively blocks the designated capability.
        self.assertEqual(active_safety_restrictions("workout_activation"), [])

    def test_closed_case_can_be_reopened_on_a_defined_trigger(self):
        incident = self._report()
        triage_safety_incident(
            incident.incident_id,
            self.closer.user_id,
            owner_user_id=self.owner.user_id,
            root_cause_status="known",
            root_cause_notes="Input validation was missing at a defined boundary.",
        )
        record_independent_safety_review(
            incident.incident_id,
            self.reviewer.user_id,
            "Evidence and root-cause assessment were independently reviewed.",
        )
        closed = close_safety_incident(
            incident.incident_id,
            self.closer.user_id,
            rationale="The low-priority issue was corrected and evidence reviewed.",
            root_cause_status="known",
            root_cause_notes="Input validation was missing at a defined boundary.",
        )
        self.assertEqual(closed.status, "closed")
        reopened = reopen_safety_incident(
            incident.incident_id,
            self.closer.user_id,
            trigger="recurrence",
            details="The same failure mode appeared in a later controlled regression run.",
        )
        self.assertEqual(reopened.status, "reopened")
        self.assertIsNone(reopened.closed_at)
        self.assertIsNone(reopened.independent_reviewer_user_id)
        self.assertTrue(verify_safety_event_chain(incident.incident_id))

