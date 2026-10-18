from datetime import datetime
import unittest

from flask import Flask

from dashboard.database import db
from dashboard.models import (
    AssessmentRecord,
    CompletedWorkoutSession,
    ExerciseIdentity,
    Patient,
    WorkoutExerciseResult,
)
from dashboard.services.progression import get_patient_progression_context


class ProgressionContextTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(f"progression-context-{id(self)}")
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI="sqlite://",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        db.session.add_all([
            Patient(patient_id=1, first_name="A", last_name="Patient"),
            Patient(patient_id=2, first_name="B", last_name="Patient"),
            ExerciseIdentity(exercise_id="bicep_curl"),
        ])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _add_session(
        self,
        session_id,
        patient_id,
        started_at,
        status,
        results,
    ):
        db.session.add(CompletedWorkoutSession(
            runtime_session_id=session_id,
            patient_id=patient_id,
            preset_id="context-test",
            workout_name="Context Test",
            status=status,
            started_at=started_at,
            completed_at=started_at,
            exercise_results=[
                WorkoutExerciseResult(
                    position=position,
                    exercise_id=exercise_id,
                    display_name=display_name,
                    side=side,
                    target_repetitions=target,
                    completed_repetitions=completed,
                    status="complete",
                    resistance_value=resistance,
                    resistance_unit=unit,
                    resistance_type=resistance_type,
                    average_score=score,
                    started_at=started_at,
                    completed_at=started_at,
                )
                for position, (
                    exercise_id,
                    display_name,
                    side,
                    target,
                    completed,
                    resistance,
                    unit,
                    resistance_type,
                    score,
                ) in enumerate(results)
            ],
        ))
        db.session.commit()

    def test_empty_history_is_clean_and_unknown_patient_isolated(self):
        self.assertEqual(get_patient_progression_context(1), [])
        self.assertEqual(get_patient_progression_context(999), [])

    def test_legacy_history_preserves_unknown_side_and_missing_resistance(self):
        db.session.add(AssessmentRecord(
            patient_id=1,
            exercise="Left Bicep Curl",
            repetitions=3,
            average_score=75,
            best_score=80,
            worst_score=70,
            created_at=datetime(2026, 1, 1),
        ))
        db.session.commit()

        context = get_patient_progression_context(1)[0]
        self.assertEqual(context.exercise_id, "bicep_curl")
        self.assertIsNone(context.side)
        self.assertEqual(context.previous_completed_repetitions, 3)
        self.assertIsNone(context.previous_target_repetitions)
        self.assertEqual(context.previous_overall_score, 75)
        self.assertIsNone(context.previous_resistance_value)
        self.assertEqual(context.source_type, "legacy_assessment")
        self.assertEqual(context.recent_record_count, 1)
        self.assertEqual(context.recent_resistance_observations[0].unit, None)

    def test_completed_cancelled_and_mixed_history_use_latest_snapshot(self):
        db.session.add(AssessmentRecord(
            patient_id=1,
            exercise="Left Bicep Curl",
            repetitions=2,
            average_score=70,
            best_score=70,
            worst_score=70,
            created_at=datetime(2026, 1, 1),
        ))
        self._add_session(
            "context-completed",
            1,
            datetime(2026, 1, 2),
            "completed",
            [(
                "bicep_curl", "Bicep Curl", "right", 3, 3,
                5, "lb", "dumbbell", 80,
            )],
        )
        self._add_session(
            "context-cancelled",
            1,
            datetime(2026, 1, 3),
            "cancelled",
            [(
                "bicep_curl", "Bicep Curl", "right", 4, 3,
                7.5, "lb", "dumbbell", 85,
            )],
        )

        contexts = get_patient_progression_context(1, exercise_id="bicep_curl")
        right = [item for item in contexts if item.side == "right"][0]
        legacy = [item for item in contexts if item.side is None][0]
        self.assertEqual(right.latest_observation_at, datetime(2026, 1, 3))
        self.assertEqual(right.previous_completed_repetitions, 3)
        self.assertEqual(right.previous_target_repetitions, 4)
        self.assertEqual(right.previous_completion_percentage, 75)
        self.assertEqual(right.previous_overall_score, 85)
        self.assertEqual(right.previous_resistance_value, 7.5)
        self.assertEqual(right.previous_resistance_unit, "lb")
        self.assertEqual(right.source_type, "workout")
        self.assertEqual(right.session_status, "cancelled")
        self.assertEqual(right.recent_record_count, 2)
        self.assertEqual(right.recent_overall_scores, (80, 85))
        self.assertEqual(right.recent_completion_percentages, (100, 75))
        self.assertEqual(
            [(item.value, item.unit) for item in right.recent_resistance_observations],
            [(5.0, "lb"), (7.5, "lb")],
        )
        self.assertEqual(legacy.source_type, "legacy_assessment")

    def test_side_multiple_exercises_units_and_order_are_preserved(self):
        self._add_session(
            "context-multi",
            1,
            datetime(2026, 1, 2),
            "completed",
            [
                ("bicep_curl", "Bicep Curl", "left", 3, 2, 5, "lb", "dumbbell", 60),
                ("bicep_curl", "Bicep Curl", "right", 3, 3, 2.5, "kg", "cable", 90),
            ],
        )
        self._add_session(
            "context-other-patient",
            2,
            datetime(2026, 1, 4),
            "completed",
            [(
                "bicep_curl", "Bicep Curl", "left", 3, 3,
                10, "lb", "dumbbell", 99,
            )],
        )
        contexts = get_patient_progression_context(1)
        self.assertEqual(
            [(item.side, item.latest_observation_at) for item in contexts],
            [("left", datetime(2026, 1, 2)), ("right", datetime(2026, 1, 2))],
        )
        left = [item for item in contexts if item.side == "left"][0]
        right = [item for item in contexts if item.side == "right"][0]
        self.assertEqual(left.previous_resistance_unit, "lb")
        self.assertEqual(right.previous_resistance_unit, "kg")
        self.assertEqual(
            get_patient_progression_context(1, side="left")[0].side,
            "left",
        )
        self.assertEqual(
            get_patient_progression_context(1, side="right")[0].side,
            "right",
        )
        self.assertEqual(
            get_patient_progression_context(1),
            get_patient_progression_context(1),
        )


if __name__ == "__main__":
    unittest.main()
