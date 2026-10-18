import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from core.analyzers.compensation_analyzer import CompensationAnalyzer
from core.analyzers.joint_analyzer import JointAnalyzer
from core.analyzers.stability_analyzer import StabilityAnalyzer
from core.analyzers.symmetry_analyzer import SymmetryAnalyzer
from core.analyzers.temporal_analyzer import TemporalAnalyzer
from core.biomechanics import BiomechanicsEngine
from core.assessment import AssessmentEngine
from core.exercise import ExerciseEngine
from core.exercise_catalog import get_exercise_profile
from core.models import (
    ExercisePhase,
    ExerciseState,
    ExerciseType,
    Joint,
    JointType,
    MovementMetrics,
    Skeleton,
)
from core.performance import PerformanceMonitor
from core.pose import LANDMARK_MAP, PoseEngine
from scripts.pose_benchmark_metrics import BicepCurlDiagnostics


def media_pipe_results(landmarks):
    return SimpleNamespace(
        pose_landmarks=SimpleNamespace(landmark=landmarks)
    )


def synthetic_landmarks():
    return [
        SimpleNamespace(
            x=index / 100.0,
            y=index / 200.0,
            z=index / 300.0,
            visibility=0.8,
        )
        for index in range(33)
    ]


def add_joint(skeleton, kind, x, y, visibility=1.0):
    skeleton.add_joint(
        Joint(
            name=kind,
            x=x,
            y=y,
            visibility=visibility,
        )
    )


def add_arm(skeleton, side, angle_degrees, visibility=1.0):
    shoulder_type = getattr(JointType, f"{side}_SHOULDER")
    elbow_type = getattr(JointType, f"{side}_ELBOW")
    wrist_type = getattr(JointType, f"{side}_WRIST")
    elbow_x = 0.25 if side == "LEFT" else 0.75
    elbow_y = 0.5
    radians = math.radians(angle_degrees)
    add_joint(skeleton, shoulder_type, elbow_x + 1.0, elbow_y, visibility)
    add_joint(skeleton, elbow_type, elbow_x, elbow_y, visibility)
    add_joint(
        skeleton,
        wrist_type,
        elbow_x + math.cos(radians),
        elbow_y + math.sin(radians),
        visibility,
    )


def add_shoulders(skeleton, left=(0.4, 0.3), right=(0.6, 0.3)):
    add_joint(skeleton, JointType.LEFT_SHOULDER, *left)
    add_joint(skeleton, JointType.RIGHT_SHOULDER, *right)


class SkeletonConstructionTests(unittest.TestCase):
    def setUp(self):
        self.pose = PoseEngine.__new__(PoseEngine)

    def test_known_landmark_mapping_and_coordinates(self):
        landmarks = synthetic_landmarks()
        skeleton = self.pose._build_skeleton(
            media_pipe_results(landmarks),
            timestamp=123.5,
            frame_number=17,
        )

        self.assertEqual(
            skeleton.get_joint(JointType.LEFT_SHOULDER).position_3d,
            (0.11, 0.055, 0.11 / 3),
        )
        self.assertEqual(
            skeleton.get_joint(JointType.RIGHT_ELBOW).position,
            (0.14, 0.07),
        )
        self.assertEqual(
            skeleton.get_joint(JointType.RIGHT_ELBOW).visibility,
            0.8,
        )
        self.assertEqual(skeleton.timestamp, 123.5)
        self.assertEqual(skeleton.frame_number, 17)
        self.assertEqual(len(LANDMARK_MAP), 17)

    def test_derived_midpoints_and_copies_propagate_coordinates(self):
        landmarks = synthetic_landmarks()
        landmarks[11].x, landmarks[11].y, landmarks[11].z = 0.2, 0.2, 0.2
        landmarks[12].x, landmarks[12].y, landmarks[12].z = 0.6, 0.4, 0.4
        landmarks[11].visibility = 0.9
        landmarks[12].visibility = 0.7

        skeleton = self.pose._build_skeleton(media_pipe_results(landmarks))

        center = skeleton.get_joint(JointType.SHOULDER_CENTER)
        for actual, expected in zip(center.position_3d, (0.4, 0.3, 0.3)):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(center.visibility, 0.7)

        left_hand = skeleton.get_joint(JointType.LEFT_HAND)
        left_wrist = skeleton.get_joint(JointType.LEFT_WRIST)
        self.assertEqual(left_hand.position_3d, left_wrist.position_3d)
        self.assertEqual(left_hand.visibility, left_wrist.visibility)
        self.assertEqual(left_hand.confidence, left_wrist.confidence)

    def test_absent_and_short_landmark_inputs_leave_missing_joints_absent(self):
        empty = self.pose._build_skeleton(
            SimpleNamespace(pose_landmarks=None),
            timestamp=4.0,
            frame_number=8,
        )
        self.assertEqual(empty.joint_count(), 0)
        self.assertEqual((empty.timestamp, empty.frame_number), (4.0, 8))

        short = self.pose._build_skeleton(
            media_pipe_results(synthetic_landmarks()[:14])
        )
        self.assertIsNone(short.get_joint(JointType.RIGHT_ELBOW))
        self.assertIsNone(short.get_joint(JointType.RIGHT_UPPER_ARM))
        self.assertIsNotNone(short.get_joint(JointType.LEFT_SHOULDER))

    def test_metadata_defaults_preserve_existing_call_compatibility(self):
        skeleton = self.pose._build_skeleton(
            media_pipe_results(synthetic_landmarks())
        )
        self.assertEqual(skeleton.timestamp, 0.0)
        self.assertEqual(skeleton.frame_number, 0)

    def test_process_propagates_capture_metadata_and_stage_timings(self):
        results = SimpleNamespace(pose_landmarks=None)
        self.pose.pose = SimpleNamespace(
            process=lambda rgb_frame: results
        )
        monitor = PerformanceMonitor(enabled=True)

        _, skeleton = self.pose.process(
            np.zeros((4, 4, 3), dtype=np.uint8),
            timestamp=42.25,
            frame_number=91,
            performance=monitor,
        )

        self.assertEqual(skeleton.timestamp, 42.25)
        self.assertEqual(skeleton.frame_number, 91)
        plain_engine = PoseEngine.__new__(PoseEngine)
        plain_engine.pose = SimpleNamespace(process=lambda rgb_frame: results)
        _, plain_skeleton = plain_engine.process(
            np.zeros((4, 4, 3), dtype=np.uint8), timestamp=42.25, frame_number=91
        )
        self.assertEqual(
            skeleton.joints,
            plain_skeleton.joints,
        )
        self.assertEqual(
            set(monitor.snapshot()["stages"]),
            {"model_inference", "perception_preprocessing", "skeleton_construction"},
        )


class PoseConfigurationTests(unittest.TestCase):
    def test_default_configuration_matches_existing_production_values(self):
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("core.pose.mp.solutions.pose.Pose") as pose_model,
        ):
            engine = PoseEngine()

        self.assertEqual(
            engine.configuration,
            {
                "static_image_mode": False,
                "model_complexity": 1,
                "smooth_landmarks": True,
                "enable_segmentation": False,
                "min_detection_confidence": 0.5,
                "min_tracking_confidence": 0.5,
            },
        )
        pose_model.assert_called_once_with(**engine.configuration)

    def test_developer_environment_overrides_only_selected_settings(self):
        with (
            patch.dict(
                "os.environ",
                {
                    "REVALIV_POSE_COMPLEXITY": "0",
                    "REVALIV_POSE_SMOOTHING": "0",
                },
                clear=True,
            ),
            patch("core.pose.mp.solutions.pose.Pose"),
        ):
            engine = PoseEngine()

        self.assertEqual(engine.configuration["model_complexity"], 0)
        self.assertFalse(engine.configuration["smooth_landmarks"])
        self.assertFalse(engine.configuration["static_image_mode"])
        self.assertFalse(engine.configuration["enable_segmentation"])
        self.assertEqual(engine.configuration["min_detection_confidence"], 0.5)
        self.assertEqual(engine.configuration["min_tracking_confidence"], 0.5)

    def test_explicit_benchmark_settings_take_precedence_over_environment(self):
        with (
            patch.dict(
                "os.environ",
                {
                    "REVALIV_POSE_COMPLEXITY": "2",
                    "REVALIV_POSE_SMOOTHING": "0",
                },
                clear=True,
            ),
            patch("core.pose.mp.solutions.pose.Pose"),
        ):
            engine = PoseEngine(model_complexity=1, smooth_landmarks=True)

        self.assertEqual(engine.configuration["model_complexity"], 1)
        self.assertTrue(engine.configuration["smooth_landmarks"])

    def test_invalid_developer_configuration_is_rejected(self):
        with patch.dict(
            "os.environ",
            {"REVALIV_POSE_COMPLEXITY": "3"},
            clear=True,
        ), self.assertRaises(ValueError):
            PoseEngine()


class PoseBenchmarkDiagnosticTests(unittest.TestCase):
    def make_side_skeleton(self, side, angle, visibility=0.8):
        skeleton = Skeleton()
        add_arm(skeleton, side.upper(), angle, visibility)
        return skeleton

    def test_counts_required_landmarks_visibility_and_usable_angles(self):
        diagnostics = BicepCurlDiagnostics("left", 0.6)
        diagnostics.update(
            self.make_side_skeleton("left", 90),
            elbow_angle=90,
        )

        low_visibility = self.make_side_skeleton("left", 100, visibility=0.59)
        diagnostics.update(low_visibility, elbow_angle=None)

        angle_unavailable = self.make_side_skeleton("left", 105)
        diagnostics.update(angle_unavailable, elbow_angle=None)

        missing_wrist = self.make_side_skeleton("left", 110)
        missing_wrist.joints.pop(JointType.LEFT_WRIST)
        diagnostics.update(missing_wrist, elbow_angle=None)

        snapshot = diagnostics.snapshot()
        self.assertEqual(snapshot["processed_frames"], 4)
        self.assertEqual(snapshot["required_landmarks_available_frames"], 3)
        self.assertEqual(snapshot["sufficient_visibility_frames"], 2)
        self.assertEqual(snapshot["valid_angle_samples"], 1)
        self.assertEqual(snapshot["angle_calculation_failures"], 1)
        self.assertEqual(snapshot["missing_landmark_frames"], 1)
        self.assertEqual(snapshot["low_visibility_frames"], 1)
        self.assertEqual(snapshot["missing_landmarks"], {"LEFT_WRIST": 1})
        self.assertAlmostEqual(snapshot["usable_measurement_percent"], 25)

    def test_angle_stability_uses_only_consecutive_valid_samples(self):
        diagnostics = BicepCurlDiagnostics("right", 0.6)
        diagnostics.update(
            self.make_side_skeleton("right", 90),
            elbow_angle=90,
        )
        diagnostics.update(
            self.make_side_skeleton("right", 95),
            elbow_angle=95,
        )

        missing = Skeleton()
        diagnostics.update(missing, elbow_angle=None)

        diagnostics.update(
            self.make_side_skeleton("right", 110),
            elbow_angle=110,
        )
        diagnostics.update(
            self.make_side_skeleton("right", 102),
            elbow_angle=102,
        )

        snapshot = diagnostics.snapshot()
        self.assertEqual(snapshot["valid_angle_samples"], 4)
        self.assertEqual(snapshot["consecutive_valid_pairs"], 2)
        self.assertEqual(snapshot["consecutive_valid_percent"], 50)
        self.assertEqual(
            snapshot["mean_absolute_angle_change_degrees"],
            6.5,
        )
        self.assertEqual(
            snapshot["maximum_absolute_angle_change_degrees"],
            8,
        )

    def test_failed_frame_breaks_temporal_continuity(self):
        diagnostics = BicepCurlDiagnostics("left", 0.6)
        diagnostics.update(
            self.make_side_skeleton("left", 90),
            elbow_angle=90,
        )
        diagnostics.break_consecutive_sequence()
        diagnostics.update(
            self.make_side_skeleton("left", 120),
            elbow_angle=120,
        )

        snapshot = diagnostics.snapshot()
        self.assertEqual(snapshot["valid_angle_samples"], 2)
        self.assertEqual(snapshot["consecutive_valid_pairs"], 0)
        self.assertIsNone(
            snapshot["mean_absolute_angle_change_degrees"]
        )


class BiomechanicsTests(unittest.TestCase):
    def test_elbow_angles_visibility_and_missing_joints(self):
        skeleton = Skeleton()
        add_arm(skeleton, "LEFT", 90)
        add_arm(skeleton, "RIGHT", 60)
        metrics = JointAnalyzer()
        result = MovementMetrics()

        metrics.analyze(skeleton, result)
        self.assertAlmostEqual(result.elbow_angle_left, 90)
        self.assertAlmostEqual(result.elbow_angle_right, 60)

        skeleton.get_joint(JointType.LEFT_WRIST).visibility = 0.59
        result = MovementMetrics()
        metrics.analyze(skeleton, result)
        self.assertIsNone(result.elbow_angle_left)
        self.assertAlmostEqual(result.elbow_angle_right, 60)

        skeleton.get_joint(JointType.RIGHT_WRIST).visibility = 0.6
        skeleton.get_joint(JointType.RIGHT_ELBOW).visibility = 0.6
        result = MovementMetrics()
        metrics.analyze(skeleton, result)
        self.assertAlmostEqual(result.elbow_angle_right, 60)

        skeleton.joints.pop(JointType.RIGHT_WRIST)
        result = MovementMetrics()
        metrics.analyze(skeleton, result)
        self.assertIsNone(result.elbow_angle_right)

    def test_rom_peaks_and_selected_side(self):
        analyzer = JointAnalyzer()
        profile = get_exercise_profile(ExerciseType.RIGHT_BICEP_CURL)

        first = Skeleton()
        add_arm(first, "LEFT", 170)
        add_arm(first, "RIGHT", 150)
        first_metrics = MovementMetrics()
        analyzer.analyze(first, first_metrics, profile)
        self.assertAlmostEqual(first_metrics.peak_extension, 150)
        self.assertAlmostEqual(first_metrics.peak_flexion, 150)
        self.assertEqual(first_metrics.range_of_motion, 0)

        second = Skeleton()
        add_arm(second, "LEFT", 20)
        add_arm(second, "RIGHT", 80)
        second_metrics = MovementMetrics()
        analyzer.analyze(second, second_metrics, profile)
        self.assertAlmostEqual(second_metrics.peak_extension, 150)
        self.assertAlmostEqual(second_metrics.peak_flexion, 80)
        self.assertAlmostEqual(second_metrics.range_of_motion, 70)

    def test_selected_side_does_not_fall_back_to_the_other_elbow(self):
        analyzer = JointAnalyzer()
        profile = get_exercise_profile(ExerciseType.RIGHT_BICEP_CURL)
        skeleton = Skeleton()
        add_arm(skeleton, "LEFT", 120)
        result = MovementMetrics()

        analyzer.analyze(skeleton, result, profile)
        self.assertIsNone(result.elbow_angle_right)
        self.assertEqual(result.peak_extension, 0)

        temporal = TemporalAnalyzer()
        metrics = MovementMetrics(
            elbow_angle_left=120,
            elbow_angle_right=None,
        )
        temporal.analyze(skeleton, metrics, profile)
        self.assertEqual(metrics.peak_velocity, 0)

    def test_profileless_biomechanics_keeps_legacy_left_first_rom(self):
        skeleton = Skeleton()
        add_arm(skeleton, "LEFT", 120)
        add_arm(skeleton, "RIGHT", 60)
        metrics = BiomechanicsEngine().calculate_metrics(skeleton)
        self.assertAlmostEqual(metrics.peak_extension, 120)

    def test_temporal_velocity_uses_selected_side_and_resets_on_missing_angle(self):
        analyzer = TemporalAnalyzer()
        profile = get_exercise_profile(ExerciseType.RIGHT_BICEP_CURL)
        first = MovementMetrics(
            elbow_angle_left=10,
            elbow_angle_right=50,
        )
        second = MovementMetrics(
            elbow_angle_left=80,
            elbow_angle_right=70,
        )

        with patch(
            "core.analyzers.temporal_analyzer.time.monotonic",
            side_effect=[1.0, 2.0, 3.0],
        ):
            analyzer.analyze(Skeleton(), first, profile)
            analyzer.analyze(Skeleton(), second, profile)
            self.assertEqual(second.peak_velocity, 20)
            self.assertEqual(second.average_velocity, 20)

            missing = MovementMetrics(
                elbow_angle_left=None,
                elbow_angle_right=None,
            )
            analyzer.analyze(Skeleton(), missing, profile)
            self.assertEqual(missing.peak_velocity, 0)
            self.assertEqual(missing.average_velocity, 0)

    def test_temporal_velocity_uses_left_side_when_selected(self):
        analyzer = TemporalAnalyzer()
        profile = get_exercise_profile(ExerciseType.LEFT_BICEP_CURL)
        first = MovementMetrics(
            elbow_angle_left=30,
            elbow_angle_right=50,
        )
        second = MovementMetrics(
            elbow_angle_left=70,
            elbow_angle_right=60,
        )

        with patch(
            "core.analyzers.temporal_analyzer.time.monotonic",
            side_effect=[1.0, 2.0],
        ):
            analyzer.analyze(Skeleton(), first, profile)
            analyzer.analyze(Skeleton(), second, profile)

        self.assertEqual(second.peak_velocity, 40)
        self.assertEqual(second.average_velocity, 40)

    def test_biomechanics_profile_selects_right_side_consistently(self):
        engine = BiomechanicsEngine()
        profile = get_exercise_profile(ExerciseType.RIGHT_BICEP_CURL)
        skeleton = Skeleton()
        add_arm(skeleton, "LEFT", 170)
        add_arm(skeleton, "RIGHT", 120)

        metrics = engine.calculate_metrics(skeleton, profile)
        self.assertAlmostEqual(metrics.peak_extension, 120)
        self.assertAlmostEqual(metrics.peak_flexion, 120)

    def test_stability_displacement_and_score(self):
        analyzer = StabilityAnalyzer()
        first = Skeleton()
        add_shoulders(first)
        analyzer.analyze(first, MovementMetrics())

        second = Skeleton()
        add_shoulders(second, left=(0.5, 0.3), right=(0.7, 0.3))
        metrics = MovementMetrics()
        analyzer.analyze(second, metrics)
        self.assertAlmostEqual(metrics.shoulder_displacement, 0.1)
        self.assertAlmostEqual(metrics.torso_displacement, 0.1)
        self.assertAlmostEqual(metrics.stability_score, 35)

        analyzer.analyze(Skeleton(), metrics)
        self.assertEqual(metrics.stability_score, 100)

    def test_compensation_measurements_and_missing_landmarks(self):
        skeleton = Skeleton()
        add_shoulders(skeleton, left=(0.4, 0.34), right=(0.6, 0.3))
        add_joint(skeleton, JointType.SHOULDER_CENTER, 0.6, 0.3)
        add_joint(skeleton, JointType.PELVIS_CENTER, 0.5, 0.7)
        metrics = MovementMetrics()

        CompensationAnalyzer().analyze(skeleton, metrics)
        self.assertAlmostEqual(metrics.shoulder_hike, 0.04)
        self.assertTrue(metrics.shoulder_hike_detected)
        self.assertAlmostEqual(
            metrics.trunk_lean,
            math.degrees(math.atan2(0.1, 0.4)),
        )
        self.assertTrue(metrics.trunk_lean_detected)

        missing = MovementMetrics()
        CompensationAnalyzer().analyze(Skeleton(), missing)
        self.assertEqual(missing.shoulder_hike, 0)
        self.assertFalse(missing.shoulder_hike_detected)
        self.assertEqual(missing.trunk_lean, 0)

    def test_symmetry_differences_and_missing_landmarks(self):
        skeleton = Skeleton()
        add_shoulders(skeleton, left=(0.4, 0.35), right=(0.6, 0.3))
        add_joint(skeleton, JointType.LEFT_WRIST, 0.3, 0.7)
        add_joint(skeleton, JointType.RIGHT_WRIST, 0.7, 0.6)
        metrics = MovementMetrics(
            elbow_angle_left=120,
            elbow_angle_right=100,
        )

        SymmetryAnalyzer().analyze(skeleton, metrics)
        self.assertAlmostEqual(metrics.shoulder_height_difference, 0.05)
        self.assertAlmostEqual(metrics.wrist_height_difference, 0.1)
        self.assertEqual(metrics.elbow_angle_difference, 20)

        missing = MovementMetrics(
            shoulder_height_difference=10,
            wrist_height_difference=10,
            elbow_angle_difference=10,
        )
        SymmetryAnalyzer().analyze(Skeleton(), missing)
        self.assertEqual(missing.shoulder_height_difference, 0)
        self.assertEqual(missing.wrist_height_difference, 0)
        self.assertEqual(missing.elbow_angle_difference, 0)


class ExerciseStateTests(unittest.TestCase):
    def setUp(self):
        self.engine = ExerciseEngine()
        self.left = get_exercise_profile(ExerciseType.LEFT_BICEP_CURL)
        self.right = get_exercise_profile(ExerciseType.RIGHT_BICEP_CURL)

    def analyze(self, profile, left=None, right=None):
        return self.engine.analyze(
            profile,
            MovementMetrics(
                elbow_angle_left=left,
                elbow_angle_right=right,
            ),
        )

    def test_initial_lowered_lifting_top_lowering_and_completed_rep(self):
        state = self.engine.state
        self.assertEqual(state.phase, ExercisePhase.IDLE)
        self.assertFalse(state.active)
        self.assertEqual(state.repetitions, 0)

        self.assertEqual(self.analyze(self.left, left=170).phase, ExercisePhase.LOWERED)
        with patch("core.exercise.time.monotonic", return_value=10.0):
            state = self.analyze(self.left, left=120)
        self.assertEqual(state.phase, ExercisePhase.LIFTING)
        self.assertTrue(state.rep_started)
        self.assertEqual(state.rep_start_time, 10.0)

        self.assertEqual(self.analyze(self.left, left=50).phase, ExercisePhase.TOP)
        self.assertEqual(
            self.analyze(self.left, left=100).phase,
            ExercisePhase.LOWERING,
        )

        completed_metrics = MovementMetrics(elbow_angle_left=160)
        with patch("core.exercise.time.monotonic", return_value=12.5):
            state = self.engine.analyze(self.left, completed_metrics)
        self.assertEqual(state.phase, ExercisePhase.LOWERED)
        self.assertEqual(state.repetitions, 1)
        self.assertTrue(state.rep_completed)
        self.assertEqual(completed_metrics.rep_duration, 2.5)

    def test_completion_without_start_time_is_not_counted_or_emitted(self):
        self.engine.state.phase = ExercisePhase.LOWERING
        self.engine.state.rep_start_time = None

        metrics = MovementMetrics(elbow_angle_left=160)
        state = self.engine.analyze(self.left, metrics)

        self.assertEqual(state.phase, ExercisePhase.LOWERED)
        self.assertEqual(state.repetitions, 0)
        self.assertFalse(state.rep_completed)
        self.assertEqual(metrics.rep_duration, 0.0)

    def test_nonpositive_duration_is_not_counted_or_emitted(self):
        for completion_time in (5.0, 4.0):
            with self.subTest(completion_time=completion_time):
                self.engine = ExerciseEngine()
                self.engine.state.phase = ExercisePhase.LOWERING
                self.engine.state.rep_start_time = 5.0
                metrics = MovementMetrics(elbow_angle_left=160)

                with patch(
                    "core.exercise.time.monotonic",
                    return_value=completion_time,
                ):
                    state = self.engine.analyze(self.left, metrics)

                self.assertEqual(state.phase, ExercisePhase.LOWERED)
                self.assertEqual(state.repetitions, 0)
                self.assertFalse(state.rep_completed)
                self.assertEqual(metrics.rep_duration, 0.0)
                self.assertIsNone(state.rep_start_time)

    def test_multiple_valid_repetitions_keep_existing_transitions(self):
        self.analyze(self.left, left=170)
        for start_time, end_time in ((10.0, 12.5), (20.0, 22.0)):
            with patch("core.exercise.time.monotonic", return_value=start_time):
                state = self.analyze(self.left, left=120)
            self.assertEqual(state.phase, ExercisePhase.LIFTING)
            self.assertTrue(state.rep_started)

            self.analyze(self.left, left=50)
            self.assertEqual(
                self.analyze(self.left, left=100).phase,
                ExercisePhase.LOWERING,
            )

            metrics = MovementMetrics(elbow_angle_left=160)
            with patch("core.exercise.time.monotonic", return_value=end_time):
                state = self.engine.analyze(self.left, metrics)
            self.assertTrue(state.rep_completed)
            self.assertEqual(metrics.rep_duration, end_time - start_time)

        self.assertEqual(state.repetitions, 2)

    def test_incomplete_movement_does_not_count_rep(self):
        self.analyze(self.left, left=170)
        self.analyze(self.left, left=120)
        state = self.analyze(self.left, left=50)
        self.assertEqual(state.phase, ExercisePhase.TOP)
        self.assertEqual(state.repetitions, 0)
        self.assertFalse(state.rep_completed)

    def test_missing_elbow_and_tracking_loss_reset_in_progress_rep(self):
        self.analyze(self.left, left=170)
        self.analyze(self.left, left=120)
        state = self.analyze(self.left, left=None)
        self.assertEqual(state.phase, ExercisePhase.IDLE)
        self.assertFalse(state.active)
        self.assertIsNone(state.rep_start_time)
        self.assertEqual(state.repetitions, 0)

        self.analyze(self.left, left=170)
        self.analyze(self.left, left=120)
        state = self.analyze(self.left, left=None)
        self.assertEqual(state.phase, ExercisePhase.IDLE)
        self.assertEqual(state.repetitions, 0)

    def test_left_and_right_curls_use_their_own_angle(self):
        left_state = self.analyze(self.left, left=170, right=30)
        self.assertEqual(left_state.phase, ExercisePhase.LOWERED)
        self.assertEqual(left_state.exercise_name, "LEFT_BICEP_CURL")

        self.engine = ExerciseEngine()
        right_state = self.analyze(self.right, left=30, right=170)
        self.assertEqual(right_state.phase, ExercisePhase.LOWERED)
        self.assertEqual(right_state.exercise_name, "RIGHT_BICEP_CURL")

    def test_rapid_and_noisy_threshold_changes_keep_existing_transitions(self):
        self.analyze(self.left, left=170)
        self.analyze(self.left, left=149)
        state = self.analyze(self.left, left=58)
        self.assertEqual(state.phase, ExercisePhase.TOP)
        state = self.analyze(self.left, left=61)
        self.assertEqual(state.phase, ExercisePhase.LOWERING)

        state = self.analyze(self.left, left=59)
        self.assertEqual(state.phase, ExercisePhase.TOP)
        self.assertFalse(state.rep_completed)
        state = self.analyze(self.left, left=151)
        self.assertEqual(state.phase, ExercisePhase.LOWERED)
        self.assertEqual(state.repetitions, 0)


class PerformanceMonitorTests(unittest.TestCase):
    def test_disabled_by_default_without_environment_setting(self):
        with patch.dict("os.environ", {}, clear=True):
            monitor = PerformanceMonitor()
        self.assertFalse(monitor.enabled)
        self.assertEqual(monitor.snapshot(), {"enabled": False})

    def test_disabled_monitor_is_inactive(self):
        monitor = PerformanceMonitor(enabled=False)
        monitor.record_stage("capture", 0.01)
        monitor.increment("frames")
        self.assertEqual(monitor.snapshot(), {"enabled": False})
        self.assertFalse(monitor.should_log())

    def test_enabled_monitor_reports_bounded_timings_rates_and_age(self):
        monitor = PerformanceMonitor(enabled=True, history_size=2)
        monitor.record_stage("capture", 0.01)
        monitor.record_stage("capture", 0.02)
        monitor.record_stage("capture", 0.03)
        monitor.record_rate_event("encoded", 1.0)
        monitor.record_rate_event("encoded", 1.5)
        monitor.record_rate_event("encoded", 2.0)
        monitor.increment("frames_encoded", 3)
        monitor.record_post_capture_age(1.0, 1.25)

        snapshot = monitor.snapshot()
        self.assertEqual(snapshot["stages"]["capture"]["samples"], 2)
        self.assertAlmostEqual(snapshot["stages"]["capture"]["mean_ms"], 25)
        self.assertAlmostEqual(snapshot["stages"]["capture"]["p50_ms"], 25)
        self.assertAlmostEqual(snapshot["stages"]["capture"]["p95_ms"], 29.5)
        self.assertAlmostEqual(snapshot["rates_fps"]["encoded"], 2)
        self.assertEqual(snapshot["counters"]["frames_encoded"], 3)
        self.assertAlmostEqual(
            snapshot["post_capture_age"]["mean_ms"],
            250,
        )

    def test_monitoring_does_not_change_scoring_results_or_inputs(self):
        profile = get_exercise_profile(ExerciseType.LEFT_BICEP_CURL)
        metrics = MovementMetrics()
        state = ExerciseState(repetitions=2)
        metrics_before = vars(metrics).copy()
        state_before = vars(state).copy()
        monitor = PerformanceMonitor(enabled=True)
        before = AssessmentEngine().analyze(profile, metrics, state)
        monitor.record_stage("scoring", 0.001)
        after = AssessmentEngine().analyze(profile, metrics, state)
        self.assertEqual(vars(before), vars(after))
        self.assertEqual(vars(metrics), metrics_before)
        self.assertEqual(vars(state), state_before)
        self.assertEqual(monitor.snapshot()["stages"]["scoring"]["samples"], 1)

    def test_performance_log_interval_is_rate_limited(self):
        monitor = PerformanceMonitor(enabled=True)
        self.assertFalse(monitor.should_log(interval_seconds=30, now=29))
        self.assertTrue(monitor.should_log(interval_seconds=30, now=30))
        self.assertFalse(monitor.should_log(interval_seconds=30, now=59))
        self.assertTrue(monitor.should_log(interval_seconds=30, now=60))


if __name__ == "__main__":
    unittest.main()
