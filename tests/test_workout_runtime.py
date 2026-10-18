from datetime import datetime, timezone
import unittest

from core.models import AssessmentResult, ExerciseState, Joint, JointType, Skeleton
from core.perception.base import PerceptionResult, PoseStatus, ReadinessState
from core.workout import SessionEngine, SessionStatus, STARTER_BICEP_CURL_PRESET
from dashboard.workout_runtime import WorkoutRuntimeAdapter


def perception_result(accepted=True):
    skeleton = Skeleton()
    if accepted:
        skeleton.add_joint(Joint(JointType.NOSE, 0.5, 0.5, visibility=1.0))
    return PerceptionResult(
        skeleton=skeleton if accepted else None,
        status=PoseStatus.VALID if accepted else PoseStatus.INVALID,
        backend="test",
        timestamp=1.0,
        frame_number=1,
        state=ReadinessState.READY if accepted else ReadinessState.NO_PERSON,
    )


def rep_event(side, score):
    exercise_state = ExerciseState(
        exercise_name=f"{side.upper()}_BICEP_CURL",
        active=True,
        repetitions=1,
        rep_completed=True,
    )
    return exercise_state, AssessmentResult(overall_score=score, feedback=["existing score"])


class WorkoutRuntimeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.calibration_resets = []
        self.adapter = WorkoutRuntimeAdapter(
            engine=SessionEngine(
                now=lambda: datetime(2026, 10, 1, tzinfo=timezone.utc),
                create_session_id=lambda: "runtime-session",
            ),
            reset_pipeline=self.calibration_resets.append,
        )

    def test_readiness_and_rep_events_drive_two_exercise_workout_end_to_end(self):
        started = self.adapter.start(STARTER_BICEP_CURL_PRESET, patient_id=4)
        self.assertEqual(started.status, SessionStatus.CALIBRATING)
        self.assertEqual(self.calibration_resets, ["Right"])

        self.assertFalse(self.adapter.begin_frame(perception_result(False)))
        self.assertEqual(self.adapter.status, SessionStatus.CALIBRATING)
        self.assertFalse(self.adapter.begin_frame(perception_result()))
        self.assertEqual(self.adapter.status, SessionStatus.READY)
        self.assertTrue(self.adapter.begin_frame(perception_result()))
        self.assertEqual(self.adapter.status, SessionStatus.EXERCISING)
        self.assertEqual(
            self.adapter.current_profile.exercise.name,
            "RIGHT_BICEP_CURL",
        )

        state, result = rep_event("right", 90)
        self.assertTrue(self.adapter.record_repetition(perception_result(), state, result))
        self.assertEqual(self.adapter.snapshot().completed_repetitions, 1)
        self.assertEqual(self.adapter.status, SessionStatus.EXERCISING)

        state, result = rep_event("right", 92)
        self.assertTrue(self.adapter.record_repetition(perception_result(), state, result))
        self.assertEqual(self.adapter.status, SessionStatus.CALIBRATING)
        snapshot = self.adapter.snapshot()
        self.assertEqual(snapshot.current_exercise_index, 1)
        self.assertEqual(snapshot.current_side, "left")
        self.assertEqual(snapshot.target_repetitions, 2)
        self.assertEqual(snapshot.completed_repetitions, 0)
        self.assertEqual(len(snapshot.completed_exercises), 1)
        self.assertEqual(snapshot.completed_exercises[0]["repetition_scores"], (90, 92))
        self.assertEqual(self.calibration_resets, ["Right", "Left"])

        self.assertFalse(self.adapter.begin_frame(perception_result()))
        self.assertEqual(self.adapter.status, SessionStatus.READY)
        self.assertTrue(self.adapter.begin_frame(perception_result()))
        self.assertEqual(
            self.adapter.current_profile.exercise.name,
            "LEFT_BICEP_CURL",
        )
        state, result = rep_event("left", 95)
        self.assertTrue(self.adapter.record_repetition(perception_result(), state, result))
        self.assertEqual(self.adapter.snapshot().completed_repetitions, 1)
        self.assertEqual(self.adapter.status, SessionStatus.EXERCISING)
        state, result = rep_event("left", 97)
        self.assertTrue(self.adapter.record_repetition(perception_result(), state, result))

        final = self.adapter.snapshot()
        self.assertEqual(final.status, SessionStatus.SESSION_COMPLETE)
        self.assertEqual(len(final.completed_exercises), 2)
        self.assertEqual(final.completed_exercises[0]["side"], "right")
        self.assertEqual(final.completed_exercises[1]["side"], "left")
        self.assertEqual(self.calibration_resets[-1], None)
        self.assertFalse(self.adapter.active)

    def test_rejected_and_duplicate_rep_events_cannot_advance_or_duplicate_results(self):
        self.adapter.start(STARTER_BICEP_CURL_PRESET)
        self.adapter.begin_frame(perception_result())
        self.adapter.begin_frame(perception_result())
        state, result = rep_event("right", 90)
        self.assertFalse(self.adapter.record_repetition(perception_result(False), state, result))
        self.assertEqual(self.adapter.snapshot().completed_repetitions, 0)

        for score in (90, 91):
            state, result = rep_event("right", score)
            self.adapter.record_repetition(perception_result(), state, result)
        self.assertEqual(len(self.adapter.snapshot().completed_exercises), 1)
        # A duplicated frame event cannot be counted against the next exercise.
        self.assertFalse(self.adapter.record_repetition(perception_result(), state, result))
        self.assertEqual(self.adapter.snapshot().completed_repetitions, 0)
        self.assertEqual(len(self.adapter.snapshot().completed_exercises), 1)

    def test_cancel_clears_live_state_but_keeps_completed_history(self):
        self.adapter.start(STARTER_BICEP_CURL_PRESET)
        self.adapter.begin_frame(perception_result())
        self.adapter.begin_frame(perception_result())
        for score in (90, 91):
            state, result = rep_event("right", score)
            self.adapter.record_repetition(perception_result(), state, result)
        self.assertEqual(len(self.adapter.snapshot().completed_exercises), 1)

        cancelled = self.adapter.cancel()
        self.assertEqual(cancelled.status, SessionStatus.CANCELLED)
        self.assertEqual(len(cancelled.completed_exercises), 1)
        self.assertEqual(self.calibration_resets[-1], None)


if __name__ == "__main__":
    unittest.main()
