from datetime import datetime
import unittest

from dashboard.app import app
from dashboard.database import db
from dashboard.models import (
    CompletedWorkoutSession,
    ExerciseIdentity,
    Patient,
    WorkoutExerciseResult,
)
from tests.support.auth import login_client, seed_clinician


class ProgressionContextApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.client = app.test_client()

    def setUp(self):
        with self.app.app_context():
            db.session.rollback()
            db.drop_all()
            db.create_all()
            db.session.add_all([
                Patient(patient_id=1, first_name="A", last_name="Patient"),
                ExerciseIdentity(exercise_id="bicep_curl"),
            ])
            seed_clinician(self.app)
            db.session.commit()
        login_client(self.app, self.client)

    def tearDown(self):
        with self.app.app_context():
            db.session.rollback()
            db.drop_all()

    def test_context_endpoint_filters_and_serializes_datetime_and_resistance(self):
        with self.app.app_context():
            db.session.add(CompletedWorkoutSession(
                runtime_session_id="context-api",
                patient_id=1,
                preset_id="context-api",
                workout_name="Context API",
                status="completed",
                started_at=datetime(2026, 1, 2, 10),
                completed_at=datetime(2026, 1, 2, 10),
                exercise_results=[WorkoutExerciseResult(
                    position=0,
                    exercise_id="bicep_curl",
                    display_name="Bicep Curl",
                    side="right",
                    target_repetitions=3,
                    completed_repetitions=3,
                    status="complete",
                    resistance_value=5,
                    resistance_unit="lb",
                    resistance_type="dumbbell",
                    average_score=87,
                    started_at=datetime(2026, 1, 2, 10),
                    completed_at=datetime(2026, 1, 2, 10),
                )],
            ))
            db.session.commit()

        response = self.client.get(
            "/api/patients/1/progression/context"
            "?exercise_id=bicep_curl&side=right"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["count"], 1)
        context = payload["contexts"][0]
        self.assertEqual(context["exercise_id"], "bicep_curl")
        self.assertEqual(context["side"], "right")
        self.assertEqual(
            context["latest_observation_at"],
            "2026-01-02T10:00:00",
        )
        self.assertEqual(context["previous_resistance_value"], 5.0)
        self.assertEqual(context["previous_resistance_unit"], "lb")
        self.assertEqual(
            context["recent_resistance_observations"][0]["occurred_at"],
            "2026-01-02T10:00:00",
        )

    def test_context_endpoint_empty_unknown_patient_and_invalid_filters(self):
        response = self.client.get("/api/patients/1/progression/context")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "count": 0,
            "contexts": [],
            "patient_id": 1,
        })
        self.assertEqual(
            self.client.get("/api/patients/999/progression/context").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                "/api/patients/1/progression/context?side=middle"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                "/api/patients/1/progression/context?exercise_id=unknown"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                "/api/patients/1/progression/context?recent_limit=0"
            ).status_code,
            400,
        )


if __name__ == "__main__":
    unittest.main()
