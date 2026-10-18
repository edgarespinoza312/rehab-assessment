from datetime import datetime
import unittest

from flask import Flask

from dashboard.config import Config
from dashboard.database import db
from dashboard.models import (
    AssessmentRecord,
    CompletedWorkoutSession,
    ExerciseIdentity,
    Patient,
    WorkoutExerciseResult,
)
from dashboard.services.progression import (
    _completion_percentage,
    get_patient_progression,
)


class ProgressionTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(f"progression-{id(self)}")
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

    def _session(self, session_id, patient_id, started_at, status, results):
        session = CompletedWorkoutSession(
            runtime_session_id=session_id,
            patient_id=patient_id,
            preset_id="test",
            workout_name="Progression Test",
            status=status,
            started_at=started_at,
            completed_at=started_at,
            exercise_results=[
                WorkoutExerciseResult(
                    position=position,
                    exercise_id="bicep_curl",
                    display_name="Bicep Curl",
                    side=side,
                    target_repetitions=target,
                    completed_repetitions=completed,
                    status="complete",
                    resistance_value=resistance,
                    resistance_unit=unit,
                    average_score=score,
                    rom_score=score - 1,
                    tempo_score=score - 2,
                    completion_score=score - 3,
                    stability_score=score - 4,
                    compensation_score=score - 5,
                    symmetry_score=score - 6,
                    started_at=started_at,
                    completed_at=started_at,
                )
                for position, (side, target, completed, resistance, unit, score)
                in enumerate(results)
            ],
        )
        db.session.add(session)
        db.session.commit()
        return session

    def test_workout_history_filters_orders_and_projects_metrics(self):
        self._session(
            "later",
            1,
            datetime(2026, 1, 2),
            "completed",
            [("right", 4, 3, 7.5, "lb", 90)],
        )
        self._session(
            "earlier",
            1,
            datetime(2026, 1, 1),
            "completed",
            [
                ("left", 3, 3, 5, "lb", 80),
                ("right", 4, 0, None, None, 70),
            ],
        )
        results = get_patient_progression(1, exercise_id="bicep_curl")
        self.assertEqual(
            [(item.occurred_at, item.side) for item in results],
            [(datetime(2026, 1, 1), "left"), (datetime(2026, 1, 1), "right"),
             (datetime(2026, 1, 2), "right")],
        )
        self.assertEqual(results[0].completion_percentage, 100)
        self.assertEqual(results[1].completion_percentage, 0)
        self.assertEqual(results[2].completion_percentage, 75)
        self.assertEqual(results[2].resistance_value, 7.5)
        self.assertEqual(results[2].resistance_unit, "lb")
        self.assertEqual(results[2].rom_score, 89)
        self.assertEqual(results[2].tempo_score, 88)
        self.assertEqual(results[2].completion_score, 87)
        self.assertEqual(results[2].stability_score, 86)
        self.assertEqual(results[2].compensation_score, 85)
        self.assertEqual(results[2].symmetry_score, 84)
        self.assertEqual(get_patient_progression(1, side="left")[0].side, "left")
        self.assertEqual(get_patient_progression(1, side="right")[0].side, "right")

    def test_cancelled_session_includes_only_persisted_completed_results(self):
        self._session(
            "cancelled",
            1,
            datetime(2026, 1, 3),
            "cancelled",
            [("left", 4, 3, 5, "lb", 85)],
        )
        results = get_patient_progression(1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].session_status, "cancelled")
        self.assertEqual(results[0].completed_repetitions, 3)

    def test_legacy_records_map_supported_fields_without_fabricating_side(self):
        db.session.add(AssessmentRecord(
            patient_id=1,
            exercise="Left Bicep Curl",
            repetitions=3,
            average_score=82,
            best_score=90,
            worst_score=70,
            created_at=datetime(2026, 1, 4),
        ))
        db.session.commit()
        results = get_patient_progression(1, exercise_id="bicep_curl")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source_type, "legacy_assessment")
        self.assertEqual(results[0].exercise_id, "bicep_curl")
        self.assertIsNone(results[0].side)
        self.assertIsNone(results[0].resistance_value)
        self.assertEqual(results[0].completed_repetitions, 3)
        self.assertIsNone(results[0].completion_percentage)
        self.assertEqual(get_patient_progression(1, side="left"), [])

    def test_patient_and_date_isolation_and_empty_history(self):
        self._session(
            "patient-a",
            1,
            datetime(2026, 2, 1),
            "completed",
            [("right", 3, 3, None, None, 91)],
        )
        self._session(
            "patient-b",
            2,
            datetime(2026, 2, 2),
            "completed",
            [("right", 3, 3, None, None, 92)],
        )
        self.assertEqual(len(get_patient_progression(1)), 1)
        self.assertEqual(len(get_patient_progression(
            1,
            start=datetime(2026, 2, 1),
            end=datetime(2026, 2, 1),
        )), 1)
        self.assertEqual(get_patient_progression(1, start=datetime(2026, 2, 2)), [])
        self.assertEqual(get_patient_progression(99), [])
        self.assertEqual(get_patient_progression(1, side="left"), [])

    def test_invalid_date_range_and_zero_target_are_safe(self):
        with self.assertRaises(ValueError):
            get_patient_progression(
                1,
                start=datetime(2026, 2, 2),
                end=datetime(2026, 2, 1),
            )
        self.assertEqual(_completion_percentage(3, 3), 100)
        self.assertEqual(_completion_percentage(3, 4), 75)
        self.assertEqual(_completion_percentage(0, 4), 0)
        self.assertEqual(_completion_percentage(0, 0), None)


if __name__ == "__main__":
    unittest.main()
