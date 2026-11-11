import unittest

from dashboard.app import app
from dashboard.database import db
from dashboard.models import Patient, PatientAssignment, Role, User
from dashboard.services.authentication import hash_password


class PatientAssignmentWorkflowTests(unittest.TestCase):
    def setUp(self):
        # Exercise engineering workflows explicitly; production configuration forbids this opt-in.
        app.config["REVALIV_ENABLE_UNVALIDATED_EXERCISES"] = True
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
            roles=[clinician_role],
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


    def test_progression_and_advisory_apis_enforce_active_assignment(self):
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

        protected_endpoints = [
            f"/api/patients/{self.patient_id}/progression",
            f"/api/patients/{self.patient_id}/progression/context",
            f"/api/patients/{self.patient_id}/progression/advisory",
            f"/api/patients/{self.patient_id}/progression/advisory/reviews",
        ]

        unassigned_clinician = app.test_client()
        self.login(unassigned_clinician, "clinician2@workflow.test")
        for endpoint in protected_endpoints:
            with self.subTest(endpoint=endpoint):
                response = unassigned_clinician.get(endpoint)
                self.assertEqual(response.status_code, 403)

        assigned_clinician = app.test_client()
        self.login(assigned_clinician, "clinician1@workflow.test")
        expected_statuses = [200, 200, 200, 400]
        for endpoint, expected_status in zip(
            protected_endpoints, expected_statuses
        ):
            with self.subTest(endpoint=endpoint):
                response = assigned_clinician.get(endpoint)
                self.assertEqual(response.status_code, expected_status)

        self.assertEqual(
            PatientAssignment.query.filter_by(
                patient_id=self.patient_id,
                ended_at=None,
            ).count(),
            1,
        )


    def test_assessment_report_and_deletion_are_assignment_scoped(self):
        from dashboard.models import AssessmentRecord

        assessment = AssessmentRecord(
            patient_id=self.patient_id,
            exercise="Shoulder flexion",
            repetitions=5,
            average_score=82.0,
            best_score=90.0,
            worst_score=70.0,
            trend="stable",
            feedback="[]",
        )
        db.session.add(assessment)
        db.session.commit()
        assessment_id = assessment.assessment_id

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

        assigned = app.test_client()
        self.login(assigned, "clinician1@workflow.test")
        unassigned = app.test_client()
        self.login(unassigned, "clinician2@workflow.test")

        self.assertEqual(
            assigned.get(f"/assessment/{assessment_id}").status_code,
            200,
        )
        self.assertEqual(
            unassigned.get(f"/assessment/{assessment_id}").status_code,
            404,
        )

        denied_delete = unassigned.post(
            f"/assessment/{assessment_id}/delete",
            data={"csrf_token": self.csrf(unassigned)},
        )
        self.assertEqual(denied_delete.status_code, 403)
        self.assertIsNotNone(db.session.get(AssessmentRecord, assessment_id))

        allowed_delete = assigned.post(
            f"/assessment/{assessment_id}/delete",
            data={"csrf_token": self.csrf(assigned)},
        )
        self.assertEqual(allowed_delete.status_code, 302)
        self.assertIsNone(db.session.get(AssessmentRecord, assessment_id))


    def test_workout_plan_builder_and_creation_are_assignment_scoped(self):
        from dashboard.models import WorkoutPlan

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

        assigned = app.test_client()
        self.login(assigned, "clinician1@workflow.test")
        unassigned = app.test_client()
        self.login(unassigned, "clinician2@workflow.test")

        self.assertEqual(
            assigned.get(
                f"/workout/builder?patient_id={self.patient_id}"
            ).status_code,
            200,
        )
        self.assertEqual(
            unassigned.get(
                f"/workout/builder?patient_id={self.patient_id}"
            ).status_code,
            403,
        )

        payload = {
            "name": "Unauthorized plan attempt",
            "description": "Must not be saved",
            "patient_id": self.patient_id,
            "exercises": [],
        }
        denied = unassigned.post(
            "/workout/plans",
            json=payload,
            headers={"X-CSRF-Token": self.csrf(unassigned)},
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(
            WorkoutPlan.query.filter_by(patient_id=self.patient_id).count(),
            0,
        )

        assigned_response = assigned.post(
            "/workout/plans",
            json=payload,
            headers={"X-CSRF-Token": self.csrf(assigned)},
        )
        self.assertEqual(assigned_response.status_code, 400)
        self.assertEqual(
            WorkoutPlan.query.filter_by(patient_id=self.patient_id).count(),
            0,
        )


    def test_unassigned_clinician_cannot_delete_patient_record(self):
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

        unassigned = app.test_client()
        self.login(unassigned, "clinician2@workflow.test")
        response = unassigned.post(
            f"/patients/{self.patient_id}/delete",
            data={"csrf_token": self.csrf(unassigned)},
        )
        self.assertEqual(response.status_code, 403)
        self.assertIsNotNone(db.session.get(Patient, self.patient_id))
        self.assertEqual(
            PatientAssignment.query.filter_by(
                patient_id=self.patient_id,
                ended_at=None,
            ).count(),
            1,
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


    def test_assessment_notes_mutation_requires_active_assignment(self):
        from dashboard.models import AssessmentRecord

        assessment = AssessmentRecord(
            patient_id=self.patient_id,
            exercise="Shoulder flexion",
            repetitions=5,
            average_score=82.0,
            best_score=90.0,
            worst_score=70.0,
            trend="stable",
            feedback="[]",
            notes="Original clinical note",
        )
        db.session.add(assessment)
        db.session.commit()
        assessment_id = assessment.assessment_id

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

        assigned = app.test_client()
        self.login(assigned, "clinician1@workflow.test")
        unassigned = app.test_client()
        self.login(unassigned, "clinician2@workflow.test")

        denied = unassigned.post(
            f"/assessment/{assessment_id}/notes",
            data={
                "csrf_token": self.csrf(unassigned),
                "notes": "Attempted change by unassigned clinician",
            },
        )
        self.assertEqual(denied.status_code, 404)
        db.session.refresh(assessment)
        self.assertEqual(assessment.notes, "Original clinical note")

        allowed = assigned.post(
            f"/assessment/{assessment_id}/notes",
            data={
                "csrf_token": self.csrf(assigned),
                "notes": "Authorized update",
            },
        )
        self.assertEqual(allowed.status_code, 302)
        db.session.refresh(assessment)
        self.assertEqual(assessment.notes, "Authorized update")


    def test_unassigned_clinician_cannot_start_patient_specific_workout_plan(self):
        from dashboard.models import WorkoutPlan
        from core.workout import WorkoutPrescription
        from dashboard.services.workout_persistence import create_workout_plan

        plan = create_workout_plan(
            "Assigned patient plan",
            (WorkoutPrescription("bicep_curl", "left", 4),),
            patient_id=self.patient_id,
        )

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

        unassigned = app.test_client()
        self.login(unassigned, "clinician2@workflow.test")
        response = unassigned.post(
            "/workout/start",
            json={"plan_id": plan.plan_id, "patient_id": self.patient_id},
            headers={"X-CSRF-Token": self.csrf(unassigned)},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(WorkoutPlan.query.filter_by(patient_id=self.patient_id).count(), 1)


    def test_patient_specific_workout_plan_listing_is_assignment_scoped(self):
        from core.workout import WorkoutPrescription
        from dashboard.services.workout_persistence import create_workout_plan

        create_workout_plan(
            "Confidential patient plan",
            (WorkoutPrescription("bicep_curl", "left", 4),),
            patient_id=self.patient_id,
        )

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

        assigned = app.test_client()
        self.login(assigned, "clinician1@workflow.test")
        response = assigned.get(f"/selection?patient_id={self.patient_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Confidential patient plan", response.get_data(as_text=True))

        unassigned = app.test_client()
        self.login(unassigned, "clinician2@workflow.test")
        response = unassigned.get(f"/selection?patient_id={self.patient_id}")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("Confidential patient plan", response.get_data(as_text=True))


    def test_active_workout_access_is_revoked_when_patient_assignment_ends(self):
        from core.workout import WorkoutPrescription
        from dashboard.services.workout_persistence import create_workout_plan, review_workout_plan

        plan = create_workout_plan(
            "Runtime revocation plan",
            (WorkoutPrescription("bicep_curl", "left", 4),),
            patient_id=self.patient_id,
            created_by_user_id=self.clinician_two_id,
        )
        review_workout_plan(
            plan.plan_id,
            self.clinician_one_id,
            "approve",
            "Independent approval for assignment access regression test.",
        )

        admin = app.test_client()
        self.login(admin, "admin@workflow.test")
        assigned = app.test_client()
        self.login(assigned, "clinician1@workflow.test")

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

        started = assigned.post(
            "/workout/start",
            json={"plan_id": plan.plan_id, "patient_id": self.patient_id},
            headers={"X-CSRF-Token": self.csrf(assigned)},
        )
        self.assertEqual(started.status_code, 201)

        revoked = admin.post(
            f"/patients/{self.patient_id}/assignment",
            data={
                "csrf_token": self.csrf(admin),
                "action": "revoke",
                "reason": "Care ended during workout",
                "filter": "all",
            },
        )
        self.assertEqual(revoked.status_code, 302)

        for endpoint in ("/workout/session", "/video_status", "/video_feed"):
            with self.subTest(endpoint=endpoint):
                response = assigned.get(endpoint)
                self.assertEqual(response.status_code, 403)

        cancel = assigned.post(
            "/workout/cancel",
            json={},
            headers={"X-CSRF-Token": self.csrf(assigned)},
        )
        self.assertEqual(cancel.status_code, 403)


    def test_active_workout_access_is_revoked_after_assignment_transfer(self):
        from core.workout import WorkoutPrescription
        from dashboard.services.workout_persistence import create_workout_plan, review_workout_plan

        plan = create_workout_plan(
            "Assignment transfer runtime plan",
            (WorkoutPrescription("bicep_curl", "left", 4),),
            patient_id=self.patient_id,
            created_by_user_id=self.clinician_two_id,
        )
        review_workout_plan(
            plan.plan_id,
            self.clinician_one_id,
            "approve",
            "Independent approval for assignment access regression test.",
        )

        admin = app.test_client()
        self.login(admin, "admin@workflow.test")
        first_clinician = app.test_client()
        self.login(first_clinician, "clinician1@workflow.test")
        second_clinician = app.test_client()
        self.login(second_clinician, "clinician2@workflow.test")

        assigned_first = admin.post(
            f"/patients/{self.patient_id}/assignment",
            data={
                "csrf_token": self.csrf(admin),
                "action": "assign",
                "clinician_user_id": str(self.clinician_one_id),
                "filter": "all",
            },
        )
        self.assertEqual(assigned_first.status_code, 302)

        started = first_clinician.post(
            "/workout/start",
            json={"plan_id": plan.plan_id, "patient_id": self.patient_id},
            headers={"X-CSRF-Token": self.csrf(first_clinician)},
        )
        self.assertEqual(started.status_code, 201)

        transferred = admin.post(
            f"/patients/{self.patient_id}/assignment",
            data={
                "csrf_token": self.csrf(admin),
                "action": "assign",
                "clinician_user_id": str(self.clinician_two_id),
                "reason": "Coverage transfer during workout",
                "filter": "all",
            },
        )
        self.assertEqual(transferred.status_code, 302)

        for endpoint in ("/workout/session", "/video_status", "/video_feed"):
            with self.subTest(endpoint=endpoint):
                response = first_clinician.get(endpoint)
                self.assertEqual(response.status_code, 403)

        cancel = first_clinician.post(
            "/workout/cancel",
            json={},
            headers={"X-CSRF-Token": self.csrf(first_clinician)},
        )
        self.assertEqual(cancel.status_code, 403)

        # The newly assigned clinician can start a separate authorized session.
        second_started = second_clinician.post(
            "/workout/start",
            json={"plan_id": plan.plan_id, "patient_id": self.patient_id},
            headers={"X-CSRF-Token": self.csrf(second_clinician)},
        )
        self.assertEqual(second_started.status_code, 201)


if __name__ == "__main__":
    unittest.main()
