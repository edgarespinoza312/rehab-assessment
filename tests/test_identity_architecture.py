from datetime import datetime
import unittest

from flask import Flask
from sqlalchemy.exc import IntegrityError

from dashboard.database import db
from dashboard.models import Patient, Role, User
from dashboard.services.identity import (
    ApplicationRole,
    Capability,
    IdentityContext,
    UserStatus,
    anonymous_identity,
    can,
    identity_from_user,
    trusted_development_identity,
)


class IdentityArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(f"identity-{id(self)}")
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI="sqlite://",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_seed_roles_and_user_patient_independence(self):
        patient = Patient(first_name="Patient", last_name="Only")
        user = User(display_name="Clinician Only", status="ACTIVE")
        db.session.add_all([patient, user])
        db.session.commit()
        self.assertIsNone(patient.user)
        self.assertIsNone(user.patient)

        linked = User(
            display_name="Patient User",
            status="ACTIVE",
            patient=patient,
        )
        db.session.add(linked)
        db.session.commit()
        self.assertIs(patient.user, linked)
        self.assertIs(linked.patient, patient)

    def test_status_and_normalized_multiple_roles(self):
        user = User(display_name="Multi-role", status="ACTIVE")
        user.roles = [
            Role(name="PATIENT"),
            Role(name="OPERATOR"),
        ]
        db.session.add(user)
        db.session.commit()
        context = identity_from_user(user)
        self.assertEqual(
            context.roles,
            frozenset({ApplicationRole.PATIENT, ApplicationRole.OPERATOR}),
        )
        user.status = "DISABLED"
        db.session.commit()
        self.assertEqual(identity_from_user(user).status, UserStatus.DISABLED)

        invalid = Role(name="INVALID")
        db.session.add(invalid)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_identity_context_and_authorization_boundary(self):
        anonymous = anonymous_identity()
        self.assertFalse(can(
            anonymous,
            Capability.VIEW_PATIENT_PROGRESSION,
            patient_id=1,
        ))
        patient = trusted_development_identity(
            1,
            roles={ApplicationRole.PATIENT},
            patient_id=7,
        )
        self.assertTrue(can(
            patient,
            Capability.VIEW_OWN_PATIENT_DATA,
            patient_id=7,
        ))
        self.assertFalse(can(
            patient,
            Capability.VIEW_OWN_PATIENT_DATA,
            patient_id=8,
        ))
        clinician = trusted_development_identity(
            2,
            roles={ApplicationRole.CLINICIAN},
        )
        self.assertTrue(can(
            clinician,
            Capability.REVIEW_ADVISORY,
            patient_id=8,
        ))
        operator = trusted_development_identity(
            3,
            roles={ApplicationRole.OPERATOR},
        )
        self.assertFalse(can(
            operator,
            Capability.REVIEW_ADVISORY,
            patient_id=8,
        ))
        disabled = IdentityContext(
            user_id=4,
            roles=frozenset({ApplicationRole.CLINICIAN}),
            trust_state="trusted-development",
            status=UserStatus.DISABLED,
        )
        self.assertFalse(can(
            disabled,
            Capability.VIEW_ADVISORY,
            patient_id=8,
        ))

    def test_client_role_payload_is_not_an_identity_constructor(self):
        self.assertFalse(can(
            anonymous_identity(),
            Capability.REVIEW_ADVISORY,
            patient_id=1,
        ))


if __name__ == "__main__":
    unittest.main()
