from datetime import datetime, timezone
import unittest

from core.models import AssessmentResult, ExerciseState, Joint, JointType, Skeleton
from core.workout import (
    ExerciseCompletionStatus,
    InvalidSessionTransition,
    SessionEngine,
    SessionStatus,
    WorkoutPreset,
    WorkoutPrescription,
)


def completed_event(score=90, exercise_name="LEFT_BICEP_CURL"):
    state = ExerciseState(
        exercise_name=exercise_name,
        active=True,
        repetitions=1,
        rep_completed=True,
    )
    return state, AssessmentResult(overall_score=score, feedback=["good form"])


def preset(*items):
    return WorkoutPreset(
        id="upper-limb-a",
        name="Upper Limb A",
        exercises=tuple(items),
    )


class WorkoutPresetTests(unittest.TestCase):
    def test_empty_preset_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            preset()

    def test_valid_preset_preserves_order_and_prescription_targets(self):
        left = WorkoutPrescription("bicep_curl", "LEFT", 10)
        right = WorkoutPrescription("bicep_curl", "right", 6)
        workout = preset(left, right)
        self.assertEqual(workout.exercises, (left, right))
        self.assertEqual([entry.target_repetitions for entry in workout.exercises], [10, 6])
        self.assertEqual([entry.side for entry in workout.exercises], ["left", "right"])

    def test_invalid_exercise_reference_is_rejected_on_start(self):
        engine = SessionEngine()
        invalid = preset(WorkoutPrescription("shoulder_raise", "left", 8))
        with self.assertRaisesRegex(ValueError, "unknown exercise"):
            engine.start(invalid)

    def test_invalid_side_for_definition_is_rejected_on_start(self):
        engine = SessionEngine()
        # Right is supported for this definition; use an injected one-sided definition.
        from core.workout import ExerciseDefinition, ExerciseDefinitionRegistry
        from core.exercise_registry import get_profile
        from core.models import ExerciseType

        left_only = ExerciseDefinitionRegistry((ExerciseDefinition(
            "left_curl", "Left Curl", (get_profile(ExerciseType.LEFT_BICEP_CURL),),
        ),))
        engine = SessionEngine(left_only)
        invalid = preset(WorkoutPrescription("left_curl", "right", 8))
        with self.assertRaisesRegex(ValueError, "does not support"):
            engine.start(invalid)

    def test_invalid_repetition_counts_and_sides_are_rejected(self):
        for count in (0, -1, 1.5, True):
            with self.subTest(count=count), self.assertRaises(ValueError):
                WorkoutPrescription("bicep_curl", "left", count)
        with self.assertRaisesRegex(ValueError, "side"):
            WorkoutPrescription("bicep_curl", "both", 5)


class SessionEngineTests(unittest.TestCase):
    def setUp(self):
        self.now_value = datetime(2026, 10, 1, tzinfo=timezone.utc)
        self.engine = SessionEngine(
            now=lambda: self.now_value,
            create_session_id=lambda: "session-1",
        )

    def _start(self, workout=None):
        workout = workout or preset(WorkoutPrescription("bicep_curl", "left", 2))
        return self.engine.start(workout, patient_id=17)

    def _ready_and_exercising(self):
        self._start()
        self.engine.calibration_succeeded()
        return self.engine.begin_exercise()

    def test_session_starts_in_calibration_with_first_exercise_and_profile(self):
        self.assertEqual(self.engine.status, SessionStatus.NOT_STARTED)
        snapshot = self._start()
        self.assertEqual(snapshot.status, SessionStatus.CALIBRATING)
        self.assertEqual(snapshot.current_exercise_index, 0)
        self.assertEqual(snapshot.current_exercise_id, "bicep_curl")
        self.assertEqual(snapshot.current_side, "left")
        self.assertEqual(snapshot.target_repetitions, 2)
        self.assertEqual(self.engine.current_profile.target_side, "Left")
        self.assertEqual(self.engine.calibration_side, "Left")

    def test_ready_and_exercise_completion_transitions(self):
        self._start()
        self.engine.calibration_succeeded()
        self.assertEqual(self.engine.snapshot().status, SessionStatus.READY)
        self.assertEqual(self.engine.begin_exercise().status, SessionStatus.EXERCISING)
        state, result = completed_event(score=88)
        self.assertTrue(self.engine.record_repetition(state, result))
        self.assertEqual(self.engine.snapshot().completed_repetitions, 1)
        self.assertEqual(self.engine.snapshot().status, SessionStatus.EXERCISING)
        state, result = completed_event(score=96)
        self.assertTrue(self.engine.record_repetition(state, result))
        snapshot = self.engine.snapshot()
        self.assertEqual(snapshot.status, SessionStatus.EXERCISE_COMPLETE)
        self.assertEqual(snapshot.completed_exercises[0]["completed_repetitions"], 2)
        self.assertEqual(snapshot.completed_exercises[0]["status"], ExerciseCompletionStatus.COMPLETE.value)

    def test_invalid_or_duplicate_pipeline_events_do_not_advance(self):
        self._ready_and_exercising()
        state, result = completed_event()
        state.rep_completed = False
        self.assertFalse(self.engine.record_repetition(state, result))
        wrong_exercise, result = completed_event(exercise_name="RIGHT_BICEP_CURL")
        self.assertFalse(self.engine.record_repetition(wrong_exercise, result))
        self.assertEqual(self.engine.snapshot().completed_repetitions, 0)

    def test_multi_exercise_transition_preserves_completed_history(self):
        self._start(preset(
            WorkoutPrescription("bicep_curl", "left", 1),
            WorkoutPrescription("bicep_curl", "right", 1),
        ))
        self.engine.calibration_succeeded()
        self.engine.begin_exercise()
        state, result = completed_event(91)
        self.engine.record_repetition(state, result)
        transitioning = self.engine.advance()
        self.assertEqual(transitioning.status, SessionStatus.TRANSITIONING)
        self.assertEqual(transitioning.current_exercise_index, 1)
        self.assertEqual(transitioning.current_side, "right")
        self.assertEqual(len(transitioning.completed_exercises), 1)

        calibrating = self.engine.begin_next_calibration()
        self.assertEqual(calibrating.status, SessionStatus.CALIBRATING)
        self.assertEqual(self.engine.current_profile.target_side, "Right")
        self.engine.calibration_succeeded()
        self.engine.begin_exercise()
        state, result = completed_event(95, "RIGHT_BICEP_CURL")
        self.engine.record_repetition(state, result)
        completed = self.engine.advance()
        self.assertEqual(completed.status, SessionStatus.SESSION_COMPLETE)
        self.assertEqual(len(completed.completed_exercises), 2)
        self.assertEqual(completed.to_dict()["completed_exercises"][1]["repetition_scores"], [95])
        self.assertIsNotNone(completed.ended_at)

    def test_cannot_advance_or_skip_without_completion(self):
        self._start(preset(
            WorkoutPrescription("bicep_curl", "left", 1),
            WorkoutPrescription("bicep_curl", "right", 1),
        ))
        with self.assertRaises(InvalidSessionTransition):
            self.engine.advance()
        self.engine.calibration_succeeded()
        with self.assertRaises(InvalidSessionTransition):
            self.engine.begin_next_calibration()
        self.engine.begin_exercise()
        with self.assertRaises(InvalidSessionTransition):
            self.engine.advance()

    def test_final_exercise_completion_and_cancel_are_terminal(self):
        self._ready_and_exercising()
        for score in (90, 80):
            state, result = completed_event(score)
            self.engine.record_repetition(state, result)
        self.assertEqual(self.engine.advance().status, SessionStatus.SESSION_COMPLETE)
        with self.assertRaises(InvalidSessionTransition):
            self.engine.cancel()

        other = SessionEngine(now=lambda: self.now_value)
        other.start(preset(WorkoutPrescription("bicep_curl", "left", 2)))
        other.calibration_succeeded()
        other.begin_exercise()
        state, result = completed_event(87)
        other.record_repetition(state, result)
        cancelled = other.cancel()
        self.assertEqual(cancelled.status, SessionStatus.CANCELLED)
        self.assertIsNotNone(cancelled.ended_at)
        self.assertEqual(cancelled.to_dict()["current_exercise"]["completed_repetitions"], 1)
        self.assertEqual(cancelled.completed_exercises, ())
        with self.assertRaises(InvalidSessionTransition):
            other.begin_exercise()

    def test_invalid_transitions_and_active_session_replacement_are_rejected(self):
        with self.assertRaises(InvalidSessionTransition):
            self.engine.begin_exercise()
        self._start()
        with self.assertRaises(InvalidSessionTransition):
            self.engine.start(preset(WorkoutPrescription("bicep_curl", "right", 1)))
        with self.assertRaises(InvalidSessionTransition):
            self.engine.advance()

    def test_result_values_and_snapshots_are_preserved_and_read_only(self):
        self._ready_and_exercising()
        state, result = completed_event(88)
        self.engine.record_repetition(state, result)
        result.feedback.append("mutated after recording")
        state, result = completed_event(96)
        self.engine.record_repetition(state, result)
        snapshot = self.engine.snapshot()
        exercise_result = snapshot.completed_exercises[0]
        self.assertEqual(exercise_result["repetition_scores"], (88, 96))
        self.assertEqual(exercise_result["average_score"], 92)
        self.assertEqual(exercise_result["best_score"], 96)
        self.assertEqual(exercise_result["worst_score"], 88)
        with self.assertRaises(TypeError):
            snapshot.completed_exercises[0]["status"] = "changed"
        mutable_copy = snapshot.to_dict()
        mutable_copy["completed_exercises"][0]["repetition_scores"].clear()
        self.assertEqual(snapshot.to_dict()["completed_exercises"][0]["repetition_scores"], [88, 96])


if __name__ == "__main__":
    unittest.main()
