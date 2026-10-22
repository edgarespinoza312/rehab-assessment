"""Regression tests for newly wired exercise movement families."""

import unittest

from core.analyzers.joint_analyzer import JointAnalyzer
from core.exercise import ExerciseEngine
from core.exercise_registry import get_profile
from core.models import ExercisePhase, ExerciseType, Joint, JointType, MovementMetrics, Skeleton
from core.workout import BUILTIN_EXERCISES, SessionEngine, WorkoutPrescription, WorkoutPreset


class ExerciseExpansionTests(unittest.TestCase):
    def test_catalog_exposes_only_fully_wired_movement_types(self):
        for exercise in (
            ExerciseType.LEFT_BICEP_CURL,
            ExerciseType.RIGHT_BICEP_CURL,
            ExerciseType.LEFT_TRICEP_EXTENSION,
            ExerciseType.RIGHT_TRICEP_EXTENSION,
            ExerciseType.LEFT_SHOULDER_ABDUCTION,
            ExerciseType.RIGHT_SHOULDER_ABDUCTION,
        ):
            with self.subTest(exercise=exercise.name):
                profile = get_profile(exercise)
                self.assertTrue(profile.tracked_joints)
                self.assertGreater(profile.target_rom, 0)

        with self.assertRaisesRegex(ValueError, "not been implemented"):
            get_profile(ExerciseType.LEFT_SHOULDER_FLEXION)

    def test_new_profiles_are_marked_engineering_only(self):
        for exercise in (
            ExerciseType.LEFT_TRICEP_EXTENSION,
            ExerciseType.RIGHT_TRICEP_EXTENSION,
            ExerciseType.LEFT_SHOULDER_ABDUCTION,
            ExerciseType.RIGHT_SHOULDER_ABDUCTION,
        ):
            with self.subTest(exercise=exercise.name):
                profile = get_profile(exercise)
                self.assertEqual(profile.validation_status, "engineering_only")
                self.assertIn("not been clinically validated", profile.description)

    def test_triceps_extension_counts_a_complete_angle_cycle(self):
        profile = get_profile(ExerciseType.LEFT_TRICEP_EXTENSION)
        engine = ExerciseEngine()
        metrics = MovementMetrics()

        for angle in (70.0, 110.0, 160.0, 110.0):
            metrics.elbow_angle_left = angle
            engine.analyze(profile, metrics)

        metrics.elbow_angle_left = 70.0
        state = engine.analyze(profile, metrics)
        self.assertTrue(state.rep_completed)
        self.assertEqual(state.repetitions, 1)
        self.assertEqual(state.exercise_name, "LEFT_TRICEP_EXTENSION")
        self.assertEqual(state.phase, ExercisePhase.LOWERED)

    def test_shoulder_abduction_counts_a_complete_angle_cycle_on_both_sides(self):
        cases = (
            (ExerciseType.LEFT_SHOULDER_ABDUCTION, "left"),
            (ExerciseType.RIGHT_SHOULDER_ABDUCTION, "right"),
        )
        for exercise, side in cases:
            with self.subTest(side=side):
                engine = ExerciseEngine()
                profile = get_profile(exercise)
                metrics = MovementMetrics()
                field = f"shoulder_angle_{side}"

                for angle in (10.0, 45.0, 85.0, 45.0):
                    setattr(metrics, field, angle)
                    engine.analyze(profile, metrics)

                setattr(metrics, field, 10.0)
                state = engine.analyze(profile, metrics)
                self.assertTrue(state.rep_completed)
                self.assertEqual(state.repetitions, 1)
                self.assertEqual(state.exercise_name, exercise.name)

    def test_shoulder_abduction_angle_uses_arm_and_trunk_reference(self):
        skeleton = Skeleton()
        for name, x, y in (
            (JointType.LEFT_HIP, 0.20, 0.80),
            (JointType.LEFT_SHOULDER, 0.20, 0.30),
            (JointType.LEFT_ELBOW, 0.10, 0.30),
            (JointType.LEFT_WRIST, 0.02, 0.30),
            (JointType.RIGHT_HIP, 0.80, 0.80),
            (JointType.RIGHT_SHOULDER, 0.80, 0.30),
            (JointType.RIGHT_ELBOW, 0.90, 0.30),
            (JointType.RIGHT_WRIST, 0.98, 0.30),
        ):
            skeleton.add_joint(Joint(name=name, x=x, y=y, visibility=0.9))

        metrics = MovementMetrics()
        JointAnalyzer().analyze(
            skeleton, metrics, get_profile(ExerciseType.LEFT_SHOULDER_ABDUCTION)
        )
        self.assertAlmostEqual(metrics.shoulder_angle_left, 90.0, delta=0.1)
        self.assertGreaterEqual(metrics.range_of_motion, 0.0)

    def test_new_exercises_are_accepted_by_workout_prescriptions(self):
        preset = WorkoutPreset(
            id="engineering-evaluation",
            name="Engineering Evaluation",
            exercises=(
                WorkoutPrescription("triceps_extension", "left", 3),
                WorkoutPrescription("shoulder_abduction", "right", 3),
            ),
        )
        engine = SessionEngine()
        snapshot = engine.start(preset, patient_id=19)
        self.assertEqual(snapshot.current_exercise_id, "triceps_extension")
        self.assertEqual(snapshot.current_side, "left")
        self.assertEqual(engine.calibration_side, "Left")
