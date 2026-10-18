import json
import unittest

from flask import Flask
from sqlalchemy.exc import IntegrityError

from core.models import AssessmentResult, ExerciseState
from core.workout import SessionEngine, SessionStatus, WorkoutPrescription
from dashboard.database import db
from dashboard.models import (
    AssessmentRecord,
    CompletedWorkoutSession,
    ExerciseIdentity,
    Patient,
    WorkoutExerciseResult,
    WorkoutPlan,
    WorkoutPlanExercise,
)
from dashboard.services.workout_persistence import (
    create_workout_plan,
    load_workout_preset,
    persist_workout_session,
)


class WorkoutPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(f"workout-persistence-{id(self)}")
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI="sqlite://",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.patient = Patient(first_name="Alex", last_name="Revaliv")
        db.session.add(self.patient)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_plan_order_side_targets_and_optional_resistance_round_trip(self):
        plan = create_workout_plan(
            "Bilateral curls",
            (
                WorkoutPrescription(
                    "bicep_curl", "right", 8, 5, "lb", "external"
                ),
                WorkoutPrescription("bicep_curl", "left", 10),
            ),
            patient_id=self.patient.patient_id,
        )

        db.session.expire_all()
        stored = db.session.get(WorkoutPlan, plan.plan_id)
        self.assertEqual(
            [(item.position, item.side, item.target_repetitions) for item in stored.exercises],
            [(0, "right", 8), (1, "left", 10)],
        )
        self.assertEqual(stored.exercises[0].exercise_id, "bicep_curl")
        self.assertEqual(float(stored.exercises[0].resistance_value), 5.0)
        self.assertEqual(stored.exercises[0].resistance_unit, "lb")
        self.assertIsNone(stored.exercises[1].resistance_value)
        self.assertIsNone(stored.exercises[1].resistance_unit)

        loaded = load_workout_preset(plan.plan_id)
        self.assertEqual(
            [(item.side, item.target_repetitions) for item in loaded.exercises],
            [("right", 8), ("left", 10)],
        )
        self.assertEqual(loaded.exercises[0].resistance_unit, "lb")
        self.assertIsNone(loaded.exercises[1].resistance_value)

    def test_unknown_exercise_id_is_rejected_without_partial_records(self):
        with self.assertRaisesRegex(ValueError, "unknown exercise definition"):
            create_workout_plan(
                "Invalid exercise",
                (WorkoutPrescription("unknown_exercise", "left", 4),),
                patient_id=self.patient.patient_id,
            )

        self.assertEqual(WorkoutPlan.query.count(), 0)
        self.assertEqual(ExerciseIdentity.query.count(), 0)

    def test_workout_plan_name_limit_matches_storage_column(self):
        exercises = (WorkoutPrescription("bicep_curl", "left", 4),)
        with self.assertRaisesRegex(ValueError, "at most 120 characters"):
            create_workout_plan("W" * 121, exercises)
        self.assertEqual(WorkoutPlan.query.count(), 0)
        self.assertEqual(ExerciseIdentity.query.count(), 0)

        plan = create_workout_plan("W" * 120, exercises)
        self.assertEqual(len(plan.name), 120)

    def test_workout_plan_description_limit_is_enforced(self):
        exercises = (WorkoutPrescription("bicep_curl", "left", 4),)
        with self.assertRaisesRegex(ValueError, "at most 10000 characters"):
            create_workout_plan(
                "Description limit",
                exercises,
                description="D" * 10_001,
            )
        self.assertEqual(WorkoutPlan.query.count(), 0)
        self.assertEqual(ExerciseIdentity.query.count(), 0)

        plan = create_workout_plan(
            "Description limit",
            exercises,
            description="D" * 10_000,
        )
        self.assertEqual(len(plan.description), 10_000)

    def test_patient_scoped_loading_allows_shared_or_matching_plan_only(self):
        patient_plan = create_workout_plan(
            "Patient curls",
            (WorkoutPrescription("bicep_curl", "right", 3),),
            patient_id=self.patient.patient_id,
        )
        shared_plan = create_workout_plan(
            "Shared curls",
            (WorkoutPrescription("bicep_curl", "left", 4),),
        )
        self.assertEqual(
            load_workout_preset(
                patient_plan.plan_id,
                patient_id=self.patient.patient_id,
            ).exercises[0].side,
            "right",
        )
        self.assertEqual(
            load_workout_preset(
                shared_plan.plan_id,
                patient_id=self.patient.patient_id,
            ).exercises[0].side,
            "left",
        )
        with self.assertRaises(LookupError):
            load_workout_preset(patient_plan.plan_id, patient_id=999)

    def _complete_plan_session(self, plan):
        engine = SessionEngine()
        engine.start(
            load_workout_preset(plan.plan_id),
            patient_id=self.patient.patient_id,
        )

        for index, prescription in enumerate(plan.exercises):
            engine.calibration_succeeded()
            engine.begin_exercise()
            result = AssessmentResult(
                overall_score=80 + index * 10,
                rom_score=70 + index * 10,
                tempo_score=75,
                completion_score=85,
                stability_score=90,
                compensation_score=65,
                symmetry_score=88,
                feedback=[f"exercise {index + 1} feedback"],
            )
            self.assertTrue(engine.record_repetition(
                ExerciseState(rep_completed=True),
                result,
            ))
            if index == 0:
                engine.advance()
                engine.begin_next_calibration()
        engine.advance()
        return engine.snapshot()

    def test_completed_workout_persists_patient_linked_ordered_scored_results(self):
        plan = create_workout_plan(
            "Weighted bilateral curls",
            (
                WorkoutPrescription("bicep_curl", "right", 1, 2.5, "kg", "external"),
                WorkoutPrescription("bicep_curl", "left", 1),
            ),
            patient_id=self.patient.patient_id,
        )
        snapshot = self._complete_plan_session(plan)
        self.assertEqual(snapshot.status, SessionStatus.SESSION_COMPLETE)

        persisted = persist_workout_session(
            snapshot,
            workout_plan_id=plan.plan_id,
        )
        db.session.expire_all()
        stored = db.session.get(CompletedWorkoutSession, persisted.workout_session_id)

        self.assertEqual(stored.patient.patient_id, self.patient.patient_id)
        self.assertEqual(len(self.patient.workout_sessions), 1)
        self.assertEqual(stored.workout_plan_id, plan.plan_id)
        self.assertEqual(stored.status, "completed")
        self.assertEqual(stored.runtime_session_id, snapshot.session_id)
        self.assertEqual(
            [(item.position, item.side, item.exercise_id) for item in stored.exercise_results],
            [(0, "right", "bicep_curl"), (1, "left", "bicep_curl")],
        )
        self.assertEqual(stored.exercise_results[0].target_repetitions, 1)
        self.assertEqual(stored.exercise_results[0].completed_repetitions, 1)
        self.assertEqual(float(stored.exercise_results[0].resistance_value), 2.5)
        self.assertEqual(stored.exercise_results[0].resistance_unit, "kg")
        self.assertIsNone(stored.exercise_results[1].resistance_value)
        self.assertAlmostEqual(stored.exercise_results[0].average_score, 80)
        self.assertAlmostEqual(stored.exercise_results[0].rom_score, 70)
        self.assertEqual(json.loads(stored.exercise_results[1].feedback), [
            "exercise 2 feedback"
        ])
        self.assertEqual(
            stored.exercise_results[0].workout_plan_exercise_id,
            plan.exercises[0].plan_exercise_id,
        )
        self.assertIs(
            stored.exercise_results[0].workout_session.patient,
            self.patient,
        )

        repeated = persist_workout_session(snapshot, workout_plan_id=plan.plan_id)
        self.assertEqual(repeated.workout_session_id, stored.workout_session_id)
        self.assertEqual(CompletedWorkoutSession.query.count(), 1)

    def test_cancelled_session_keeps_completed_exercise_and_cancel_status(self):
        plan = create_workout_plan(
            "Two-stage workout",
            (
                WorkoutPrescription("bicep_curl", "right", 1),
                WorkoutPrescription("bicep_curl", "left", 2),
            ),
            patient_id=self.patient.patient_id,
        )
        engine = SessionEngine()
        engine.start(load_workout_preset(plan.plan_id), patient_id=self.patient.patient_id)
        engine.calibration_succeeded()
        engine.begin_exercise()
        engine.record_repetition(
            ExerciseState(rep_completed=True),
            AssessmentResult(overall_score=91, feedback=["completed first exercise"]),
        )
        engine.advance()
        engine.begin_next_calibration()
        snapshot = engine.cancel()

        persisted = persist_workout_session(snapshot, workout_plan_id=plan.plan_id)
        self.assertEqual(persisted.status, "cancelled")
        self.assertEqual(len(persisted.exercise_results), 1)
        self.assertEqual(persisted.exercise_results[0].side, "right")

    def test_patient_and_exercise_foreign_keys_are_enforced(self):
        invalid_patient_plan = WorkoutPlan(
            patient_id=999,
            name="Invalid patient",
            exercises=[
                WorkoutPlanExercise(
                    position=0,
                    exercise_id="bicep_curl",
                    side="left",
                    target_repetitions=1,
                )
            ],
        )
        db.session.add(ExerciseIdentity(exercise_id="bicep_curl"))
        db.session.add(invalid_patient_plan)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        plan = WorkoutPlan(name="Invalid exercise", exercises=[
            WorkoutPlanExercise(
                position=0,
                exercise_id="unknown_exercise",
                side="left",
                target_repetitions=1,
            )
        ])
        db.session.add(plan)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_required_fields_and_database_checks_are_enforced(self):
        with self.assertRaises(ValueError):
            WorkoutPrescription("bicep_curl", "both", 4)
        with self.assertRaises(ValueError):
            WorkoutPrescription("bicep_curl", "left", 4, 5, None)
        with self.assertRaises(ValueError):
            WorkoutPrescription("bicep_curl", "left", 4, float("nan"), "kg")

        empty_name = WorkoutPlan(name=None)
        db.session.add(empty_name)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        exercise_identity = ExerciseIdentity(exercise_id="bicep_curl")
        invalid_side_plan = WorkoutPlan(name="Bad side", exercises=[
            WorkoutPlanExercise(
                position=0,
                exercise_identity=exercise_identity,
                side="both",
                target_repetitions=1,
            )
        ])
        db.session.add(invalid_side_plan)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_legacy_assessment_record_relationship_remains_intact(self):
        legacy = AssessmentRecord(
            patient_id=self.patient.patient_id,
            exercise="Left Bicep Curl",
            repetitions=2,
            average_score=80,
            best_score=90,
            worst_score=70,
        )
        db.session.add(legacy)
        db.session.commit()
        self.assertEqual(self.patient.assessments[0].exercise, "Left Bicep Curl")


if __name__ == "__main__":
    unittest.main()
