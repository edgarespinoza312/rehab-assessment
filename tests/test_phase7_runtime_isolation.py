import unittest
from unittest.mock import patch

from dashboard.app import app, runtime_registry, _generate_frames
from dashboard.database import db
from dashboard.models import Patient, Role, User
from dashboard.runtime_context import RuntimeLifecycle
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

    def _login(self, client, email, password):
        client.get("/login")
        with client.session_transaction() as state:
            token = state["revaliv_csrf_token"]
        response = client.post("/login", data={
            "csrf_token": token,
            "email": email,
            "password": password,
            "role": "PATIENT",
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
            patch("dashboard.app.vision.get_frame", side_effect=finish_during_capture) as get_frame,
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
        context.session_manager.add_result(
            __import__("core.models", fromlist=["AssessmentResult"]).AssessmentResult(
                overall_score=75,
            )
        )

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
            runtime_id = state[RUNTIME_SESSION_KEY] if RUNTIME_SESSION_KEY in state else None
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
