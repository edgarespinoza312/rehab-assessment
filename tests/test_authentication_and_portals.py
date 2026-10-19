import unittest

from dashboard.app import app
from dashboard.database import db
from dashboard.models import AssessmentRecord, Patient, Role, User
from dashboard.services.authentication import hash_password


class AuthenticationAndPortalTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        db.session.rollback()
        db.drop_all()
        db.create_all()
        patient = Patient(patient_id=1, first_name="Pat", last_name="User")
        other_patient = Patient(patient_id=2, first_name="Other", last_name="Patient")
        clinician = User(
            display_name="Clinician",
            email="clinician@example.test",
            password_hash=hash_password("correct horse"),
        )
        clinician.roles = [Role(name="CLINICIAN")]
        patient_user = User(
            display_name="Patient",
            email="patient@example.test",
            password_hash=hash_password("correct horse"),
            patient=patient,
        )
        patient_user.roles = [Role(name="PATIENT")]
        operator = User(
            display_name="Operator",
            email="operator@example.test",
            password_hash=hash_password("correct horse"),
        )
        operator.roles = [Role(name="OPERATOR")]
        admin = User(
            display_name="Admin",
            email="admin@example.test",
            password_hash=hash_password("correct horse"),
        )
        admin.roles = [Role(name="ADMIN")]
        db.session.add_all([patient, other_patient, clinician, patient_user, operator, admin])
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

    def _login(self, email, role):
        token = self._csrf()
        response = self.client.post("/login", data={
            "csrf_token": token,
            "email": email,
            "password": "correct horse",
            "role": role,
        })
        self.assertEqual(response.status_code, 302)
        return response

    def test_missing_csrf_secret_rejects_empty_token(self):
        self._login("patient@example.test", "PATIENT")
        with self.client.session_transaction() as session:
            session.pop("revaliv_csrf_token", None)

        response = self.client.post(
            "/logout",
            headers={"X-CSRF-Token": ""},
        )

        self.assertEqual(response.status_code, 400)
        # Failed CSRF validation must not perform the state-changing action.
        self.assertEqual(self.client.get("/patient").status_code, 200)

    def test_login_role_selection_cannot_elevate(self):
        token = self._csrf()
        response = self.client.post("/login", data={
            "csrf_token": token,
            "email": "patient@example.test",
            "password": "correct horse",
            "role": "CLINICIAN",
        })
        self.assertEqual(response.status_code, 403)

    def test_patient_portal_uses_linked_patient_and_logout(self):
        token = self._csrf()
        response = self.client.post("/login", data={
            "csrf_token": token,
            "email": "patient@example.test",
            "password": "correct horse",
            "role": "PATIENT",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/patient").status_code, 200)
        logout_token = self._csrf()
        self.assertEqual(
            self.client.post("/logout", data={"csrf_token": logout_token}).status_code,
            302,
        )
        self.assertEqual(self.client.get("/patient").status_code, 302)

    def test_disabled_user_session_is_rejected(self):
        token = self._csrf()
        self.client.post("/login", data={
            "csrf_token": token,
            "email": "clinician@example.test",
            "password": "correct horse",
            "role": "CLINICIAN",
        })
        user = User.query.filter_by(email="clinician@example.test").one()
        user.status = "DISABLED"
        db.session.commit()
        self.assertEqual(self.client.get("/clinician").status_code, 302)

    def test_anonymous_and_patient_cannot_enter_clinician_or_other_patient(self):
        self.assertEqual(self.client.get("/patient").status_code, 302)
        self.assertEqual(self.client.get("/clinician").status_code, 302)
        token = self._csrf()
        self.client.post("/login", data={
            "csrf_token": token,
            "email": "patient@example.test",
            "password": "correct horse",
            "role": "PATIENT",
        })
        self.assertEqual(self.client.get("/clinician").status_code, 403)
        self.assertEqual(self.client.get("/patients/2").status_code, 403)

    def test_historical_notes_editor_is_only_shown_to_clinicians(self):
        record = AssessmentRecord(
            assessment_id=1,
            patient_id=1,
            exercise="Left Bicep Curl",
            repetitions=1,
            average_score=50.0,
            best_score=60.0,
            worst_score=40.0,
            feedback="[]",
        )
        db.session.add(record)
        db.session.commit()

        self._login("patient@example.test", "PATIENT")
        patient_view = self.client.get("/assessment/1")
        self.assertEqual(patient_view.status_code, 200)
        patient_html = patient_view.get_data(as_text=True)
        self.assertNotIn("Save Notes", patient_html)
        self.assertNotIn("Enter additional observations", patient_html)

        self.client.post("/logout", data={"csrf_token": self._csrf()})
        self._login("clinician@example.test", "CLINICIAN")
        clinician_view = self.client.get("/assessment/1")
        self.assertEqual(clinician_view.status_code, 200)
        clinician_html = clinician_view.get_data(as_text=True)
        self.assertIn("Save Notes", clinician_html)
        self.assertIn("Enter additional observations", clinician_html)

    def test_assessment_notes_reject_missing_or_overlong_input(self):
        record = AssessmentRecord(
            assessment_id=1,
            patient_id=1,
            exercise="Left Bicep Curl",
            repetitions=1,
            average_score=50.0,
            best_score=60.0,
            worst_score=40.0,
            feedback="[]",
            notes="Original note",
        )
        db.session.add(record)
        db.session.commit()
        self._login("clinician@example.test", "CLINICIAN")

        invalid_updates = [
            ("missing notes", {}),
            ("overlong notes", {"notes": "N" * 10001}),
        ]
        for case, fields in invalid_updates:
            with self.subTest(case=case):
                payload = dict(fields)
                payload["csrf_token"] = self._csrf()
                response = self.client.post("/assessment/1/notes", data=payload)
                self.assertEqual(response.status_code, 400)

        db.session.refresh(record)
        self.assertEqual(record.notes, "Original note")

    def test_patient_cannot_infer_other_assessment_ids_from_status_codes(self):
        record = AssessmentRecord(
            assessment_id=1,
            patient_id=2,
            exercise="Left Bicep Curl",
            repetitions=1,
            average_score=50.0,
            best_score=60.0,
            worst_score=40.0,
            feedback="[]",
        )
        db.session.add(record)
        db.session.commit()
        self._login("patient@example.test", "PATIENT")

        existing = self.client.get("/assessment/1")
        missing = self.client.get("/assessment/999")
        self.assertEqual(existing.status_code, 404)
        self.assertEqual(missing.status_code, 404)

        notes_token = self._csrf()
        update = self.client.post(
            "/assessment/1/notes",
            data={"csrf_token": notes_token, "notes": "Unauthorized"},
        )
        self.assertEqual(update.status_code, 404)
        db.session.refresh(record)
        self.assertIsNone(record.notes)

    def test_anonymous_legacy_routes_and_apis_are_denied(self):
        self.assertEqual(self.client.get("/selection").status_code, 302)
        self.assertEqual(self.client.get("/workout/builder").status_code, 302)
        self.assertEqual(self.client.post("/workout/plans", json={}).status_code, 401)
        self.assertEqual(
            self.client.get("/api/patients/1/progression").status_code,
            401,
        )
        self.assertEqual(
            self.client.get("/api/patients/1/progression/context").status_code,
            401,
        )
        self.assertEqual(
            self.client.get("/api/patients/1/progression/advisory").status_code,
            401,
        )
        self.assertEqual(
            self.client.get(
                "/api/patients/1/progression/advisory/reviews"
                "?exercise_id=bicep_curl"
            ).status_code,
            401,
        )

    def test_patient_legacy_workflow_is_owned_and_clinician_data_is_hidden(self):
        self._login("patient@example.test", "PATIENT")
        selection = self.client.get("/selection?patient_id=2")
        self.assertEqual(selection.status_code, 200)
        selection_html = selection.get_data(as_text=True)
        self.assertIn('name="patient_id"', selection_html)
        self.assertIn('value="1"', selection_html)
        self.assertNotIn("Patient, Other", selection_html)
        builder = self.client.get("/workout/builder?patient_id=2")
        self.assertEqual(builder.status_code, 200)
        self.assertNotIn("Other Patient", builder.get_data(as_text=True))
        own_plan = self.client.post("/workout/plans", json={
            "name": "My plan",
            "patient_id": 1,
            "exercises": [{"position": 0, "exercise_id": "bicep_curl",
                           "side": "left", "target_repetitions": 1}],
        }, headers={"X-CSRF-Token": self._csrf()})
        self.assertEqual(own_plan.status_code, 201)
        spoof = self.client.post("/workout/plans", json={
            "name": "Spoof",
            "patient_id": 2,
            "exercises": [{"position": 0, "exercise_id": "bicep_curl",
                           "side": "left", "target_repetitions": 1}],
        }, headers={"X-CSRF-Token": self._csrf()})
        self.assertEqual(spoof.status_code, 403)
        self.assertEqual(self.client.get("/api/patients/1/progression").status_code, 200)
        self.assertEqual(self.client.get("/api/patients/2/progression").status_code, 403)
        self.assertEqual(
            self.client.get("/api/patients/1/progression/advisory").status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                "/api/patients/1/progression/advisory/reviews"
                "?exercise_id=bicep_curl"
            ).status_code,
            403,
        )

    def test_operator_has_safe_fallback_and_no_patient_workspace_capabilities(self):
        response = self._login("operator@example.test", "OPERATOR")
        self.assertEqual(response.location, "/access-unavailable")
        fallback = self.client.get(response.location)
        self.assertEqual(fallback.status_code, 200)
        self.assertIn("No workspace available", fallback.get_data(as_text=True))
        self.assertEqual(self.client.get("/clinician").status_code, 403)
        self.assertEqual(self.client.get("/workout/builder").status_code, 403)
        self.assertEqual(self.client.get("/selection").status_code, 403)
        self.assertEqual(self.client.get("/patient").status_code, 403)
        denied = self.client.post("/workout/plans", json={
            "name": "Operator plan",
            "patient_id": 1,
            "exercises": [{"position": 0, "exercise_id": "bicep_curl",
                           "side": "left", "target_repetitions": 5}],
        }, headers={"X-CSRF-Token": self._csrf()})
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(
            self.client.get("/api/patients/1/progression/advisory").status_code,
            403,
        )

    def test_admin_cannot_use_clinician_or_workout_builder_capabilities(self):
        self._login("admin@example.test", "ADMIN")
        self.assertEqual(self.client.get("/clinician").status_code, 403)
        self.assertEqual(self.client.get("/workout/builder").status_code, 403)
        self.assertEqual(self.client.get("/selection").status_code, 403)
        self.assertEqual(self.client.get("/patient").status_code, 403)
        denied = self.client.post("/workout/plans", json={
            "name": "Admin plan without clinician role",
            "patient_id": 1,
            "exercises": [{"position": 0, "exercise_id": "bicep_curl",
                           "side": "left", "target_repetitions": 5}],
        }, headers={"X-CSRF-Token": self._csrf()})
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(self.client.get("/api/patients/1/progression").status_code, 403)

    def test_admin_and_operator_cannot_open_assessment_camera_workflow(self):
        for email in ("admin@example.test", "operator@example.test"):
            with self.subTest(email=email):
                self.client = app.test_client()
                self._login(email, email.split("@")[0].upper())
                response = self.client.get("/assessment")
                self.assertEqual(response.status_code, 403)
                # Denying the page must not create a runtime that exposes video.
                self.assertEqual(self.client.get("/video_feed").status_code, 404)
                self.assertEqual(self.client.get("/video_status").status_code, 404)

    def test_camera_stream_requires_patient_linked_runtime_session(self):
        self._login("clinician@example.test", "CLINICIAN")
        # A direct page visit must not allocate an empty runtime or expose video.
        self.assertEqual(
            self.client.get("/assessment?patient_id=1").status_code,
            404,
        )
        self.assertEqual(self.client.get("/video_feed").status_code, 404)
        self.assertEqual(self.client.get("/video_status").status_code, 404)

    def test_finished_legacy_assessment_no_longer_exposes_camera_endpoints(self):
        self._login("clinician@example.test", "CLINICIAN")
        token = self._csrf()
        started = self.client.post(
            "/assessment",
            data={
                "csrf_token": token,
                "exercise": "LEFT_BICEP_CURL",
                "patient_id": 1,
            },
        )
        self.assertEqual(started.status_code, 302)

        finished = self.client.post(
            "/finish",
            data={"csrf_token": self._csrf()},
        )
        self.assertEqual(finished.status_code, 302)
        self.assertEqual(self.client.get("/video_feed").status_code, 404)
        self.assertEqual(self.client.get("/video_status").status_code, 404)

    def test_cancelled_workout_no_longer_exposes_camera_endpoints(self):
        self._login("clinician@example.test", "CLINICIAN")
        started = self.client.post(
            "/workout/start",
            json={"preset_id": "bilateral_bicep_curl_2", "patient_id": 1},
            headers={"X-CSRF-Token": self._csrf()},
        )
        self.assertEqual(started.status_code, 201)

        cancelled = self.client.post(
            "/workout/cancel",
            headers={"X-CSRF-Token": self._csrf()},
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(self.client.get("/video_feed").status_code, 404)
        self.assertEqual(self.client.get("/video_status").status_code, 404)

    def test_unknown_exercise_requests_return_client_errors(self):
        self._login("clinician@example.test", "CLINICIAN")

        unknown_info = self.client.get("/exercise_info/NOT_A_REAL_EXERCISE")
        self.assertEqual(unknown_info.status_code, 404)

        unknown_start = self.client.post(
            "/assessment",
            data={
                "csrf_token": self._csrf(),
                "exercise": "NOT_A_REAL_EXERCISE",
                "patient_id": 1,
            },
        )
        self.assertEqual(unknown_start.status_code, 400)

    def test_new_patient_rejects_invalid_fields_without_creating_records(self):
        self._login("clinician@example.test", "CLINICIAN")
        initial_count = Patient.query.count()
        valid_form = {
            "first_name": "New",
            "last_name": "Patient",
            "date_of_birth": "2000-01-02",
            "sex": "Other",
            "diagnosis": "Test diagnosis",
            "affected_side": "Left",
            "therapist_notes": "",
        }
        invalid_forms = [
            ("missing required field", {**valid_form, "first_name": ""}),
            ("invalid date", {**valid_form, "date_of_birth": "not-a-date"}),
            ("future date", {**valid_form, "date_of_birth": "2999-01-01"}),
            ("invalid sex", {**valid_form, "sex": "unknown"}),
            ("invalid affected side", {**valid_form, "affected_side": "center"}),
            ("overlong name", {**valid_form, "first_name": "N" * 51}),
            ("overlong diagnosis", {**valid_form, "diagnosis": "D" * 151}),
            ("overlong notes", {**valid_form, "therapist_notes": "N" * 10001}),
        ]
        for case, form in invalid_forms:
            with self.subTest(case=case):
                payload = dict(form)
                payload["csrf_token"] = self._csrf()
                response = self.client.post("/patients/new", data=payload)
                self.assertEqual(response.status_code, 400)

        self.assertEqual(Patient.query.count(), initial_count)

    def test_clinician_can_create_patient_with_valid_form(self):
        self._login("clinician@example.test", "CLINICIAN")
        response = self.client.post(
            "/patients/new",
            data={
                "csrf_token": self._csrf(),
                "first_name": "New",
                "last_name": "Patient",
                "date_of_birth": "2000-01-02",
                "sex": "Other",
                "diagnosis": "Test diagnosis",
                "affected_side": "Left",
                "therapist_notes": "Initial note",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Patient.query.count(), 3)
        patient = Patient.query.filter_by(first_name="New", last_name="Patient").one()
        self.assertEqual(patient.therapist_notes, "Initial note")

    def test_destructive_actions_require_explicit_clinician_delete_capabilities(self):
        record = AssessmentRecord(
            assessment_id=1,
            patient_id=1,
            exercise="Left Bicep Curl",
            repetitions=1,
            average_score=50.0,
            best_score=60.0,
            worst_score=40.0,
            feedback="[]",
        )
        db.session.add(record)
        db.session.commit()

        for email, role in (
            ("patient@example.test", "PATIENT"),
            ("admin@example.test", "ADMIN"),
            ("operator@example.test", "OPERATOR"),
        ):
            with self.subTest(email=email):
                self._login(email, role)
                headers = {"X-CSRF-Token": self._csrf()}
                assessment_response = self.client.post(
                    "/assessment/1/delete",
                    headers=headers,
                )
                patient_response = self.client.post(
                    "/patients/2/delete",
                    headers=headers,
                )
                self.assertEqual(assessment_response.status_code, 403)
                self.assertEqual(patient_response.status_code, 403)
                self.assertIsNotNone(db.session.get(AssessmentRecord, 1))
                self.assertIsNotNone(db.session.get(Patient, 2))
                self.client.post("/logout", data={"csrf_token": self._csrf()})

        self._login("clinician@example.test", "CLINICIAN")
        clinician_headers = {"X-CSRF-Token": self._csrf()}
        deleted_assessment = self.client.post(
            "/assessment/1/delete",
            headers=clinician_headers,
        )
        self.assertEqual(deleted_assessment.status_code, 302)
        self.assertIsNone(db.session.get(AssessmentRecord, 1))

        deleted_patient = self.client.post(
            "/patients/2/delete",
            headers={"X-CSRF-Token": self._csrf()},
        )
        self.assertEqual(deleted_patient.status_code, 302)
        self.assertIsNone(db.session.get(Patient, 2))

    def test_clinician_patient_profile_alias_reaches_protected_profile(self):
        self._login("clinician@example.test", "CLINICIAN")
        response = self.client.get(
            "/clinician/patients/1",
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Pat", response.get_data(as_text=True))
        self.assertIn("User", response.get_data(as_text=True))

    def test_clinician_can_build_and_create_patient_workout_plan(self):
        self._login("clinician@example.test", "CLINICIAN")
        self.assertEqual(self.client.get("/workout/builder?patient_id=1").status_code, 200)
        selection = self.client.get("/selection?patient_id=1")
        self.assertEqual(selection.status_code, 200)
        selection_html = selection.get_data(as_text=True)
        self.assertIn("User, Pat", selection_html)
        self.assertIn("Patient, Other", selection_html)
        self.assertRegex(selection_html, r'<option value="1"\s+selected>')
        response = self.client.post("/workout/plans", json={
            "name": "Clinician plan",
            "patient_id": 1,
            "exercises": [{"position": 0, "exercise_id": "bicep_curl",
                           "side": "left", "target_repetitions": 5}],
        }, headers={"X-CSRF-Token": self._csrf()})
        self.assertEqual(response.status_code, 201)


if __name__ == "__main__":
    unittest.main()
