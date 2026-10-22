import os
import sys
import threading
import unittest
import numpy as np
from unittest.mock import patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard.config import Config
from core.vision import VisionEngine


class StubPoseBackend:
    name = "mediapipe"
    last_result = None

    def __init__(self):
        self.side = None
        self.calibration_started = threading.Event()
        self.allow_calibration = threading.Event()
        self.block_calibration = False

    @property
    def calibration_status(self):
        return {
            "stage": "baseline" if self.side else "required",
            "side": self.side,
            "calibrated": False,
        }

    def begin_calibration(self, side):
        self.side = side
        self.last_result = None
        self.calibration_started.set()
        if self.block_calibration:
            if not self.allow_calibration.wait(3):
                raise TimeoutError("test did not release calibration")

    def reset_calibration(self):
        self.side = None
        self.last_result = None

    def close(self):
        pass


_test_pose = StubPoseBackend()
_original_database_uri = Config.SQLALCHEMY_DATABASE_URI
Config.SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
try:
    with patch.object(VisionEngine, "start", return_value=None), patch(
        "core.perception.create_perception_backend", return_value=_test_pose
    ):
        import dashboard.app as dashboard
finally:
    Config.SQLALCHEMY_DATABASE_URI = _original_database_uri

from core.models import (
    AssessmentResult,
    ExercisePhase,
    Joint,
    JointType,
    Skeleton,
    AssessmentSession,
    ExerciseState,
    ExerciseType,
    MovementMetrics,
)
from core.exercise_catalog import get_exercise_profile
from core.perception.base import PerceptionResult, PoseStatus, ReadinessState
from core.workout import SessionEngine, SessionStatus, STARTER_BICEP_CURL_PRESET
from dashboard.database import db
from dashboard.models import CompletedWorkoutSession, Patient, Role, User, WorkoutPlan
from dashboard.workout_runtime import WorkoutRuntimeAdapter
from dashboard.services.workout_persistence import review_workout_plan
from tests.support.auth import login_client, seed_clinician


class DashboardAssessmentStateSyncTests(unittest.TestCase):
    def setUp(self):
        with dashboard.app.app_context():
            if db.session.get(Patient, 8) is None:
                db.session.add(Patient(
                    patient_id=8,
                    first_name="Workout",
                    last_name="Patient",
                ))
                if User.query.filter_by(email="clinician@test.invalid").first() is None:
                    seed_clinician(dashboard.app)
                db.session.commit()
        with dashboard.assessment_state_lock:
            dashboard.session = None
            dashboard.completed_session = None
            dashboard.runtime_mode = dashboard.RuntimeMode.LEGACY_ASSESSMENT
            dashboard.workout_runtime = None
            dashboard.display_pose_continuity.clear()
            dashboard.pose = _test_pose
            dashboard.session_manager.clear()
            dashboard.exercise.state = ExerciseState()
            dashboard.biomechanics.reset_rep_metrics()
            _test_pose.side = None
            _test_pose.last_result = None
            _test_pose.block_calibration = False
            _test_pose.calibration_started.clear()
            _test_pose.allow_calibration.clear()

    def _approve_saved_plan(self, plan_id):
        """Use a separate clinician to satisfy the plan's independent review gate."""
        with dashboard.app.app_context():
            reviewer = User.query.filter_by(email="plan-reviewer@test.invalid").one_or_none()
            if reviewer is None:
                role = Role.query.filter_by(name="CLINICIAN").one_or_none()
                if role is None:
                    role = Role(name="CLINICIAN")
                    db.session.add(role)
                    db.session.flush()
                reviewer = User(
                    display_name="Independent Test Reviewer",
                    email="plan-reviewer@test.invalid",
                    status="ACTIVE",
                    roles=[role],
                )
                db.session.add(reviewer)
                db.session.commit()
            review_workout_plan(
                plan_id,
                reviewer.user_id,
                "approve",
                "Independent review recorded by workflow test fixture.",
            )

    def _new_session(self, metrics=None, state=None):
        exercise = ExerciseType.LEFT_BICEP_CURL
        return AssessmentSession(
            exercise=exercise,
            profile=get_exercise_profile(exercise),
            exercise_state=state or ExerciseState(),
            movement_metrics=metrics or MovementMetrics(),
        )

    @staticmethod
    def _run_request(method, path, **kwargs):
        with dashboard.app.test_client() as client:
            login_client(dashboard.app, client)
            if method.lower() == "post":
                with client.session_transaction() as session:
                    csrf = session["revaliv_csrf_token"]
                if kwargs.get("json") is not None:
                    headers = dict(kwargs.get("headers") or {})
                    headers["X-CSRF-Token"] = csrf
                    kwargs["headers"] = headers
                else:
                    data = kwargs.get("data")
                    if isinstance(data, dict):
                        data = dict(data)
                        data.setdefault("csrf_token", csrf)
                        kwargs["data"] = data
                    else:
                        headers = dict(kwargs.get("headers") or {})
                        headers["X-CSRF-Token"] = csrf
                        kwargs["headers"] = headers
            return getattr(client, method)(path, **kwargs)

    def test_session_returns_calibration_without_an_active_assessment(self):
        _test_pose.side = "left"
        response = self._run_request("get", "/session")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(
            payload["perception_calibration"],
            {"stage": "baseline", "side": "left", "calibrated": False},
        )

    def test_session_returns_active_assessment_and_calibration(self):
        with dashboard.assessment_state_lock:
            dashboard.session = self._new_session()
            _test_pose.side = "left"
        response = self._run_request("get", "/session")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["exercise"], "Left Bicep Curl")
        self.assertEqual(payload["trend"], "Collecting Data")
        self.assertEqual(payload["perception_calibration"]["side"], "left")

    def test_brief_rejection_keeps_pose_display_only_and_never_reuses_measurements(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        skeleton = Skeleton(timestamp=1.0, frame_number=1)
        skeleton.add_joint(Joint(JointType.LEFT_SHOULDER, 0.3, 0.2))
        skeleton.add_joint(Joint(JointType.LEFT_ELBOW, 0.4, 0.4))
        accepted = PerceptionResult(
            skeleton=skeleton, status=PoseStatus.VALID, backend="mediapipe",
            timestamp=1.0, frame_number=1, state=ReadinessState.READY, tracking=True,
        )
        rejected = PerceptionResult(
            skeleton=None, status=PoseStatus.INVALID, backend="mediapipe",
            timestamp=1.1, frame_number=2, state=ReadinessState.NO_PERSON,
        )
        results = iter((accepted, rejected))
        annotations = np.full_like(frame, 255)

        def process(*args, **kwargs):
            result = next(results)
            _test_pose.last_result = result
            return annotations, result.skeleton

        with dashboard.assessment_state_lock:
            dashboard.session = self._new_session()
        _test_pose.side = "left"
        generator = dashboard._generate_frames()
        with patch.object(dashboard.vision, "get_frame", side_effect=(frame, frame)), \
             patch.object(dashboard.pose, "process", side_effect=process, create=True), \
             patch.object(dashboard.overlay, "draw", side_effect=lambda image, *a, **kw: image) as draw, \
             patch.object(dashboard.biomechanics, "calculate_metrics", return_value=MovementMetrics()) as calculate, \
             patch.object(dashboard.exercise, "analyze", return_value=ExerciseState(active=True)) as analyze, \
             patch.object(dashboard.cv2, "imencode", return_value=(True, np.array([1], dtype=np.uint8))):
            next(generator)
            next(generator)
            generator.close()

        self.assertEqual(calculate.call_count, 1)
        self.assertEqual(analyze.call_count, 1)
        self.assertIs(draw.call_args_list[0].args[1], skeleton)
        self.assertIsNotNone(draw.call_args_list[1].args[1])
        self.assertTrue(draw.call_args_list[1].kwargs["display_only_stale"])
        self.assertIsNone(draw.call_args_list[1].args[2])
        self.assertIsNone(draw.call_args_list[1].args[3])
        self.assertIs(draw.call_args_list[1].args[0], frame)
        self.assertIsNot(draw.call_args_list[1].args[0], annotations)
        self.assertIsNone(dashboard.session.movement_metrics)

    def test_session_keeps_completed_history_and_reports_pose_loss_without_live_metrics(self):
        with dashboard.assessment_state_lock:
            dashboard.session = self._new_session(metrics=None)
            dashboard.session.movement_metrics = None
            dashboard.session_manager.add_result(AssessmentResult(overall_score=88))
            _test_pose.last_result = PerceptionResult(
                skeleton=None, status=PoseStatus.INVALID, backend="mediapipe",
                timestamp=1.0, frame_number=3, state=ReadinessState.NO_PERSON,
            )
        response = self._run_request("get", "/session")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["repetitions"], 1)
        self.assertEqual(payload["current_score"], 88)
        self.assertEqual(payload["joint_angles"], {})
        self.assertEqual(payload["perception_readiness"]["state"], "no_person")
        self.assertFalse(payload["perception_readiness"]["tracking"])

    def test_rejected_frame_shows_no_cached_pose_to_analysis_or_raw_backend_overlay(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        backend_annotated = np.full_like(frame, 255)
        result = PerceptionResult(
            skeleton=None, status=PoseStatus.INVALID, backend="mediapipe",
            timestamp=1.0, frame_number=1, state=ReadinessState.NO_PERSON,
        )
        with dashboard.assessment_state_lock:
            dashboard.session = self._new_session()
        _test_pose.last_result = result

        def process(*args, **kwargs):
            return backend_annotated, None

        generator = dashboard._generate_frames()
        with patch.object(dashboard.vision, "get_frame", return_value=frame), \
             patch.object(dashboard.pose, "process", side_effect=process, create=True), \
             patch.object(dashboard.overlay, "draw", side_effect=lambda image, *a, **kw: image) as draw, \
             patch.object(dashboard.biomechanics, "calculate_metrics") as calculate, \
             patch.object(dashboard.exercise, "analyze") as analyze, \
             patch.object(dashboard.cv2, "imencode", return_value=(True, np.array([1], dtype=np.uint8))):
            next(generator)
            generator.close()

        calculate.assert_not_called()
        analyze.assert_not_called()
        self.assertIs(draw.call_args.args[0], frame)
        self.assertIsNone(draw.call_args.args[1])
        self.assertIsNone(dashboard.session.movement_metrics)
        self.assertEqual(dashboard.session_manager.repetition_count, 0)
        self.assertIsNot(draw.call_args.args[0], backend_annotated)

    def test_assessment_initialization_blocks_session_read_until_atomic_reset_finishes(self):
        with dashboard.assessment_state_lock:
            dashboard.session_manager.add_result(AssessmentResult(overall_score=99))
            dashboard.exercise.state = ExerciseState(repetitions=8)
        _test_pose.block_calibration = True
        start_done = threading.Event()
        read_started = threading.Event()
        read_done = threading.Event()
        results = {}

        def start():
            try:
                results["start"] = self._run_request(
                    "post", "/assessment",
                    data={"exercise": "LEFT_BICEP_CURL", "patient_id": 8}
                )
            finally:
                start_done.set()

        def read():
            read_started.set()
            results["read"] = self._run_request("get", "/session")
            read_done.set()

        starter = threading.Thread(target=start)
        starter.start()
        self.assertTrue(_test_pose.calibration_started.wait(2))
        reader = threading.Thread(target=read)
        reader.start()
        self.assertTrue(read_started.wait(2))
        self.assertFalse(read_done.wait(0.05))

        _test_pose.allow_calibration.set()
        starter.join(3)
        reader.join(3)
        self.assertTrue(start_done.is_set())
        self.assertTrue(read_done.is_set())
        self.assertEqual(results["start"].status_code, 302)
        payload = results["read"].get_json()
        self.assertEqual(payload["exercise"], "Left Bicep Curl")
        self.assertEqual(payload["repetitions"], 0)
        self.assertEqual(payload["perception_calibration"]["stage"], "baseline")
        self.assertEqual(dashboard.exercise.state.repetitions, 0)

    def test_assessment_initialization_waits_for_active_frame_transaction(self):
        with dashboard.assessment_state_lock:
            dashboard.session = self._new_session()
        frame_started = threading.Event()
        allow_frame_to_finish = threading.Event()
        start_started = threading.Event()
        start_done = threading.Event()
        responses = {}

        def frame_transaction():
            with dashboard.assessment_state_lock:
                dashboard.session.movement_metrics.elbow_angle_left = 123
                frame_started.set()
                if not allow_frame_to_finish.wait(3):
                    raise TimeoutError("test did not release frame transaction")
                dashboard.session.exercise_state = ExerciseState(active=True)

        def start_assessment():
            start_started.set()
            responses["start"] = self._run_request(
                "post", "/assessment",
                data={"exercise": "LEFT_BICEP_CURL", "patient_id": 8}
            )
            start_done.set()

        frame = threading.Thread(target=frame_transaction)
        frame.start()
        self.assertTrue(frame_started.wait(2))
        starter = threading.Thread(target=start_assessment)
        starter.start()
        self.assertTrue(start_started.wait(2))
        self.assertFalse(start_done.wait(0.05))

        allow_frame_to_finish.set()
        frame.join(3)
        starter.join(3)
        self.assertTrue(start_done.is_set())
        self.assertEqual(responses["start"].status_code, 302)
        self.assertEqual(dashboard.session.profile.display_name, "Left Bicep Curl")
        self.assertEqual(dashboard.session_manager.repetition_count, 0)
        self.assertEqual(dashboard.exercise.state.repetitions, 0)

    def test_finish_waits_for_frame_transaction_and_snapshots_consistent_scores(self):
        with dashboard.assessment_state_lock:
            dashboard.session = self._new_session()
            dashboard.session_manager.add_result(AssessmentResult(overall_score=80))
        mutation_started = threading.Event()
        allow_mutation = threading.Event()
        finish_started = threading.Event()
        finish_done = threading.Event()
        responses = {}

        def frame_transaction():
            with dashboard.assessment_state_lock:
                dashboard.session.movement_metrics.elbow_angle_left = 141
                mutation_started.set()
                if not allow_mutation.wait(3):
                    raise TimeoutError("test did not release frame transaction")
                dashboard.session.exercise_state = ExerciseState(active=True, repetitions=2)
                dashboard.session_manager.add_result(AssessmentResult(overall_score=100))

        def finish():
            finish_started.set()
            responses["finish"] = self._run_request("post", "/finish")
            finish_done.set()

        mutator = threading.Thread(target=frame_transaction)
        mutator.start()
        self.assertTrue(mutation_started.wait(2))
        finisher = threading.Thread(target=finish)
        finisher.start()
        self.assertTrue(finish_started.wait(2))
        self.assertFalse(finish_done.wait(0.05))

        allow_mutation.set()
        mutator.join(3)
        finisher.join(3)
        self.assertTrue(finish_done.is_set())
        self.assertEqual(responses["finish"].status_code, 302)
        self.assertEqual(dashboard.completed_session["repetitions"], 2)
        self.assertEqual(dashboard.completed_session["average_score"], 90)

    def test_legacy_assessment_still_finishes_and_builds_its_report(self):
        with dashboard.assessment_state_lock:
            dashboard.session = self._new_session()
            dashboard.session_manager.clear()
            dashboard.session_manager.add_result(
                AssessmentResult(overall_score=84, feedback=["steady movement"])
            )

        response = self._run_request("post", "/finish")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/report", response.headers["Location"])
        self.assertEqual(dashboard.completed_session["exercise"], "Left Bicep Curl")
        self.assertEqual(dashboard.completed_session["repetitions"], 1)
        self.assertEqual(dashboard.completed_session["average_score"], 84)
        self.assertEqual(dashboard.completed_session["feedback"], ["steady movement"])

    def test_legacy_session_is_independent_of_inactive_workout_state(self):
        adapter = WorkoutRuntimeAdapter(
            engine=SessionEngine(
                create_session_id=lambda: "cancelled-workout",
            ),
            reset_pipeline=lambda side: None,
        )
        adapter.start(STARTER_BICEP_CURL_PRESET)
        adapter.cancel()
        self.assertEqual(adapter.status, SessionStatus.CANCELLED)

        with dashboard.assessment_state_lock:
            dashboard.workout_runtime = adapter
            dashboard.runtime_mode = dashboard.RuntimeMode.LEGACY_ASSESSMENT
            dashboard.session = self._new_session()
            dashboard.session_manager.clear()
            dashboard.session_manager.add_result(AssessmentResult(overall_score=88))

        legacy_response = self._run_request("get", "/session")
        workout_response = self._run_request("get", "/workout/session")

        self.assertEqual(legacy_response.status_code, 200)
        self.assertEqual(legacy_response.get_json()["exercise"], "Left Bicep Curl")
        self.assertEqual(legacy_response.get_json()["repetitions"], 1)
        self.assertEqual(workout_response.status_code, 200)
        self.assertEqual(workout_response.get_json()["status"], "cancelled")

    def test_session_waits_for_frame_transaction_and_returns_coherent_snapshot(self):
        with dashboard.assessment_state_lock:
            dashboard.session = self._new_session()
            dashboard.session_manager.add_result(AssessmentResult(overall_score=80))
        mutation_started = threading.Event()
        allow_mutation = threading.Event()
        read_started = threading.Event()
        read_done = threading.Event()
        responses = {}

        def frame_transaction():
            with dashboard.assessment_state_lock:
                dashboard.session.movement_metrics.elbow_angle_left = 137
                mutation_started.set()
                if not allow_mutation.wait(3):
                    raise TimeoutError("test did not release frame transaction")
                dashboard.session.exercise_state = ExerciseState(active=True, repetitions=1)
                dashboard.session_manager.add_result(AssessmentResult(overall_score=92))

        def read_session():
            read_started.set()
            responses["session"] = self._run_request("get", "/session")
            read_done.set()

        mutator = threading.Thread(target=frame_transaction)
        mutator.start()
        self.assertTrue(mutation_started.wait(2))
        reader = threading.Thread(target=read_session)
        reader.start()
        self.assertTrue(read_started.wait(2))
        self.assertFalse(read_done.wait(0.05))

        allow_mutation.set()
        mutator.join(3)
        reader.join(3)
        self.assertTrue(read_done.is_set())
        payload = responses["session"].get_json()
        self.assertEqual(payload["joint_angles"]["Left Elbow"], 137)
        self.assertTrue(payload["tracking"])
        self.assertEqual(payload["repetitions"], 2)
        self.assertEqual(payload["current_score"], 92)

    def test_workout_api_validates_missing_malformed_and_unknown_requests(self):
        missing = self._run_request("post", "/workout/start", json={})
        malformed = self._run_request(
            "post", "/workout/start", data="not-json", content_type="application/json"
        )
        unknown = self._run_request(
            "post", "/workout/start", json={"preset_id": "not-a-preset"}
        )
        missing_patient = self._run_request(
            "post",
            "/workout/start",
            json={"preset_id": "bilateral_bicep_curl_2"},
        )
        unknown_patient = self._run_request(
            "post",
            "/workout/start",
            json={"preset_id": "bilateral_bicep_curl_2", "patient_id": 999},
        )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(missing_patient.status_code, 400)
        self.assertEqual(unknown_patient.status_code, 404)
        self.assertEqual(self._run_request("get", "/workout/session").status_code, 404)
        self.assertEqual(self._run_request("post", "/workout/cancel").status_code, 404)

    def test_workout_start_read_cancel_and_second_start_behavior(self):
        response = self._run_request(
            "post",
            "/workout/start",
            json={"preset_id": "bilateral_bicep_curl_2", "patient_id": 8},
        )
        self.assertEqual(response.status_code, 201)
        snapshot = response.get_json()
        runtime_session_id = snapshot["session_id"]
        self.assertEqual(snapshot["status"], "calibrating")
        self.assertEqual(snapshot["patient_id"], 8)
        self.assertEqual(snapshot["current_exercise"]["side"], "right")
        self.assertEqual(snapshot["current_exercise"]["target_repetitions"], 2)
        self.assertEqual(_test_pose.side, "Right")
        self.assertEqual(dashboard.runtime_mode, dashboard.RuntimeMode.WORKOUT_SESSION)

        read = self._run_request("get", "/workout/session")
        self.assertEqual(read.status_code, 200)
        workout_state = read.get_json()
        self.assertEqual(workout_state["session_id"], snapshot["session_id"])
        self.assertEqual(workout_state["current_exercise"]["side"], "right")
        self.assertEqual(workout_state["completed_repetitions"], 0)
        self.assertEqual(workout_state["exercise_phase"], None)
        self.assertEqual(workout_state["calibration"]["side"], "Right")

        with dashboard.assessment_state_lock:
            dashboard.workout_runtime.begin_frame(
                PerceptionResult(
                    skeleton=Skeleton(),
                    status=PoseStatus.VALID,
                    backend="test",
                    timestamp=1.0,
                    frame_number=1,
                    state=ReadinessState.READY,
                )
            )
            dashboard.workout_runtime.begin_frame(
                PerceptionResult(
                    skeleton=Skeleton(),
                    status=PoseStatus.VALID,
                    backend="test",
                    timestamp=2.0,
                    frame_number=2,
                    state=ReadinessState.READY,
                )
            )
            dashboard.exercise.state.phase = ExercisePhase.LIFTING
        exercising = self._run_request("get", "/workout/session")
        self.assertEqual(exercising.get_json()["status"], "exercising")
        self.assertEqual(exercising.get_json()["exercise_phase"], "LIFTING")

        duplicate_start = self._run_request(
            "post",
            "/workout/start",
            json={"preset_id": "bilateral_bicep_curl_2", "patient_id": 8},
        )
        self.assertEqual(duplicate_start.status_code, 409)

        accepted = PerceptionResult(
            skeleton=Skeleton(),
            status=PoseStatus.VALID,
            backend="test",
            timestamp=3.0,
            frame_number=3,
            state=ReadinessState.READY,
        )
        with dashboard.app.app_context():
            with dashboard.assessment_state_lock:
                for score in (89, 93):
                    dashboard._record_workout_repetition_locked(
                        accepted,
                        ExerciseState(
                            exercise_name="RIGHT_BICEP_CURL",
                            rep_completed=True,
                        ),
                        AssessmentResult(overall_score=score),
                    )
                self.assertEqual(
                    CompletedWorkoutSession.query.filter_by(
                        runtime_session_id=runtime_session_id
                    ).count(),
                    0,
                )

        cancelled = self._run_request("post", "/workout/cancel")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.get_json()["status"], "cancelled")
        self.assertIsNone(_test_pose.side)
        with dashboard.app.app_context():
            persisted = CompletedWorkoutSession.query.filter_by(
                runtime_session_id=runtime_session_id
            ).one()
            self.assertEqual(persisted.patient_id, 8)
            self.assertEqual(persisted.status, "cancelled")
            self.assertEqual(len(persisted.exercise_results), 1)
            self.assertEqual(persisted.exercise_results[0].side, "right")
            self.assertEqual(persisted.exercise_results[0].completed_repetitions, 2)

        restarted = self._run_request(
            "post",
            "/workout/start",
            json={"preset_id": "bilateral_bicep_curl_2", "patient_id": 8},
        )
        self.assertEqual(restarted.status_code, 201)

    def test_workout_persists_only_after_terminal_rep_and_is_idempotent(self):
        response = self._run_request(
            "post",
            "/workout/start",
            json={"preset_id": "bilateral_bicep_curl_2", "patient_id": 8},
        )
        self.assertEqual(response.status_code, 201)
        runtime_session_id = response.get_json()["session_id"]
        accepted = PerceptionResult(
            skeleton=Skeleton(),
            status=PoseStatus.VALID,
            backend="test",
            timestamp=1.0,
            frame_number=1,
            state=ReadinessState.READY,
        )

        with dashboard.app.app_context():
            with dashboard.assessment_state_lock:
                self.assertFalse(dashboard.workout_runtime.begin_frame(accepted))
                self.assertEqual(
                    CompletedWorkoutSession.query.filter_by(
                        runtime_session_id=runtime_session_id
                    ).count(),
                    0,
                )
                self.assertTrue(dashboard.workout_runtime.begin_frame(accepted))
                self.assertEqual(
                    CompletedWorkoutSession.query.filter_by(
                        runtime_session_id=runtime_session_id
                    ).count(),
                    0,
                )

                for side, scores in (
                    ("right", (88, 94)),
                    ("left", (90, 96)),
                ):
                    for index, score in enumerate(scores):
                        completed = dashboard._record_workout_repetition_locked(
                            accepted,
                            ExerciseState(
                                exercise_name=f"{side.upper()}_BICEP_CURL",
                                rep_completed=True,
                            ),
                            AssessmentResult(
                                overall_score=score,
                                rom_score=score - 5,
                                feedback=[f"{side} rep score {score}"],
                            ),
                        )
                        if side == "right" and index == 0:
                            self.assertFalse(completed)
                        if side == "right" and index == 1:
                            self.assertTrue(completed)
                            self.assertEqual(
                                CompletedWorkoutSession.query.filter_by(
                                    runtime_session_id=runtime_session_id
                                ).count(),
                                0,
                            )
                            self.assertFalse(
                                dashboard.workout_runtime.begin_frame(accepted)
                            )
                            self.assertTrue(
                                dashboard.workout_runtime.begin_frame(accepted)
                            )
                        if side == "left" and index == 0:
                            self.assertFalse(completed)
                        if side == "left" and index == 1:
                            self.assertTrue(completed)

                session_record = CompletedWorkoutSession.query.filter_by(
                    runtime_session_id=runtime_session_id
                ).one()
                self.assertEqual(session_record.patient_id, 8)
                self.assertEqual(session_record.status, "completed")
                self.assertEqual(len(session_record.exercise_results), 2)
                right, left = session_record.exercise_results
                self.assertEqual(
                    [(result.position, result.exercise_id, result.side) for result in (right, left)],
                    [(0, "bicep_curl", "right"), (1, "bicep_curl", "left")],
                )
                for result in (right, left):
                    self.assertEqual(result.target_repetitions, 2)
                    self.assertEqual(result.completed_repetitions, 2)
                self.assertEqual(right.average_score, 91)
                self.assertEqual(left.average_score, 93)
                self.assertEqual(right.rom_score, 86)
                self.assertEqual(left.rom_score, 88)

                dashboard._persist_workout_snapshot(dashboard.workout_runtime.snapshot())
                self.assertEqual(
                    CompletedWorkoutSession.query.filter_by(
                        runtime_session_id=runtime_session_id
                    ).count(),
                    1,
                )

    def test_builder_saves_validated_ordered_patient_plan(self):
        invalid_cases = (
            {"exercise_id": "unknown_exercise", "side": "left", "target_repetitions": 4},
            {"exercise_id": "bicep_curl", "side": "left", "target_repetitions": 0},
            {"exercise_id": "bicep_curl", "side": "both", "target_repetitions": 4},
        )
        for item in invalid_cases:
            response = self._run_request(
                "post",
                "/workout/plans",
                json={
                    "name": "Invalid",
                    "patient_id": 8,
                    "exercises": [{"position": 0, **item}],
                },
            )
            self.assertEqual(response.status_code, 400)

        invalid_order = self._run_request(
            "post",
            "/workout/plans",
            json={
                "name": "Invalid order",
                "patient_id": 8,
                "exercises": [
                    {"position": 0, "exercise_id": "bicep_curl", "side": "right",
                     "target_repetitions": 4},
                    {"position": 0, "exercise_id": "bicep_curl", "side": "left",
                     "target_repetitions": 4},
                ],
            },
        )
        self.assertEqual(invalid_order.status_code, 400)

        created = self._run_request(
            "post",
            "/workout/plans",
            json={
                "name": "Custom order",
                "description": "Saved from builder",
                "patient_id": 8,
                "exercises": [
                    {
                        "position": 2,
                        "exercise_id": "bicep_curl",
                        "side": "right",
                        "target_repetitions": 7,
                    },
                    {
                        "position": 0,
                        "exercise_id": "bicep_curl",
                        "side": "right",
                        "target_repetitions": 3,
                        "resistance_value": 2.5,
                        "resistance_unit": "kg",
                        "resistance_type": "external",
                    },
                    {
                        "position": 1,
                        "exercise_id": "bicep_curl",
                        "side": "left",
                        "target_repetitions": 5,
                    },
                ],
            },
        )
        self.assertEqual(created.status_code, 201)
        plan_id = created.get_json()["plan_id"]
        with dashboard.app.app_context():
            plan = db.session.get(WorkoutPlan, plan_id)
            self.assertEqual(plan.patient_id, 8)
            self.assertEqual(
                [(item.position, item.side, item.target_repetitions) for item in plan.exercises],
                [(0, "right", 3), (1, "left", 5), (2, "right", 7)],
            )
            self.assertEqual(float(plan.exercises[0].resistance_value), 2.5)
            self.assertEqual(plan.exercises[0].resistance_unit, "kg")

        builder = self._run_request("get", "/workout/builder?patient_id=8")
        self.assertEqual(builder.status_code, 200)
        self.assertIn("builder-exercise-data", builder.get_data(as_text=True))
        listing = self._run_request("get", "/selection?patient_id=8")
        self.assertIn("Custom order", listing.get_data(as_text=True))

    def test_saved_plan_runs_in_order_and_persists_plan_resistance_and_results(self):
        created = self._run_request(
            "post",
            "/workout/plans",
            json={
                "name": "Ordered workout",
                "patient_id": 8,
                "exercises": [
                    {
                        "position": 0,
                        "exercise_id": "bicep_curl",
                        "side": "right",
                        "target_repetitions": 1,
                        "resistance_value": 5,
                        "resistance_unit": "lb",
                        "resistance_type": "external",
                    },
                    {
                        "position": 1,
                        "exercise_id": "bicep_curl",
                        "side": "left",
                        "target_repetitions": 1,
                    },
                    {
                        "position": 2,
                        "exercise_id": "bicep_curl",
                        "side": "right",
                        "target_repetitions": 1,
                    },
                ],
            },
        )
        self.assertEqual(created.status_code, 201)
        plan_id = created.get_json()["plan_id"]
        self._approve_saved_plan(plan_id)

        started = self._run_request(
            "post",
            "/workout/start",
            json={"plan_id": plan_id, "patient_id": 8},
        )
        self.assertEqual(started.status_code, 201)
        snapshot = started.get_json()
        runtime_id = snapshot["session_id"]
        self.assertEqual(snapshot["preset_id"], f"workout_plan_{plan_id}")
        self.assertEqual(snapshot["current_exercise"]["side"], "right")
        self.assertEqual(snapshot["current_exercise"]["resistance_value"], 5.0)
        self.assertEqual(dashboard.workout_runtime.workout_plan_id, plan_id)

        accepted = PerceptionResult(
            skeleton=Skeleton(),
            status=PoseStatus.VALID,
            backend="test",
            timestamp=1.0,
            frame_number=1,
            state=ReadinessState.READY,
        )
        with dashboard.app.app_context():
            with dashboard.assessment_state_lock:
                for index, (side, score) in enumerate(
                    (("right", 80), ("left", 85), ("right", 90))
                ):
                    self.assertFalse(
                        dashboard.workout_runtime.begin_frame(accepted)
                    )
                    self.assertTrue(
                        dashboard.workout_runtime.begin_frame(accepted)
                    )
                    exercise_transitioned = dashboard._record_workout_repetition_locked(
                        accepted,
                        ExerciseState(
                            exercise_name=f"{side.upper()}_BICEP_CURL",
                            rep_completed=True,
                        ),
                        AssessmentResult(
                            overall_score=score,
                            rom_score=score - 2,
                            feedback=[f"{side} feedback"],
                        ),
                    )
                    if index < 2:
                        self.assertTrue(exercise_transitioned)
                        self.assertEqual(
                            CompletedWorkoutSession.query.filter_by(
                                runtime_session_id=runtime_id
                            ).count(),
                            0,
                        )
                    else:
                        self.assertTrue(exercise_transitioned)

                persisted = CompletedWorkoutSession.query.filter_by(
                    runtime_session_id=runtime_id
                ).one()
                self.assertEqual(persisted.workout_plan_id, plan_id)
                self.assertEqual(persisted.patient_id, 8)
                self.assertEqual(persisted.status, "completed")
                self.assertEqual(
                    [
                        (item.position, item.exercise_id, item.side)
                        for item in persisted.exercise_results
                    ],
                    [
                        (0, "bicep_curl", "right"),
                        (1, "bicep_curl", "left"),
                        (2, "bicep_curl", "right"),
                    ],
                )
                self.assertEqual(
                    [item.average_score for item in persisted.exercise_results],
                    [80, 85, 90],
                )
                self.assertEqual(
                    persisted.exercise_results[0].resistance_unit,
                    "lb",
                )
                self.assertEqual(
                    persisted.exercise_results[0].resistance_type,
                    "external",
                )
                self.assertIsNone(persisted.exercise_results[1].resistance_value)

        wrong_patient = self._run_request(
            "post",
            "/workout/start",
            json={"plan_id": plan_id, "patient_id": 999},
        )
        self.assertEqual(wrong_patient.status_code, 404)
        unknown_plan = self._run_request(
            "post",
            "/workout/start",
            json={"plan_id": plan_id + 1000, "patient_id": 8},
        )
        self.assertEqual(unknown_plan.status_code, 404)

    def test_cancelled_saved_plan_links_plan_and_only_completed_results(self):
        created = self._run_request(
            "post",
            "/workout/plans",
            json={
                "name": "Cancel after first",
                "patient_id": 8,
                "exercises": [
                    {
                        "position": 0,
                        "exercise_id": "bicep_curl",
                        "side": "right",
                        "target_repetitions": 1,
                    },
                    {
                        "position": 1,
                        "exercise_id": "bicep_curl",
                        "side": "left",
                        "target_repetitions": 3,
                    },
                ],
            },
        )
        plan_id = created.get_json()["plan_id"]
        self._approve_saved_plan(plan_id)
        started = self._run_request(
            "post",
            "/workout/start",
            json={"plan_id": plan_id, "patient_id": 8},
        )
        runtime_id = started.get_json()["session_id"]
        accepted = PerceptionResult(
            skeleton=Skeleton(),
            status=PoseStatus.VALID,
            backend="test",
            timestamp=1.0,
            frame_number=1,
            state=ReadinessState.READY,
        )
        with dashboard.app.app_context():
            with dashboard.assessment_state_lock:
                dashboard.workout_runtime.begin_frame(accepted)
                dashboard.workout_runtime.begin_frame(accepted)
                self.assertTrue(dashboard._record_workout_repetition_locked(
                    accepted,
                    ExerciseState(
                        exercise_name="RIGHT_BICEP_CURL",
                        rep_completed=True,
                    ),
                    AssessmentResult(overall_score=89),
                ))
                self.assertFalse(dashboard.workout_runtime.begin_frame(accepted))

        cancelled = self._run_request("post", "/workout/cancel")
        self.assertEqual(cancelled.status_code, 200)
        with dashboard.app.app_context():
            persisted = CompletedWorkoutSession.query.filter_by(
                runtime_session_id=runtime_id
            ).one()
            self.assertEqual(persisted.status, "cancelled")
            self.assertEqual(persisted.workout_plan_id, plan_id)
            self.assertEqual(len(persisted.exercise_results), 1)
            self.assertEqual(persisted.exercise_results[0].side, "right")
            self.assertEqual(persisted.exercise_results[0].completed_repetitions, 1)

    def test_selection_page_displays_server_defined_workout_preset_and_legacy_mode(self):
        response = self._run_request("get", "/selection?patient_id=8")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Legacy Assessment", html)
        self.assertIn("Workout Mode", html)
        self.assertIn("Right Bicep Curl", html)
        self.assertIn("Left Bicep Curl", html)
        self.assertIn("data-preset-id=\"bilateral_bicep_curl_2\"", html)
        self.assertIn("data-patient-id=\"8\"", html)

    def test_live_page_shows_authoritative_mode_and_active_exercise(self):
        legacy = self._new_session()
        with dashboard.assessment_state_lock:
            dashboard.session = legacy
        legacy_html = self._run_request("get", "/assessment").get_data(as_text=True)
        self.assertIn("data-workout-mode=\"false\"", legacy_html)
        self.assertIn("Legacy Assessment", legacy_html)
        self.assertIn("<h1 id=\"exercise-name\">Left Bicep Curl</h1>", legacy_html)
        self.assertIn('<div class="assessment-controls" >', legacy_html)

        with dashboard.assessment_state_lock:
            dashboard.session = None
        started = self._run_request(
            "post",
            "/workout/start",
            json={"preset_id": "bilateral_bicep_curl_2", "patient_id": 8},
        )
        self.assertEqual(started.status_code, 201)
        workout_html = self._run_request("get", "/assessment").get_data(as_text=True)
        self.assertIn("data-workout-mode=\"true\"", workout_html)
        self.assertIn("Workout Session", workout_html)
        self.assertIn("<h1 id=\"exercise-name\">Right Bicep Curl</h1>", workout_html)
        self.assertIn('id="workout-hud"', workout_html)
        self.assertIn('id="workout-cancel"', workout_html)
        self.assertIn('<div class="assessment-controls" hidden>', workout_html)

    def test_workout_and_legacy_modes_cannot_overwrite_each_other(self):
        with dashboard.assessment_state_lock:
            dashboard.session = self._new_session()
        conflict = self._run_request(
            "post",
            "/workout/start",
            json={"preset_id": "bilateral_bicep_curl_2", "patient_id": 8},
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertIsNotNone(dashboard.session)
        with dashboard.assessment_state_lock:
            dashboard.session = None

        started = self._run_request(
            "post",
            "/workout/start",
            json={"preset_id": "bilateral_bicep_curl_2", "patient_id": 8},
        )
        self.assertEqual(started.status_code, 201)
        legacy_conflict = self._run_request(
            "post", "/assessment",
            data={"exercise": "LEFT_BICEP_CURL", "patient_id": 8}
        )
        self.assertEqual(legacy_conflict.status_code, 409)
        self.assertIsNone(dashboard.session)

    def test_legacy_assessment_still_starts_in_legacy_mode(self):
        response = self._run_request(
            "post", "/assessment",
            data={"exercise": "LEFT_BICEP_CURL", "patient_id": 8}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(dashboard.runtime_mode, dashboard.RuntimeMode.LEGACY_ASSESSMENT)
        self.assertEqual(dashboard.session.profile.display_name, "Left Bicep Curl")
        self.assertEqual(_test_pose.side, "Left")


if __name__ == "__main__":
    unittest.main()
