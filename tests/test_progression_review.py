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
from dashboard.services.advisory_progression import (
    AdvisoryEvidenceRecord,
    evaluate_progression,
)
from dashboard.services.progression_review import (
    advisory_fingerprint,
    create_review_event,
    list_review_events,
    normalize_note,
    normalize_reviewer_reference,
)


class ProgressionReviewServiceTests(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.context = self.app.app_context()
        self.context.push()
        db.session.rollback()
        db.drop_all()
        db.create_all()
        db.session.add_all([
            Patient(patient_id=1, first_name="A", last_name="Patient"),
            ExerciseIdentity(exercise_id="bicep_curl"),
        ])
        db.session.commit()

    def tearDown(self):
        db.session.rollback()
        db.drop_all()
        self.context.pop()

    def _decision(self):
        evidence = (
            AdvisoryEvidenceRecord(
                patient_id=1,
                exercise_id="bicep_curl",
                side="right",
                occurred_at=datetime(2026, 1, 1),
                source_type="workout",
                session_status="completed",
                completed_repetitions=2,
                target_repetitions=3,
                overall_score=70,
                source_id=10,
            ),
            AdvisoryEvidenceRecord(
                patient_id=1,
                exercise_id="bicep_curl",
                side="right",
                occurred_at=datetime(2026, 1, 2),
                source_type="workout",
                session_status="completed",
                completed_repetitions=3,
                target_repetitions=3,
                overall_score=80,
                source_id=11,
            ),
        )
        return evaluate_progression(
            evidence,
            patient_id=1,
            exercise_id="bicep_curl",
            side="right",
        )

    def test_fingerprint_is_stable_and_changes_with_relevant_evidence(self):
        first = self._decision()
        second = self._decision()
        self.assertEqual(advisory_fingerprint(first), advisory_fingerprint(second))
        changed = evaluate_progression(
            (
                *first.evidence_records[:-1],
                AdvisoryEvidenceRecord(
                    **{
                        **first.evidence_records[-1].__dict__,
                        "overall_score": 81,
                    }
                ),
            ),
            patient_id=1,
            exercise_id="bicep_curl",
            side="right",
        )
        self.assertNotEqual(
            advisory_fingerprint(first),
            advisory_fingerprint(changed),
        )

    def test_append_only_reviews_preserve_history_and_latest(self):
        decision = self._decision()
        first = create_review_event(
            decision,
            reviewer_reference="reviewer_demo_01",
            disposition="REVIEWED",
            note="First review",
            reviewed_at=datetime(2026, 2, 1),
        )
        second = create_review_event(
            decision,
            reviewer_reference="reviewer_demo_02",
            disposition="ACKNOWLEDGED",
            note="Second review",
            reviewed_at=datetime(2026, 2, 2),
        )
        history = list_review_events(
            1,
            exercise_id="bicep_curl",
            side="right",
            fingerprint=advisory_fingerprint(decision),
        )
        self.assertEqual([event.review_event_id for event in history], [
            first.review_event_id,
            second.review_event_id,
        ])
        self.assertEqual(history[0].disposition, "REVIEWED")
        self.assertEqual(history[-1].disposition, "ACKNOWLEDGED")
        self.assertEqual(history[0].note, "First review")

    def test_validation_and_no_evidence_guard(self):
        with self.assertRaises(ValueError):
            normalize_reviewer_reference(" ")
        with self.assertRaises(ValueError):
            normalize_reviewer_reference("x" * 121)
        self.assertIsNone(normalize_note("  "))
        with self.assertRaises(ValueError):
            normalize_note("x" * 2001)
        empty = evaluate_progression(
            (),
            patient_id=1,
            exercise_id="bicep_curl",
            side="right",
        )
        with self.assertRaises(ValueError):
            create_review_event(
                empty,
                reviewer_reference="reviewer",
                disposition="REVIEWED",
            )


if __name__ == "__main__":
    unittest.main()
