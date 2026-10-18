import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from dashboard.app import (
    app,
    runtime_registry,
    video_consumer_guard,
    vision,
    _generate_frames,
    _expire_idle_runtime_contexts,
    _release_runtime_context,
)
from dashboard.database import db
from dashboard.models import AssessmentRecord, Patient, Role, User, WorkoutPlan
from dashboard.runtime_context import RuntimeLifecycle
from core.models import AssessmentResult
from dashboard.services.authentication import RUNTIME_SESSION_KEY, hash_password
from dashboard.services.user_provisioning import create_user, disable_user


class Phase7RuntimeIsolationTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        db.session.rollback()
        db.drop_all()
        db.create_all()
        db.session.add_all([
            Role(name="PATIENT"),
            Role(name="CLINICIAN"),
            Patient(patient_id=1, first_name="A", last_name="Patient"),
            Patient(patient_id=2, first_name="B", last_name="Patient"),
        ])
        db.session.commit()
        self.a = create_user(
            display_name="A", email="a@example.test",
            password="password-a", role="PATIENT", patient_id=1,
        )
        self.b = create_user(
            display_name="B", email="b@example.test",
            password="password-b", role="PATIENT", patient_id=2,
        )

    def tearDown(self):
        db.session.rollback()
        db.drop_all()
        db.create_all()
        self.context.pop()

    def _login(self, client, email, password, role="PATIENT"):
        client.get("/login")
        with client.session_transaction() as state:
            token = state["revaliv_csrf_token"]
        response = client.post("/login", data={
            "csrf_token": token,
            "email": email,
            "password": password,
            "role": role,
        })
        self.assertEqual(response.status_code, 302)

    def _start_assessment(self, client, patient_id):
        with client.session_transaction() as state:
            token = state["revaliv_csrf_token"]
        response = client.post("/assessment", data={
            "csrf_token": token,
            "exercise": "LEFT_BICEP_CURL",
            "patient_id": patient_id,
        })
        self.assertEqual(response.status_code, 302)

    def test_unavailable_camera_returns_503_and_releases_video_lease(self):
        client = app.test_client()
        self._login(client, "a@example.test", "password-a")
        self._start_assessment(client, 1)

        with patch.object(vision, "camera", None), patch.object(
            vision, "start", side_effect=RuntimeError("camera unavailable")
        ):
            response = client.get("/video_feed")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), {"error": "camera unavailable"})
        self.assertFalse(video_consumer_guard.active)
        self.assertEqual(client.get("/patient").status_code, 200)

    def test_workout_api_rejects_excessive_repetition_target(self):
        client = app.test_client()
        self._login(client, "a@example.test", "password-a")
        with client.session_transaction() as state:
            csrf = state["revaliv_csrf_token"]

        response = client.post(
            "/workout/plans",
            json={
                "name": "Excessive reps",
                "description": "",
                "patient_id": 1,
                "exercises": [{
                    "position": 0,
                    "exercise_id": "bicep_curl",
                    "side": "left",
                    "target_repetitions": 1001,
                    "resistance_value": None,
                    "resistance_unit": None,
                    "resistance_type": None,
                }],
            },
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("target_repetitions", response.get_json()["error"])
        self.assertEqual(WorkoutPlan.query.count(), 0)

    def test_assessment_save_rejects_concurrent_duplicate_submission(self):
        client = app.test_client()
        self._login(client, "a@example.test", "password-a")
        self._start_assessment(client, 1)
        with client.session_transaction() as state:
            runtime_id = state[RUNTIME_SESSION_KEY]
            csrf = state["revaliv_csrf_token"]

        context = runtime_registry.get(runtime_id)
        self.assertIsNotNone(context)
        with context.lock:
            context.completed_session = {
                "patient_id": 1,
                "exercise": "Left Bicep Curl",
                "repetitions": 3,
                "average_score": 80.0,
                "best_score": 90.0,
                "worst_score": 70.0,
                "trend": "stable",
                "feedback": [],
            }
            context.save_in_progress = True

        initial_count = AssessmentRecord.query.count()
        try:
            response = client.post(
                "/save_assessment",
                data={"csrf_token": csrf},
            )
            self.assertEqual(response.status_code, 409)
            self.assertEqual(
                response.get_json(),
                {"error": "assessment save already in progress"},
            )
            self.assertEqual(AssessmentRecord.query.count(), initial_count)

            finish_response = client.post(
                "/finish",
                data={"csrf_token": csrf},
            )
            self.assertEqual(finish_response.status_code, 409)

            discard_response = client.post(
                "/discard",
                data={"csrf_token": csrf},
            )
            self.assertEqual(discard_response.status_code, 409)
            self.assertIsNotNone(context.completed_session)
        finally:
            with context.lock:
                context.save_in_progress = False
            _release_runtime_context(runtime_id)

    def test_two_users_receive_independent_owned_runtimes(self):
        client_a = app.test_client()
        client_b = app.test_client()
        self._login(client_a, "a@example.test", "password-a")
        self._login(client_b, "b@example.test", "password-b")
        self._start_assessment(client_a, 1)
        self._start_assessment(client_b, 2)

        with client_a.session_transaction() as state_a:
            runtime_a = state_a[RUNTIME_SESSION_KEY]
        with client_b.session_transaction() as state_b:
            runtime_b = state_b[RUNTIME_SESSION_KEY]
        self.assertNotEqual(runtime_a, runtime_b)

        context_a = runtime_registry.get(runtime_a)
        context_b = runtime_registry.get(runtime_b)
        self.assertEqual(context_a.user_id, self.a.user_id)
        self.assertEqual(context_b.user_id, self.b.user_id)
        self.assertEqual(context_a.patient_id, 1)
        self.assertEqual(context_b.patient_id, 2)

        context_a.transition(RuntimeLifecycle.ACTIVE)
        context_b.transition(RuntimeLifecycle.ACTIVE)
        original_b_session = context_b.session
        context_a.session = object()
        self.assertIs(context_b.session, original_b_session)
        self.assertIsNot(context_a.session, context_b.session)

    def test_runtime_id_cannot_be_used_by_another_user(self):
        client_a = app.test_client()
        client_b = app.test_client()
        self._login(client_a, "a@example.test", "password-a")
        self._login(client_b, "b@example.test", "password-b")
        self._start_assessment(client_a, 1)
        self._start_assessment(client_b, 2)
        with client_a.session_transaction() as state_a:
            runtime_a = state_a[RUNTIME_SESSION_KEY]
        with client_b.session_transaction() as state_b:
            state_b[RUNTIME_SESSION_KEY] = runtime_a
        response = client_b.get("/session")
        self.assertEqual(response.status_code, 404)

    def test_admin_disabling_user_immediately_releases_active_runtime(self):
        admin_user = create_user(
            display_name="Admin",
            email="admin@example.test",
            password="password-admin",
            role="ADMIN",
        )
        patient_client = app.test_client()
        self._login(patient_client, "a@example.test", "password-a")
        self._start_assessment(patient_client, 1)
        with patient_client.session_transaction() as state:
            runtime_id = state[RUNTIME_SESSION_KEY]

        context = runtime_registry.get(runtime_id)
        self.assertIsNotNone(context)
        admin_client = app.test_client()
        self._login(
            admin_client,
            "admin@example.test",
            "password-admin",
            role="ADMIN",
        )
        with patch.object(context.pose, "close") as close_pose:
            response = admin_client.post(
                f"/admin/accounts/{self.a.user_id}/disable",
                data={"csrf_token": self._csrf_for(admin_client)},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(close_pose.call_count, 1)
        self.assertIsNone(runtime_registry.get(runtime_id))
        self.assertEqual(context.lifecycle, RuntimeLifecycle.EXPIRED)
        self.assertIsNone(context.session)
        self.assertIsNone(context.completed_session)

    def test_deleting_patient_immediately_releases_patient_runtime(self):
        create_user(
            display_name="Clinician",
            email="clinician@example.test",
            password="password-clinician",
            role="CLINICIAN",
        )
        patient_client = app.test_client()
        self._login(patient_client, "a@example.test", "password-a")
        self._start_assessment(patient_client, 1)
        with patient_client.session_transaction() as state:
            runtime_id = state[RUNTIME_SESSION_KEY]

        context = runtime_registry.get(runtime_id)
        self.assertIsNotNone(context)
        clinician_client = app.test_client()
        self._login(
            clinician_client,
            "clinician@example.test",
            "password-clinician",
            role="CLINICIAN",
        )
        with patch.object(context.pose, "close") as close_pose:
            response = clinician_client.post(
                "/patients/1/delete",
                data={"csrf_token": self._csrf_for(clinician_client)},
            )

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(db.session.get(Patient, 1))
        self.assertEqual(close_pose.call_count, 1)
        self.assertIsNone(runtime_registry.get(runtime_id))
        self.assertEqual(context.lifecycle, RuntimeLifecycle.EXPIRED)
        self.assertIsNone(context.session)
        self.assertIsNone(context.completed_session)

    def test_deleting_patient_releases_clinician_workout_runtime(self):
        create_user(
            display_name="Workout Clinician",
            email="workout-clinician@example.test",
            password="password-clinician",
            role="CLINICIAN",
        )
        client = app.test_client()
        self._login(
            client,
            "workout-clinician@example.test",
            "password-clinician",
            role="CLINICIAN",
        )
        with client.session_transaction() as state:
            csrf = state["revaliv_csrf_token"]

        started = client.post(
            "/workout/start",
            json={
                "preset_id": "bilateral_bicep_curl_2",
                "patient_id": 1,
            },
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(started.status_code, 201)
        with client.session_transaction() as state:
            runtime_id = state[RUNTIME_SESSION_KEY]

        context = runtime_registry.get(runtime_id)
        self.assertIsNotNone(context)
        self.assertIsNone(context.patient_id)
        self.assertEqual(context.workout_runtime.snapshot().patient_id, 1)

        with patch.object(context.pose, "close") as close_pose:
            response = client.post(
                "/patients/1/delete",
                data={"csrf_token": csrf},
            )

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(db.session.get(Patient, 1))
        self.assertEqual(close_pose.call_count, 1)
        self.assertIsNone(runtime_registry.get(runtime_id))
        self.assertEqual(context.lifecycle, RuntimeLifecycle.EXPIRED)
        self.assertIsNone(context.workout_runtime)

    def test_disabled_user_cannot_continue_runtime(self):
        client = app.test_client()
        self._login(client, "a@example.test", "password-a")
        self._start_assessment(client, 1)
        with client.session_transaction() as state:
            runtime_id = state[RUNTIME_SESSION_KEY]
        context = runtime_registry.get(runtime_id)
        self.assertIsNotNone(context)

        from unittest.mock import patch
        with patch.object(context.pose, "close") as close_pose:
            disable_user(self.a.user_id)
            response = client.get("/session")

        self.assertIn(response.status_code, {302, 401})
        self.assertIsNone(runtime_registry.get(runtime_id))
        self.assertEqual(close_pose.call_count, 1)
        self.assertIsNone(context.session)
        with client.session_transaction() as state:
            self.assertNotIn(RUNTIME_SESSION_KEY, state)

    def test_logout_releases_runtime_and_closes_pose_backend(self):
        client = app.test_client()
        self._login(client, "a@example.test", "password-a")
        self._start_assessment(client, 1)
        with client.session_transaction() as state:
            runtime_id = state[RUNTIME_SESSION_KEY]
            csrf = state["revaliv_csrf_token"]
        context = runtime_registry.get(runtime_id)
        self.assertIsNotNone(context)

        from unittest.mock import patch
        with patch.object(context.pose, "close") as close_pose:
            response = client.post("/logout", data={"csrf_token": csrf})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(close_pose.call_count, 1)
        self.assertIsNone(runtime_registry.get(runtime_id))
        self.assertEqual(context.lifecycle, RuntimeLifecycle.EXPIRED)
        self.assertIsNone(context.session)
        self.assertIsNone(context.completed_session)
        self.assertIsNone(context.workout_runtime)


    def test_idle_runtime_expiry_closes_stale_resources_but_keeps_recent_runtime(self):
        now = datetime.utcnow()
        stale = runtime_registry.create(self.a.user_id, patient_id=1)
        recent = runtime_registry.create(self.b.user_id, patient_id=2)
        stale.updated_at = now - timedelta(hours=2)
        recent.updated_at = now

        with (
            patch.object(stale.pose, "close") as close_stale,
            patch.object(recent.pose, "close") as close_recent,
        ):
            expired_count = _expire_idle_runtime_contexts(
                now=now,
                idle_timeout_seconds=60 * 60,
            )

        self.assertEqual(expired_count, 1)
        self.assertIsNone(runtime_registry.get(stale.runtime_id))
        self.assertEqual(stale.lifecycle, RuntimeLifecycle.EXPIRED)
        close_stale.assert_called_once()
        self.assertIs(runtime_registry.get(recent.runtime_id), recent)
        close_recent.assert_not_called()
        _release_runtime_context(recent.runtime_id)

    def test_request_recovers_when_signed_session_references_missing_runtime(self):
        client = app.test_client()
        self._login(client, "a@example.test", "password-a")
        with patch.dict(app.config, {"TESTING": False}):
            self._start_assessment(client, 1)
            with client.session_transaction() as state:
                old_runtime_id = state[RUNTIME_SESSION_KEY]
            old_context = runtime_registry.get(old_runtime_id)
            self.assertIsNotNone(old_context)

            _release_runtime_context(old_runtime_id)
            missing_runtime_response = client.get("/session")
            self.assertEqual(missing_runtime_response.status_code, 404)
            with client.session_transaction() as state:
                self.assertNotIn(RUNTIME_SESSION_KEY, state)

            self._start_assessment(client, 1)
            with client.session_transaction() as state:
                new_runtime_id = state[RUNTIME_SESSION_KEY]
            self.assertNotEqual(new_runtime_id, old_runtime_id)
            self.assertIsNotNone(runtime_registry.get(new_runtime_id))
            _release_runtime_context(new_runtime_id)

    def test_finishing_legacy_assessment_marks_runtime_completed(self):
        client = app.test_client()
        self._login(client, "a@example.test", "password-a")
        self._start_assessment(client, 1)
        with client.session_transaction() as state:
            runtime_id = state[RUNTIME_SESSION_KEY]
            csrf = state["revaliv_csrf_token"]
        context = runtime_registry.get(runtime_id)
        self.assertIsNotNone(context)

        response = client.post("/finish", data={"csrf_token": csrf})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(context.lifecycle, RuntimeLifecycle.COMPLETED)
        self.assertIsNotNone(context.completed_session)

    def test_frame_generator_stops_if_assessment_finishes_during_capture(self):
        client = app.test_client()
        self._login(client, "a@example.test", "password-a")
        self._start_assessment(client, 1)
        with client.session_transaction() as state:
            runtime_id = state[RUNTIME_SESSION_KEY]
        context = runtime_registry.get(runtime_id)
        self.assertIsNotNone(context)

        def finish_during_capture():
            with context.lock:
                # Simulate /finish winning the lock after camera capture starts.
                context.completed_session = {"patient_id": 1}
            return object()

        frames = _generate_frames(context)
        with (
            patch.object(vision, "get_frame", side_effect=finish_during_capture) as get_frame,
            patch.object(context.pose, "process") as process_pose,
        ):
            with self.assertRaises(StopIteration):
                next(frames)

        get_frame.assert_called_once()
        process_pose.assert_not_called()

    def test_discarding_active_legacy_assessment_marks_runtime_cancelled(self):
        client = app.test_client()
        self._login(client, "a@example.test", "password-a")
        self._start_assessment(client, 1)
        with client.session_transaction() as state:
            runtime_id = state[RUNTIME_SESSION_KEY]
            csrf = state["revaliv_csrf_token"]
        context = runtime_registry.get(runtime_id)
        self.assertIsNotNone(context)
        context.session_manager.add_result(AssessmentResult(overall_score=75))

        response = client.post("/discard", data={"csrf_token": csrf})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(context.lifecycle, RuntimeLifecycle.CANCELLED)
        self.assertIsNone(context.session)
        self.assertIsNone(context.completed_session)
        self.assertEqual(context.session_manager.repetition_count, 0)
        self.assertEqual(client.get("/video_feed").status_code, 404)

    def test_discard_route_cannot_clobber_active_workout(self):
        client = app.test_client()
        self._login(client, "a@example.test", "password-a")
        with client.session_transaction() as state:
            csrf = state["revaliv_csrf_token"]
        started = client.post(
            "/workout/start",
            json={
                "preset_id": "bilateral_bicep_curl_2",
                "patient_id": 1,
            },
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(started.status_code, 201)
        with client.session_transaction() as state:
            runtime_id = state[RUNTIME_SESSION_KEY]
            csrf = state["revaliv_csrf_token"]
        context = runtime_registry.get(runtime_id)
        self.assertIsNotNone(context)
        self.assertTrue(context.workout_runtime.active)

        response = client.post("/discard", data={"csrf_token": csrf})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(context.runtime_mode, "workout_session")
        self.assertTrue(context.workout_runtime.active)

    def test_workout_cancellation_does_not_change_other_runtime(self):
        client_a = app.test_client()
        client_b = app.test_client()
        self._login(client_a, "a@example.test", "password-a")
        self._login(client_b, "b@example.test", "password-b")
        for client, patient_id in ((client_a, 1), (client_b, 2)):
            with client.session_transaction() as state:
                token = state["revaliv_csrf_token"]
            response = client.post(
                "/workout/start",
                json={
                    "preset_id": "bilateral_bicep_curl_2",
                    "patient_id": patient_id,
                },
                headers={"X-CSRF-Token": token},
            )
            self.assertEqual(response.status_code, 201)

        with client_b.session_transaction() as state:
            runtime_b = state[RUNTIME_SESSION_KEY]
        response = client_a.post(
            "/workout/cancel",
            headers={"X-CSRF-Token": self._csrf_for(client_a)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(runtime_registry.get(runtime_b).workout_runtime.active)

    @staticmethod
    def _csrf_for(client):
        with client.session_transaction() as state:
            return state["revaliv_csrf_token"]


if __name__ == "__main__":
    unittest.main()
