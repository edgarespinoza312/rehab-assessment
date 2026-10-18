import unittest
import tempfile
import math
from unittest.mock import Mock

import numpy as np

from core.models import Joint, JointType, Skeleton
from core.perception import (
    MediaPipeBackend,
    PoseStatus,
    ReadinessState,
    YoloTensorRTBackend,
    create_perception_backend,
    selected_backend_name,
)
from core.perception.base import (
    PerceptionResult,
    is_rejected_experimental_result,
    is_rejected_result,
)
from core.perception.identity import IdentityState
from core.performance import PerformanceMonitor
from core.perception.quality import validate_landmarks
from core.perception.yolo_tensorrt_backend import (
    COCO_KEYPOINTS,
    LetterboxInfo,
    decode_output,
    letterbox,
)


def valid_keypoints():
    return {
        "left_shoulder": (420.0, 120.0, 0.9),
        "right_shoulder": (220.0, 120.0, 0.9),
        "left_elbow": (450.0, 220.0, 0.9),
        "right_elbow": (230.0, 220.0, 0.9),
        "left_wrist": (470.0, 320.0, 0.9),
        "right_wrist": (240.0, 320.0, 0.9),
    }


def calibrated_identity(side="right", **kwargs):
    state = IdentityState(**kwargs)
    state.begin_calibration(side)
    state.calibrated_side = side
    state.calibration_stage = "ready"
    state.calibration_reason = "calibrated"
    return state


def skeleton_from_keypoints(points=None, visibility=0.9):
    points = valid_keypoints() if points is None else points
    skeleton = Skeleton()
    for name, joint_type in {
        "left_shoulder": JointType.LEFT_SHOULDER,
        "right_shoulder": JointType.RIGHT_SHOULDER,
        "left_elbow": JointType.LEFT_ELBOW,
        "right_elbow": JointType.RIGHT_ELBOW,
        "left_wrist": JointType.LEFT_WRIST,
        "right_wrist": JointType.RIGHT_WRIST,
    }.items():
        if name not in points:
            continue
        x, y, score = points[name]
        skeleton.add_joint(Joint(
            name=joint_type, x=x / 640, y=y / 480,
            visibility=visibility if visibility is not None else score,
            confidence=0.123,
        ))
    return skeleton


class PerceptionBackendTests(unittest.TestCase):
    @staticmethod
    def _detected_output():
        locations = {
            "nose": (320.0, 60.0),
            "left_eye": (330.0, 55.0),
            "right_eye": (310.0, 55.0),
            "left_ear": (340.0, 65.0),
            "right_ear": (300.0, 65.0),
            "left_shoulder": (420.0, 120.0),
            "right_shoulder": (220.0, 120.0),
            "left_elbow": (450.0, 220.0),
            "right_elbow": (230.0, 220.0),
            "left_wrist": (470.0, 320.0),
            "right_wrist": (240.0, 320.0),
            "left_hip": (420.0, 300.0),
            "right_hip": (220.0, 300.0),
            "left_knee": (420.0, 380.0),
            "right_knee": (220.0, 380.0),
            "left_ankle": (420.0, 450.0),
            "right_ankle": (220.0, 450.0),
        }
        output = np.zeros((1, 56, 8400), dtype=np.float32)
        output[0, :5, 0] = (320.0, 320.0, 200.0, 300.0, 0.9)
        points = []
        for name in COCO_KEYPOINTS:
            x, y = locations[name]
            points.extend((x, y + 80.0, 0.9))
        output[0, 5:, 0] = points
        return output

    def _run_tensor_rt_candidate(self, output):
        class FakeSession:
            def infer(self, tensor):
                return output, {
                    "h2d_ms": 0.1,
                    "inference_ms": 1.0,
                    "d2h_ms": 0.1,
                }

            def close(self):
                pass

        with tempfile.NamedTemporaryFile(suffix=".engine") as engine_file:
            backend = YoloTensorRTBackend(
                engine_path=engine_file.name,
                session_factory=lambda _: FakeSession(),
                identity_state=calibrated_identity("left", bootstrap_frames=1),
            )
            _, skeleton = backend.process(
                np.zeros((480, 640, 3), dtype=np.uint8),
                timestamp=1.0,
                frame_number=1,
                exercise_side="left",
            )
            result = backend.last_result
            backend.close()
            return result, skeleton

    def test_tensorrt_person_score_boundary_and_rejected_frame_contract(self):
        for label, score, accepted, state in (
            ("below", np.nextafter(np.float32(0.25), np.float32(0.0)), False,
             ReadinessState.NO_PERSON),
            ("exact", np.float32(0.25), True, ReadinessState.READY),
            ("above", np.nextafter(np.float32(0.25), np.float32(1.0)), True,
             ReadinessState.READY),
        ):
            with self.subTest(label=label):
                output = self._detected_output()
                output[0, 4, 0] = score
                result, skeleton = self._run_tensor_rt_candidate(output)
                self.assertEqual(result.state, state)
                self.assertEqual(result.pose_valid, accepted)
                self.assertEqual(skeleton is not None, accepted)
                if not accepted:
                    self.assertIsNone(result.skeleton)
                    self.assertFalse(result.tracking)

    def test_tensorrt_general_identity_confidence_boundary(self):
        right_wrist_index = COCO_KEYPOINTS.index("right_wrist")
        confidence_channel = 5 + right_wrist_index * 3 + 2
        for label, score, accepted in (
            ("below", np.nextafter(np.float32(0.50), np.float32(0.0)), False),
            ("exact", np.float32(0.50), True),
            ("above", np.nextafter(np.float32(0.50), np.float32(1.0)), True),
        ):
            with self.subTest(label=label):
                output = self._detected_output()
                output[0, confidence_channel, 0] = score
                result, skeleton = self._run_tensor_rt_candidate(output)
                self.assertEqual(result.state, (
                    ReadinessState.READY if accepted else ReadinessState.LOW_CONFIDENCE
                ))
                self.assertEqual(result.pose_valid, accepted)
                self.assertEqual(skeleton is not None, accepted)
                if not accepted:
                    self.assertIsNone(result.skeleton)
                    self.assertFalse(result.tracking)

    def test_active_side_confidence_boundary_and_float32_representation(self):
        # The shared rule accepts the mathematical decimal boundary itself.
        for label, score, accepted in (
            ("below", math.nextafter(0.65, 0.0), False),
            ("exact", 0.65, True),
            ("above", math.nextafter(0.65, 1.0), True),
        ):
            with self.subTest(policy_boundary=label):
                points = valid_keypoints()
                points.update({
                    "left_shoulder": (*points["left_shoulder"][:2], score),
                    "left_elbow": (*points["left_elbow"][:2], score),
                    "left_wrist": (*points["left_wrist"][:2], score),
                })
                decision = validate_landmarks(
                    points, 0.9, 640, 480, exercise_side="left"
                )
                self.assertEqual(decision.accepted, accepted)

        # TensorRT output is float32: its closest representable value below
        # 0.65 is strictly below the Python threshold, while the next value up
        # clears it. Both rejection cases must keep Skeleton hidden.
        float32_below = np.float32(0.65)
        self.assertLess(float(float32_below), 0.65)
        for label, score, accepted in (
            ("nearest_float32_below", float32_below, False),
            ("next_float32_above", np.nextafter(float32_below, np.float32(1.0)), True),
            ("lower_float32", np.nextafter(float32_below, np.float32(0.0)), False),
        ):
            with self.subTest(tensorrt_value=label):
                output = self._detected_output()
                for name in ("left_shoulder", "left_elbow", "left_wrist"):
                    channel = 5 + COCO_KEYPOINTS.index(name) * 3 + 2
                    output[0, channel, 0] = score
                result, skeleton = self._run_tensor_rt_candidate(output)
                self.assertEqual(result.pose_valid, accepted)
                self.assertEqual(skeleton is not None, accepted)
                self.assertEqual(result.state, (
                    ReadinessState.READY if accepted else ReadinessState.LOW_CONFIDENCE
                ))
                if not accepted:
                    self.assertIsNone(result.skeleton)
                    self.assertFalse(result.tracking)

    def test_tensorrt_calibrates_from_synthetic_baseline_bend_and_return(self):
        class FakeSession:
            output = PerceptionBackendTests._detected_output()

            def infer(self, tensor):
                return self.output, {
                    "h2d_ms": 0.1,
                    "inference_ms": 1.0,
                    "d2h_ms": 0.1,
                }

            def close(self):
                pass

        baseline_output = PerceptionBackendTests._detected_output()

        def set_left_wrist(output, x, y):
            channel = 5 + COCO_KEYPOINTS.index("left_wrist") * 3
            output[0, channel, 0] = x
            output[0, channel + 1, 0] = y + 80.0

        with tempfile.NamedTemporaryFile(suffix=".engine") as engine_file:
            backend = YoloTensorRTBackend(
                engine_path=engine_file.name,
                session_factory=lambda _: FakeSession(),
            )
            backend.begin_calibration("left")
            self.assertEqual(backend.calibration_status["stage"], "baseline")
            frame = np.zeros((480, 640, 3), dtype=np.uint8)

            def process_frame(frame_number, bent=False):
                output = baseline_output.copy()
                if bent:
                    set_left_wrist(output, 520.0, 220.0)
                FakeSession.output = output
                _, skeleton = backend.process(
                    frame,
                    timestamp=frame_number / 30.0,
                    frame_number=frame_number,
                    exercise_side="left",
                )
                self.assertIsNone(skeleton)
                self.assertIsNone(backend.last_result.skeleton)
                self.assertFalse(backend.last_result.pose_valid)
                return backend.calibration_status

            for frame_number in range(1, 4):
                status = process_frame(frame_number)
            self.assertEqual(status["stage"], "movement")

            for frame_number in range(4, 13):
                status = process_frame(frame_number, bent=True)
            self.assertEqual(status["stage"], "confirming")
            self.assertEqual(status["matching_frames"], 9)
            self.assertFalse(status["calibrated"])

            status = process_frame(13, bent=True)
            self.assertEqual(status["stage"], "return")
            self.assertEqual(status["matching_frames"], 10)
            self.assertFalse(status["calibrated"])

            status = process_frame(14)
            self.assertEqual(status["stage"], "return")
            self.assertEqual(status["matching_frames"], 10)
            self.assertFalse(status["calibrated"])
            process_frame(15)
            status = process_frame(16)
            self.assertEqual(status["stage"], "ready")
            self.assertEqual(status["side"], "left")
            self.assertTrue(status["calibrated"])

            # Calibration completes before tracking bootstrap exposes a pose.
            for frame_number in (17, 18):
                _, skeleton = backend.process(
                    frame, timestamp=frame_number / 30.0,
                    frame_number=frame_number, exercise_side="left",
                )
                self.assertIsNone(skeleton)
                self.assertFalse(backend.last_result.pose_valid)
            _, skeleton = backend.process(
                frame, timestamp=19 / 30.0,
                frame_number=19, exercise_side="left",
            )
            self.assertIsNotNone(skeleton)
            self.assertTrue(backend.last_result.pose_valid)
            self.assertEqual(backend.last_result.state, ReadinessState.READY)
            backend.close()

    def test_coco_keypoint_mapping_is_coco_17_order(self):
        self.assertEqual(
            COCO_KEYPOINTS,
            (
                "nose", "left_eye", "right_eye", "left_ear", "right_ear",
                "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
                "left_wrist", "right_wrist", "left_hip", "right_hip",
                "left_knee", "right_knee", "left_ankle", "right_ankle",
            ),
        )

    def test_letterbox_converts_bgr_to_rgb_float_chw_and_reverses_padding(self):
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        image[:, :, 2] = 255
        tensor, info = letterbox(image)
        self.assertEqual(tensor.shape, (1, 3, 640, 640))
        self.assertEqual(tensor.dtype, np.float32)
        self.assertAlmostEqual(float(tensor[0, 0, 80, 0]), 1.0)
        self.assertAlmostEqual(float(tensor[0, 2, 80, 0]), 0.0)
        self.assertEqual(info.padding_top, 80)

        output = np.zeros((1, 56, 8400), dtype=np.float32)
        output[0, 4, 0] = 0.9
        output[0, 5:, 0] = np.tile(
            np.array([320.0, 320.0, 0.9], dtype=np.float32), 17
        )
        decoded = decode_output(output, info)
        self.assertEqual(decoded["candidate_index"], 0)
        self.assertAlmostEqual(decoded["person_confidence"], 0.9)
        self.assertAlmostEqual(decoded["keypoints"]["nose"][0], 320.0)
        self.assertAlmostEqual(decoded["keypoints"]["nose"][1], 240.0)

    def test_decode_rejects_malformed_and_nonfinite_output(self):
        info = LetterboxInfo(640, 480, 640, 480, 1.0, 0, 80, 0, 80)
        with self.assertRaises(ValueError):
            decode_output(np.zeros((1, 56, 10), dtype=np.float32), info)
        output = np.zeros((1, 56, 8400), dtype=np.float32)
        output[0, 5, 0] = np.inf
        with self.assertRaises(ValueError):
            decode_output(output, info)

    def test_quality_checks_bounds_confidence_missing_and_nonfinite(self):
        landmarks = valid_keypoints()
        self.assertTrue(validate_landmarks(landmarks, 0.9, 640, 480).accepted)

        outside = dict(landmarks, right_wrist=(640.0, 320.0, 0.9))
        result = validate_landmarks(outside, 0.9, 640, 480)
        self.assertTrue(result.invalid)
        self.assertIn("landmark_out_of_bounds:right_wrist", result.reasons)

        optional_outside = dict(landmarks, nose=(-15.0, 10.0, 0.9))
        self.assertTrue(
            validate_landmarks(optional_outside, 0.9, 640, 480).accepted
        )

        weak = dict(landmarks, right_wrist=(240.0, 320.0, 0.3))
        result = validate_landmarks(weak, 0.9, 640, 480)
        self.assertFalse(result.accepted)
        self.assertFalse(result.invalid)

        missing = dict(landmarks)
        del missing["right_wrist"]
        self.assertTrue(validate_landmarks(missing, 0.9, 640, 480).invalid)

        nonfinite = dict(landmarks, right_wrist=(float("nan"), 320.0, 0.9))
        self.assertTrue(validate_landmarks(nonfinite, 0.9, 640, 480).invalid)
        infinite = dict(landmarks, right_wrist=(240.0, float("inf"), 0.9))
        self.assertTrue(validate_landmarks(infinite, 0.9, 640, 480).invalid)

        implausible = dict(
            landmarks,
            right_shoulder=(20.0, 20.0, 0.9),
            right_elbow=(50.0, 20.0, 0.9),
            right_wrist=(630.0, 470.0, 0.9),
        )
        result = validate_landmarks(implausible, 0.9, 640, 480)
        self.assertFalse(result.accepted)
        self.assertIn("implausible_right_forearm_length", result.reasons)

    def test_quality_gate_requires_the_active_exercise_side(self):
        landmarks = valid_keypoints()
        landmarks.update({
            "left_shoulder": (420.0, 120.0, 0.70),
            "left_elbow": (450.0, 220.0, 0.70),
            "left_wrist": (470.0, 320.0, 0.70),
            "right_shoulder": (220.0, 120.0, 0.60),
            "right_elbow": (230.0, 220.0, 0.60),
            "right_wrist": (240.0, 320.0, 0.60),
        })
        self.assertTrue(
            validate_landmarks(
                landmarks, 0.9, 640, 480, exercise_side="Left"
            ).accepted
        )
        right_result = validate_landmarks(
            landmarks, 0.9, 640, 480, exercise_side="right"
        )
        self.assertFalse(right_result.accepted)
        self.assertEqual(right_result.category, "low_confidence")
        self.assertIn("right_elbow", right_result.reasons[0])

    def test_identity_requires_stable_bootstrap_and_rejects_side_switch(self):
        state = calibrated_identity("right", bootstrap_frames=3)
        points = {name: point[:2] for name, point in valid_keypoints().items()}
        self.assertFalse(state.assess(points, 1, 1.0, 640, 480).accepted)
        self.assertFalse(state.assess(points, 2, 1.1, 640, 480).accepted)
        accepted = state.assess(points, 3, 1.2, 640, 480)
        self.assertTrue(accepted.accepted)
        self.assertFalse(accepted.ambiguous)

        switched = {
            name: (640.0 - point[0], point[1])
            for name, point in points.items()
        }
        rejected = state.assess(switched, 4, 1.3, 640, 480)
        self.assertFalse(rejected.accepted)
        self.assertIn("spatial_identity_switch", rejected.reasons)
        self.assertEqual(state.consecutive_ambiguous_frames, 1)

    def test_identity_reset_clears_temporal_state(self):
        state = calibrated_identity("right", bootstrap_frames=1)
        points = {name: point[:2] for name, point in valid_keypoints().items()}
        self.assertTrue(state.assess(points, 1, 1.0, 640, 480).accepted)
        state.reject(reason="test")
        state.reset()
        self.assertIsNone(state.established_assignment)
        self.assertEqual(state.consecutive_ambiguous_frames, 0)
        self.assertEqual(state.consecutive_valid_frames, 0)
        self.assertIsNone(state.previous_frame_number)

    def test_invalid_frames_break_consecutive_identity_streaks(self):
        state = calibrated_identity("right", bootstrap_frames=1)
        points = {name: point[:2] for name, point in valid_keypoints().items()}
        self.assertTrue(state.assess(points, 1, 1.0, 640, 480).accepted)
        state.mark_invalid()
        self.assertEqual(state.consecutive_valid_frames, 0)
        self.assertEqual(state.consecutive_ambiguous_frames, 0)

    def test_invalid_extreme_single_frame_jump_is_rejected(self):
        state = calibrated_identity("right", bootstrap_frames=1)
        points = {name: point[:2] for name, point in valid_keypoints().items()}
        self.assertTrue(state.assess(points, 1, 1.0, 640, 480).accepted)
        jumped = {
            name: (point[0] + 150.0, point[1])
            for name, point in points.items()
        }
        result = state.assess(jumped, 2, 1.1, 640, 480)
        self.assertFalse(result.accepted)
        self.assertIn("extreme_frame_to_frame_displacement", result.reasons)

    def test_identity_requires_named_side_movement_and_return_calibration(self):
        state = IdentityState(calibration_frames=10)
        state.begin_calibration("left")
        baseline = {
            name: point[:2] for name, point in valid_keypoints().items()
        }
        bent = dict(baseline)
        bent["left_wrist"] = (500.0, 220.0)

        for _ in range(state.calibration_baseline_frames):
            self.assertFalse(state.observe_calibration(baseline).accepted)
        self.assertEqual(state.calibration_stage, "movement")
        for _ in range(9):
            result = state.observe_calibration(bent)
            self.assertFalse(result.accepted)
            self.assertFalse(state.is_calibrated)
        state.observe_calibration(bent)
        self.assertEqual(state.calibration_stage, "return")
        self.assertFalse(state.is_calibrated)

        for _ in range(state.calibration_return_frames):
            result = state.observe_calibration(baseline)
            self.assertFalse(result.accepted)
        self.assertTrue(state.is_calibrated)
        self.assertEqual(state.calibrated_side, "left")

        self.assertFalse(state.assess(baseline, 1, 1.0, 640, 480).accepted)
        self.assertFalse(state.assess(baseline, 2, 1.1, 640, 480).accepted)
        self.assertTrue(state.assess(baseline, 3, 1.2, 640, 480).accepted)

    def test_identity_calibration_rejects_opposite_arm_motion(self):
        state = IdentityState(calibration_frames=2)
        state.begin_calibration("left")
        baseline = {name: point[:2] for name, point in valid_keypoints().items()}
        for _ in range(state.calibration_baseline_frames):
            state.observe_calibration(baseline)

        opposite_moved = dict(baseline)
        opposite_moved["right_wrist"] = (400.0, 220.0)
        result = state.observe_calibration(opposite_moved)
        self.assertFalse(result.accepted)
        self.assertEqual(state.calibration_matching_frames, 0)
        self.assertEqual(state.calibration_reason, "opposite_side_moved")
        self.assertFalse(state.is_calibrated)

    def test_identity_calibration_does_not_use_spatial_order_as_side_proof(self):
        state = IdentityState(calibration_frames=2)
        state.begin_calibration("left")
        baseline = {name: point[:2] for name, point in valid_keypoints().items()}
        swapped = {
            name: baseline[
                ("right_" + name[5:])
                if name.startswith("left_")
                else ("left_" + name[6:])
                if name.startswith("right_")
                else name
            ]
            for name in baseline
        }
        bent_wrong_semantics = dict(swapped)
        bent_wrong_semantics["right_wrist"] = (400.0, 220.0)
        for _ in range(state.calibration_baseline_frames):
            state.observe_calibration(swapped)
        result = state.observe_calibration(bent_wrong_semantics)
        self.assertFalse(result.accepted)
        self.assertEqual(state.calibration_reason, "opposite_side_moved")
        self.assertFalse(state.is_calibrated)

    def test_skeleton_maps_anatomical_semantics(self):
        from core.perception.yolo_tensorrt_backend import build_skeleton

        points = dict(valid_keypoints())
        points["right_hip"] = (220.0, 300.0, 0.9)
        points["left_hip"] = (420.0, 300.0, 0.9)
        skeleton = build_skeleton(points, 1.5, 7, 640, 480)
        right_elbow = skeleton.get_joint(JointType.RIGHT_ELBOW)
        self.assertEqual(right_elbow.position, (230 / 640, 220 / 480))
        self.assertEqual(skeleton.frame_number, 7)

    def test_default_and_invalid_backend_selection_use_mediapipe(self):
        self.assertEqual(selected_backend_name({}), "mediapipe")
        self.assertEqual(
            selected_backend_name({"REVALIV_PERCEPTION_BACKEND": "nonsense"}),
            "mediapipe",
        )
        selected = []
        backend = create_perception_backend(
            environ={"REVALIV_PERCEPTION_BACKEND": "mediapipe"},
            mediapipe_factory=lambda: selected.append("mediapipe") or "mp",
            yolo_factory=lambda: selected.append("yolo") or "yolo",
        )
        self.assertEqual(backend, "mp")
        self.assertEqual(selected, ["mediapipe"])

    def test_yolo_backend_selection_is_opt_in(self):
        selected = []
        backend = create_perception_backend(
            environ={"REVALIV_PERCEPTION_BACKEND": "yolo"},
            mediapipe_factory=lambda: selected.append("mediapipe") or "mp",
            yolo_factory=lambda: selected.append("yolo") or "yolo",
        )
        self.assertEqual(backend, "yolo")
        self.assertEqual(selected, ["yolo"])

    def test_gpu_backend_name_selects_tensor_rt_backend_without_fallback(self):
        selected = []

        def gpu_factory(**kwargs):
            selected.append(kwargs)
            return "gpu"

        backend = create_perception_backend(
            environ={"REVALIV_PERCEPTION_BACKEND": "gpu"},
            mediapipe_factory=lambda: self.fail("GPU must not fall back to MediaPipe"),
            yolo_factory=gpu_factory,
        )
        self.assertEqual(backend, "gpu")
        self.assertEqual(selected, [{"backend_name": "gpu"}])

    def test_invalid_yolo_engine_is_reported_and_fails_closed(self):
        backend = YoloTensorRTBackend(engine_path="/definitely/missing.engine")
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        annotated, skeleton = backend.process(frame, timestamp=1.0, frame_number=1)
        self.assertFalse(backend.available)
        self.assertEqual(backend.last_result.status, PoseStatus.INVALID)
        self.assertFalse(backend.last_result.pose_valid)
        self.assertIsNone(skeleton)
        self.assertEqual(annotated.shape, frame.shape)
        self.assertEqual(backend.last_result.diagnostics["reason"], "backend_unavailable")
        self.assertFalse(backend.runtime_diagnostics["gpu_initialized"])
        self.assertFalse(
            backend.last_result.diagnostics["gpu_inference_completed"]
        )

    def test_tensor_rt_preprocess_buffer_is_reused(self):
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        reusable = np.empty((1, 3, 640, 640), dtype=np.float32)
        tensor, _ = letterbox(image, output_buffer=reusable)
        self.assertIs(tensor, reusable)

    def test_backend_rejects_frames_until_named_side_calibration_finishes(self):
        class FakeSession:
            def infer(self, tensor):
                return PerceptionBackendTests._detected_output(), {
                    "h2d_ms": 0.1,
                    "inference_ms": 1.0,
                    "d2h_ms": 0.1,
                }

            def close(self):
                pass

        identity = IdentityState()
        identity.begin_calibration("left")
        with tempfile.NamedTemporaryFile(suffix=".engine") as engine_file:
            backend = YoloTensorRTBackend(
                engine_path=engine_file.name,
                session_factory=lambda _: FakeSession(),
                identity_state=identity,
            )
            _, skeleton = backend.process(
                np.zeros((480, 640, 3), dtype=np.uint8),
                frame_number=1,
                exercise_side="left",
            )
            self.assertIsNone(skeleton)
            self.assertEqual(backend.last_result.status, PoseStatus.AMBIGUOUS)
            self.assertEqual(
                backend.last_result.diagnostics["rejection_category"],
                "identity_calibration_pending",
            )
            self.assertEqual(
                backend.last_result.diagnostics["identity_calibration"]["stage"],
                "baseline",
            )
            self.assertEqual(backend.accepted_frames, 0)
            self.assertEqual(backend.rejected_frames, 1)
            backend.close()

    def test_backend_rejects_a_different_side_than_the_calibrated_side(self):
        class FakeSession:
            def infer(self, tensor):
                raise AssertionError("Mismatched side must fail before inference")

            def close(self):
                pass

        identity = calibrated_identity("left")
        with tempfile.NamedTemporaryFile(suffix=".engine") as engine_file:
            backend = YoloTensorRTBackend(
                engine_path=engine_file.name,
                session_factory=lambda _: FakeSession(),
                identity_state=identity,
            )
            _, skeleton = backend.process(
                np.zeros((480, 640, 3), dtype=np.uint8),
                frame_number=1,
                exercise_side="right",
            )
            self.assertIsNone(skeleton)
            self.assertEqual(backend.last_result.status, PoseStatus.INVALID)
            self.assertEqual(
                backend.last_result.diagnostics["rejection_category"],
                "identity_ambiguity",
            )
            self.assertEqual(backend.inference_count, 0)
            backend.close()

    def test_yolo_backend_gates_identity_then_builds_typed_skeleton(self):
        class FakeSession:
            def infer(self, tensor):
                self.input_shape = tensor.shape
                return PerceptionBackendTests._detected_output(), {
                    "h2d_ms": 0.1,
                    "inference_ms": 1.0,
                    "d2h_ms": 0.1,
                }

            def close(self):
                pass

        with tempfile.NamedTemporaryFile(suffix=".engine") as engine_file:
            backend = YoloTensorRTBackend(
                engine_path=engine_file.name,
                session_factory=lambda _: FakeSession(),
                identity_state=calibrated_identity("right"),
            )
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            for frame_number in (1, 2):
                _, skeleton = backend.process(
                    frame, timestamp=frame_number / 30, frame_number=frame_number
                )
                self.assertIsNone(skeleton)
                self.assertEqual(backend.last_result.status, PoseStatus.AMBIGUOUS)
            performance = PerformanceMonitor(enabled=True)
            annotated, skeleton = backend.process(
                frame,
                timestamp=0.1,
                frame_number=3,
                performance=performance,
            )
            self.assertIsNotNone(skeleton)
            self.assertEqual(annotated.shape, frame.shape)
            self.assertEqual(backend.last_result.status, PoseStatus.VALID)
            self.assertEqual(backend.last_result.backend, "yolo")
            self.assertAlmostEqual(
                skeleton.get_joint(JointType.RIGHT_ELBOW).x,
                230 / 640,
            )
            self.assertEqual(skeleton.frame_number, 3)
            snapshot = performance.snapshot()
            self.assertEqual(snapshot["counters"]["yolo_valid_frames"], 1)
            self.assertIn("yolo_tensorrt_inference", snapshot["stages"])
            for stage in (
                "perception_preprocessing",
                "model_inference",
                "perception_decoding_adaptation",
                "skeleton_construction",
                "exercise_readiness",
            ):
                self.assertIn(stage, snapshot["stages"])
            backend.close()

    def test_active_left_and_right_arm_confidence_is_gated_independently(self):
        class FakeSession:
            def __init__(self):
                self.output = PerceptionBackendTests._detected_output()
                for keypoint_index, name in enumerate(COCO_KEYPOINTS):
                    if name.startswith("left_"):
                        self.output[0, 5 + keypoint_index * 3 + 2, 0] = 0.70
                    elif name.startswith("right_"):
                        self.output[0, 5 + keypoint_index * 3 + 2, 0] = 0.60

            def infer(self, tensor):
                return self.output, {
                    "h2d_ms": 0.1,
                    "inference_ms": 1.0,
                    "d2h_ms": 0.1,
                }

            def close(self):
                pass

        with tempfile.NamedTemporaryFile(suffix=".engine") as engine_file:
            left_backend = YoloTensorRTBackend(
                engine_path=engine_file.name,
                session_factory=lambda _: FakeSession(),
                identity_state=calibrated_identity("left", bootstrap_frames=1),
            )
            right_backend = YoloTensorRTBackend(
                engine_path=engine_file.name,
                session_factory=lambda _: FakeSession(),
                identity_state=calibrated_identity("right", bootstrap_frames=1),
            )
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            _, left_skeleton = left_backend.process(
                frame, frame_number=1, exercise_side="left"
            )
            _, right_skeleton = right_backend.process(
                frame, frame_number=1, exercise_side="right"
            )
            self.assertIsNotNone(left_skeleton)
            self.assertIsNone(right_skeleton)
            self.assertEqual(
                right_backend.last_result.diagnostics["rejection_category"],
                "low_confidence",
            )
            left_backend.close()
            right_backend.close()

    def test_gpu_backend_preserves_anatomical_left_and_right_mapping(self):
        from core.perception.yolo_tensorrt_backend import build_skeleton

        points = dict(valid_keypoints())
        points["left_hip"] = (420.0, 300.0, 0.9)
        points["right_hip"] = (220.0, 300.0, 0.9)
        skeleton = build_skeleton(points, 1.5, 7, 640, 480)
        self.assertEqual(
            skeleton.get_joint(JointType.LEFT_ELBOW).position,
            (450 / 640, 220 / 480),
        )
        self.assertEqual(
            skeleton.get_joint(JointType.RIGHT_ELBOW).position,
            (230 / 640, 220 / 480),
        )

    def test_yolo_inference_exception_returns_invalid_without_skeleton(self):
        class FailingSession:
            def infer(self, tensor):
                raise RuntimeError("inference failed")

            def close(self):
                pass

        with tempfile.NamedTemporaryFile(suffix=".engine") as engine_file:
            backend = YoloTensorRTBackend(
                engine_path=engine_file.name,
                session_factory=lambda _: FailingSession(),
            )
            _, skeleton = backend.process(
                np.zeros((480, 640, 3), dtype=np.uint8),
                timestamp=1.0,
                frame_number=1,
            )
            self.assertIsNone(skeleton)
            self.assertEqual(backend.last_result.status, PoseStatus.INVALID)
            self.assertEqual(
                backend.last_result.diagnostics["reason"],
                "inference_or_decode_failure",
            )

    def test_invalid_results_from_each_backend_are_excluded_from_analysis(self):
        rejected = PerceptionResult(
            skeleton=None,
            status=PoseStatus.AMBIGUOUS,
            backend="gpu",
            timestamp=1.0,
            frame_number=1,
        )
        accepted = PerceptionResult(
            skeleton=Mock(),
            status=PoseStatus.VALID,
            backend="gpu",
            timestamp=1.0,
            frame_number=2,
        )
        legacy_missing_pose = PerceptionResult(
            skeleton=None,
            status=PoseStatus.INVALID,
            backend="mediapipe",
            timestamp=1.0,
            frame_number=3,
        )
        self.assertTrue(is_rejected_result(rejected))
        self.assertFalse(is_rejected_result(accepted))
        self.assertTrue(is_rejected_result(legacy_missing_pose))
        self.assertTrue(is_rejected_result(None))
        # Keep the old helper name compatible while applying shared semantics.
        self.assertTrue(is_rejected_experimental_result(legacy_missing_pose))

    def test_mediapipe_wrapper_preserves_engine_return_and_invocation(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        annotated = object()
        skeleton = skeleton_from_keypoints()
        engine = Mock()
        engine.process.return_value = (annotated, skeleton)
        backend = MediaPipeBackend(
            engine, identity_state=calibrated_identity("left", bootstrap_frames=1)
        )
        performance = PerformanceMonitor(enabled=True)
        returned = backend.process(
            frame, timestamp=12.5, frame_number=14, performance=performance,
            exercise_side="left",
        )
        self.assertIs(returned[0], annotated)
        self.assertIs(returned[1], skeleton)
        engine.process.assert_called_once_with(
            frame, timestamp=12.5, frame_number=14, performance=performance,
        )
        self.assertTrue(backend.last_result.pose_valid)
        self.assertIn("perception_decoding_adaptation", performance.snapshot()["stages"])
        self.assertIn("exercise_readiness", performance.snapshot()["stages"])
        self.assertEqual(backend.last_result.state, ReadinessState.READY)
        self.assertEqual((skeleton.timestamp, skeleton.frame_number), (12.5, 14))

    def test_mediapipe_empty_skeleton_is_rejected_by_shared_contract(self):
        engine = Mock()
        empty_skeleton = Mock()
        empty_skeleton.joint_count.return_value = 0
        engine.process.return_value = (object(), empty_skeleton)
        backend = MediaPipeBackend(engine)

        backend.process(np.zeros((480, 640, 3), dtype=np.uint8), timestamp=1.0, frame_number=3)

        self.assertEqual(backend.last_result.status, PoseStatus.INVALID)
        self.assertEqual(backend.last_result.state, ReadinessState.NO_PERSON)
        self.assertFalse(backend.last_result.pose_valid)
        self.assertTrue(is_rejected_result(backend.last_result))


    def test_shared_gate_uses_profile_active_side_and_rejects_weak_opposite_side(self):
        class FakeEngine:
            def process(self, frame, **kwargs):
                skeleton = skeleton_from_keypoints()
                for joint_type in (
                    JointType.RIGHT_SHOULDER, JointType.RIGHT_ELBOW, JointType.RIGHT_WRIST
                ):
                    skeleton.get_joint(joint_type).visibility = 0.60
                return frame.copy(), skeleton

            def close(self):
                pass

        backend = MediaPipeBackend(
            FakeEngine(), identity_state=calibrated_identity("left", bootstrap_frames=1)
        )
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        _, result = backend.process(frame, frame_number=1, exercise_side="left")
        self.assertIsNotNone(result)
        self.assertEqual(backend.last_result.state, ReadinessState.READY)
        # Same raw pose, with the right arm active, must fail the same shared gate.
        backend = MediaPipeBackend(
            FakeEngine(), identity_state=calibrated_identity("right", bootstrap_frames=1)
        )
        _, result = backend.process(frame, frame_number=1, exercise_side="right")
        self.assertIsNone(result)
        self.assertEqual(backend.last_result.state, ReadinessState.LOW_CONFIDENCE)

    def test_shared_gate_states_and_rejected_frames_never_expose_skeleton(self):
        from core.perception.readiness import AdaptedPose, ExerciseReadiness

        gate = ExerciseReadiness()
        gate.begin_calibration("left")
        result = gate.evaluate(
            None, backend="mediapipe", timestamp=1, frame_number=2,
            width=640, height=480, exercise_side="left",
        )
        self.assertEqual(result.state, ReadinessState.NO_PERSON)
        self.assertIsNone(result.skeleton)

        weak = dict(valid_keypoints(), left_elbow=(450.0, 220.0, 0.40))
        candidate = AdaptedPose(
            skeleton=skeleton_from_keypoints(weak), keypoints=weak,
            native_confidence={"source": "test", "value": 0.40},
        )
        result = gate.evaluate(
            candidate, backend="mediapipe", timestamp=1, frame_number=3,
            width=640, height=480, exercise_side="left",
        )
        self.assertEqual(result.state, ReadinessState.LOW_CONFIDENCE)
        self.assertIsNone(result.skeleton)
        self.assertFalse(result.tracking)

        sparse = dict(valid_keypoints())
        del sparse["right_wrist"]
        candidate = AdaptedPose(
            skeleton=skeleton_from_keypoints(sparse), keypoints=sparse,
        )
        result = gate.evaluate(
            candidate, backend="mediapipe", timestamp=1, frame_number=4,
            width=640, height=480, exercise_side="left",
        )
        self.assertEqual(result.state, ReadinessState.POOR_QUALITY)
        self.assertIsNone(result.skeleton)

    def test_common_calibration_interface_and_calibration_required_state(self):
        class FakeEngine:
            def process(self, frame, **kwargs):
                return frame.copy(), skeleton_from_keypoints()
            def close(self):
                pass

        backend = MediaPipeBackend(FakeEngine())
        backend.begin_calibration("left")
        self.assertEqual(backend.calibration_status["stage"], "baseline")
        _, skeleton = backend.process(
            np.zeros((480, 640, 3), dtype=np.uint8),
            timestamp=4.25, frame_number=9, exercise_side="left",
        )
        self.assertIsNone(skeleton)
        self.assertEqual(backend.last_result.state, ReadinessState.CALIBRATION_REQUIRED)
        self.assertIsNone(backend.last_result.skeleton)
        self.assertEqual(backend.last_result.timestamp, 4.25)
        self.assertEqual(backend.last_result.frame_number, 9)

    def test_common_reset_calibration_clears_identity_and_stale_backend_result(self):
        mp_identity = calibrated_identity("left")
        mp_backend = MediaPipeBackend(object(), identity_state=mp_identity)
        mp_backend.last_result = object()
        mp_backend.reset_calibration()
        self.assertIsNone(mp_backend.last_result)
        self.assertEqual(mp_backend.calibration_status["stage"], "required")

        class FakeSession:
            def close(self):
                pass

        trt_identity = calibrated_identity("right")
        with tempfile.NamedTemporaryFile(suffix=".engine") as engine_file:
            trt_backend = YoloTensorRTBackend(
                engine_path=engine_file.name,
                session_factory=lambda _: FakeSession(),
                identity_state=trt_identity,
            )
            trt_backend.last_result = object()
            trt_backend.reset_calibration()
            self.assertIsNone(trt_backend.last_result)
            self.assertEqual(trt_backend.calibration_status["stage"], "required")
            trt_backend.close()

    def test_mediapipe_and_tensorrt_expose_equivalent_ready_contract(self):
        class FakeEngine:
            def process(self, frame, **kwargs):
                return frame.copy(), skeleton_from_keypoints()
            def close(self):
                pass

        class FakeSession:
            def infer(self, tensor):
                return PerceptionBackendTests._detected_output(), {
                    "h2d_ms": 0.1, "inference_ms": 1.0, "d2h_ms": 0.1,
                }
            def close(self):
                pass

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mp = MediaPipeBackend(
            FakeEngine(), identity_state=calibrated_identity("left", bootstrap_frames=1)
        )
        with tempfile.NamedTemporaryFile(suffix=".engine") as engine_file:
            trt = YoloTensorRTBackend(
                engine_path=engine_file.name, session_factory=lambda _: FakeSession(),
                identity_state=calibrated_identity("left", bootstrap_frames=1),
            )
            _, mp_skeleton = mp.process(
                frame, timestamp=2.5, frame_number=77, exercise_side="left"
            )
            _, trt_skeleton = trt.process(
                frame, timestamp=2.5, frame_number=77, exercise_side="left"
            )
            for backend, skeleton in ((mp, mp_skeleton), (trt, trt_skeleton)):
                self.assertEqual(backend.last_result.state, ReadinessState.READY)
                self.assertTrue(backend.last_result.tracking)
                self.assertIsNotNone(skeleton)
                self.assertEqual((skeleton.timestamp, skeleton.frame_number), (2.5, 77))
            for joint_name, score in mp.last_result.quality[
                "required_joint_confidence"
            ].items():
                self.assertAlmostEqual(
                    score, trt.last_result.quality["required_joint_confidence"][joint_name]
                )
            self.assertEqual(
                mp_skeleton.get_joint(JointType.LEFT_ELBOW).position,
                trt_skeleton.get_joint(JointType.LEFT_ELBOW).position,
            )
            self.assertEqual(
                mp.last_result.diagnostics["native_confidence"]["source"],
                "mediapipe_visibility",
            )
            self.assertEqual(
                trt.last_result.diagnostics["native_confidence"]["source"],
                "yolov8_pose_keypoint_confidence",
            )
            trt.close()

    def test_native_visibility_is_not_rescaled_and_side_mismatch_is_shared_state(self):
        from core.perception.readiness import AdaptedPose

        skeleton = skeleton_from_keypoints()
        for joint in skeleton.joints.values():
            joint.visibility = 0.72
            joint.confidence = 0.13
        candidate = AdaptedPose.from_skeleton(skeleton, 640, 480)
        self.assertAlmostEqual(candidate.keypoints["left_elbow"][2], 0.72)
        self.assertAlmostEqual(
            candidate.native_confidence["joints"]["left_elbow"]["confidence"], 0.13
        )

        from core.perception.readiness import ExerciseReadiness
        gate = ExerciseReadiness(calibrated_identity("left"))
        mismatch = gate.reject_side_mismatch(
            backend="mediapipe", timestamp=3, frame_number=8, exercise_side="right"
        )
        self.assertEqual(mismatch.state, ReadinessState.IDENTITY_AMBIGUOUS)
        self.assertIsNone(mismatch.skeleton)


if __name__ == "__main__":
    unittest.main()
