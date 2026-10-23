"""Narrow independent-review grants expire with assignment and can be revoked."""
import unittest

from flask import Flask

from dashboard.database import db
from dashboard.models import Patient, PatientAssignment, PatientReviewDelegation, Role, User
from dashboard.services.patient_assignments import assign_patient
from dashboard.services.patient_review_delegations import (
    ReviewDelegationError,
    create_review_delegation,
    has_active_review_delegation,
    revoke_review_delegation,
)


class PatientReviewDelegationTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask("review-delegations")
        self.app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", SQLALCHEMY_TRACK_MODIFICATIONS=False)
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        role = Role(name="CLINICIAN")
        self.owner = User(display_name="Assigned Clinician", email="owner@example.test", status="ACTIVE", roles=[role])
        self.reviewer = User(display_name="Independent Clinician", email="reviewer@example.test", status="ACTIVE", roles=[role])
        self.other = User(display_name="Other Clinician", email="other@example.test", status="ACTIVE", roles=[role])
        self.patient = Patient(first_name="Delegation", last_name="Patient", diagnosis="Test-only", affected_side="LEFT")
        db.session.add_all([role, self.owner, self.reviewer, self.other, self.patient])
        db.session.flush()
        assignment = PatientAssignment(
            patient_id=self.patient.patient_id,
            clinician_user_id=self.owner.user_id,
            assigned_by_user_id=self.owner.user_id,
        )
        db.session.add(assignment)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_scope_is_narrow_and_revocation_is_durable(self):
        grant = create_review_delegation(
            self.patient.patient_id,
            self.owner.user_id,
            self.reviewer.user_id,
            scope="plan_approval",
            reason="Independent review of a proposed plan is required.",
        )
        self.assertTrue(has_active_review_delegation(self.reviewer.user_id, self.patient.patient_id, "plan_approval"))
        self.assertFalse(has_active_review_delegation(self.reviewer.user_id, self.patient.patient_id, "assessment_correction"))
        revoked = revoke_review_delegation(
            grant.delegation_id, self.owner.user_id,
            reason="The review request is no longer active.",
        )
        self.assertIsNotNone(revoked.revoked_at)
        self.assertFalse(has_active_review_delegation(self.reviewer.user_id, self.patient.patient_id, "plan_approval"))
        self.assertEqual(PatientReviewDelegation.query.count(), 1)

    def test_reviewer_cannot_self_delegate_and_only_assigned_clinician_grants(self):
        with self.assertRaisesRegex(ReviewDelegationError, "independent"):
            create_review_delegation(
                self.patient.patient_id, self.owner.user_id, self.owner.user_id,
                scope="plan_approval", reason="No self-review delegation allowed.",
            )
        with self.assertRaisesRegex(ReviewDelegationError, "currently assigned"):
            create_review_delegation(
                self.patient.patient_id, self.other.user_id, self.reviewer.user_id,
                scope="plan_approval", reason="An unrelated clinician cannot grant access.",
            )

    def test_assignment_transfer_automatically_invalidates_prior_grant(self):
        grant = create_review_delegation(
            self.patient.patient_id, self.owner.user_id, self.reviewer.user_id,
            scope="assessment_correction",
            reason="Independent assessment correction review is required.",
        )
        # Only an admin may reassign, so add a separately identified admin.
        admin_role = Role(name="ADMIN")
        admin = User(display_name="Administrator", email="admin@example.test", status="ACTIVE", roles=[admin_role])
        db.session.add_all([admin_role, admin])
        db.session.commit()
        assign_patient(
            self.patient.patient_id,
            self.other.user_id,
            admin.user_id,
            allow_reassignment=True,
            reason="Controlled test of delegation revocation on reassignment.",
        )
        self.assertFalse(has_active_review_delegation(self.reviewer.user_id, self.patient.patient_id, "assessment_correction"))
        # Delegation remains as historical evidence but is no longer effective.
        self.assertIsNone(db.session.get(PatientReviewDelegation, grant.delegation_id).revoked_at)

    def test_duplicate_active_grant_is_rejected(self):
        create_review_delegation(
            self.patient.patient_id, self.owner.user_id, self.reviewer.user_id,
            scope="plan_approval",
            reason="Independent review of the treatment plan is required.",
        )
        with self.assertRaisesRegex(ReviewDelegationError, "already exists"):
            create_review_delegation(
                self.patient.patient_id, self.owner.user_id, self.reviewer.user_id,
                scope="plan_approval",
                reason="A duplicate active review grant must not be created.",
            )
        self.assertEqual(PatientReviewDelegation.query.count(), 1)

    def test_inactive_reviewer_loses_effective_delegated_access(self):
        grant = create_review_delegation(
            self.patient.patient_id, self.owner.user_id, self.reviewer.user_id,
            scope="assessment_correction",
            reason="Independent correction review is required.",
        )
        self.reviewer.status = "DISABLED"
        db.session.commit()
        self.assertFalse(
            has_active_review_delegation(
                self.reviewer.user_id,
                self.patient.patient_id,
                "assessment_correction",
            )
        )
        # Preserve the grant as historical evidence; disabled status alone
        # removes effective access without rewriting the delegation record.
        self.assertIsNone(
            db.session.get(PatientReviewDelegation, grant.delegation_id).revoked_at
        )

    def test_only_grantor_or_active_admin_can_revoke_and_revoke_is_one_time(self):
        grant = create_review_delegation(
            self.patient.patient_id, self.owner.user_id, self.reviewer.user_id,
            scope="plan_approval",
            reason="Independent review of the treatment plan is required.",
        )
        with self.assertRaisesRegex(ReviewDelegationError, "grantor or an active admin"):
            revoke_review_delegation(
                grant.delegation_id,
                self.other.user_id,
                reason="An unrelated clinician must not revoke this grant.",
            )
        self.assertIsNone(
            db.session.get(PatientReviewDelegation, grant.delegation_id).revoked_at
        )
        revoked = revoke_review_delegation(
            grant.delegation_id,
            self.owner.user_id,
            reason="The independent review request is no longer active.",
        )
        self.assertIsNotNone(revoked.revoked_at)
        with self.assertRaisesRegex(ReviewDelegationError, "already revoked"):
            revoke_review_delegation(
                grant.delegation_id,
                self.owner.user_id,
                reason="A repeated revocation attempt must be rejected.",
            )
        self.assertEqual(PatientReviewDelegation.query.count(), 1)

