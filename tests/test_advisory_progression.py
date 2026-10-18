import unittest

from dashboard.services.advisory_progression import (
    AdvisoryEvidenceRecord,
    ProgressionClassification,
    evaluate_progression,
)
from tests.support.progression_scenarios import SCENARIOS


def _records(scenario_id):
    return tuple(
        AdvisoryEvidenceRecord(
            patient_id=item.patient_id,
            exercise_id=item.exercise_id,
            side=item.side,
            occurred_at=item.occurred_at,
            source_type=item.source_type,
            session_status=item.session_status,
            completed_repetitions=item.completed_repetitions,
            target_repetitions=item.target_repetitions,
            overall_score=item.overall_score,
            rom_score=item.rom_score,
            tempo_score=item.tempo_score,
            stability_score=item.stability_score,
            compensation_score=item.compensation_score,
            symmetry_score=item.symmetry_score,
            resistance_value=item.resistance_value,
            resistance_unit=item.resistance_unit,
            resistance_type=item.resistance_type,
            source_id=item.source_id,
        )
        for item in SCENARIOS[scenario_id].observations
    )


class AdvisoryProgressionTests(unittest.TestCase):
    def evaluate(self, scenario_id, **kwargs):
        records = _records(scenario_id)
        return evaluate_progression(
            records,
            patient_id=kwargs.pop("patient_id", "synthetic-patient-001"),
            exercise_id=kwargs.pop("exercise_id", "bicep_curl"),
            **kwargs,
        )

    def test_decision_categories_and_history_gate(self):
        self.assertEqual(
            self.evaluate("no_history").classification,
            ProgressionClassification.INSUFFICIENT_DATA,
        )
        self.assertEqual(
            self.evaluate("single_observation").classification,
            ProgressionClassification.INSUFFICIENT_DATA,
        )
        self.assertEqual(
            self.evaluate("consistent_performance").classification,
            ProgressionClassification.NO_CHANGE,
        )
        self.assertEqual(
            self.evaluate("improving_performance").classification,
            ProgressionClassification.POSSIBLE_PROGRESSION,
        )
        self.assertEqual(
            self.evaluate("declining_performance").classification,
            ProgressionClassification.POSSIBLE_REGRESSION,
        )
        self.assertEqual(
            self.evaluate("inconsistent_performance").classification,
            ProgressionClassification.REVIEW_REQUIRED,
        )

    def test_resistance_is_observational_and_mixed_units_require_review(self):
        increase = self.evaluate("observed_resistance_increase")
        decrease = self.evaluate("observed_resistance_decrease")
        self.assertEqual(
            increase.classification,
            ProgressionClassification.NO_CHANGE,
        )
        self.assertEqual(
            decrease.classification,
            ProgressionClassification.REVIEW_REQUIRED,
        )
        self.assertEqual(
            self.evaluate("mixed_resistance_units").classification,
            ProgressionClassification.REVIEW_REQUIRED,
        )
        for decision in (increase, decrease):
            self.assertFalse(hasattr(decision, "recommended_resistance"))
            self.assertFalse(hasattr(decision, "recommended_repetitions"))
            self.assertIn("resistance_observations", decision.evidence_summary.__dict__)

    def test_side_and_patient_isolation(self):
        scenario = _records("left_right_independent_history")
        left = evaluate_progression(
            scenario,
            patient_id="synthetic-patient-001",
            exercise_id="bicep_curl",
            side="left",
        )
        right = evaluate_progression(
            scenario,
            patient_id="synthetic-patient-001",
            exercise_id="bicep_curl",
            side="right",
        )
        self.assertEqual(len(left.evidence_records), 2)
        self.assertEqual(len(right.evidence_records), 2)
        self.assertTrue(all(item.side == "left" for item in left.evidence_records))
        self.assertTrue(all(item.side == "right" for item in right.evidence_records))
        self.assertEqual(
            self.evaluate("multiple_patients", patient_id="synthetic-patient-002")
            .evidence_records[0].patient_id,
            "synthetic-patient-002",
        )
        self.assertEqual(
            self.evaluate("multiple_exercises", exercise_id="shoulder_abduction")
            .evidence_records[0].exercise_id,
            "shoulder_abduction",
        )

    def test_legacy_and_missing_data_are_conservative(self):
        legacy = self.evaluate("side_unspecified_legacy_history")
        self.assertEqual(legacy.side, None)
        self.assertEqual(legacy.classification, ProgressionClassification.INSUFFICIENT_DATA)
        self.assertTrue(all(item.side is None for item in legacy.evidence_records))
        self.assertEqual(
            self.evaluate("mixed_legacy_workout_history").classification,
            ProgressionClassification.REVIEW_REQUIRED,
        )
        self.assertEqual(
            self.evaluate("missing_resistance").classification,
            ProgressionClassification.NO_CHANGE,
        )
        self.assertEqual(
            self.evaluate("missing_metric_fields").classification,
            ProgressionClassification.INSUFFICIENT_DATA,
        )

    def test_cancellation_and_conflicting_evidence_preserve_provenance(self):
        cancelled = self.evaluate("cancelled_session_with_completed_result")
        self.assertEqual(
            cancelled.classification,
            ProgressionClassification.INSUFFICIENT_DATA,
        )
        self.assertEqual(cancelled.evidence_records[0].session_status, "cancelled")
        self.assertEqual(
            self.evaluate("cancelled_session_without_completed_result").classification,
            ProgressionClassification.INSUFFICIENT_DATA,
        )
        self.assertEqual(
            len(self.evaluate("cancelled_session_without_completed_result").evidence_records),
            0,
        )
        self.assertEqual(
            self.evaluate("conflicting_data_quality").classification,
            ProgressionClassification.REVIEW_REQUIRED,
        )

    def test_explanation_is_machine_readable_and_deterministic(self):
        first = self.evaluate("improving_performance")
        second = self.evaluate("improving_performance")
        self.assertEqual(first, second)
        self.assertEqual(first.evidence_summary.observation_count, 3)
        self.assertEqual(len(first.evidence_summary.observation_dates), 3)
        self.assertEqual(first.evidence_summary.source_types, ("workout",))
        self.assertEqual(first.evidence_summary.side, "right")
        self.assertAlmostEqual(
            first.evidence_summary.completion_percentages[0],
            200 / 3,
        )
        self.assertEqual(
            first.evidence_summary.completion_percentages[1:],
            (100.0, 100.0),
        )
        self.assertTrue(first.evidence_summary.reasons)
        self.assertTrue(first.limitations)
        self.assertIn("not been clinically validated", first.limitations[0])

    def test_no_prescription_or_mutation_surface_exists(self):
        decision = self.evaluate("improving_performance")
        fields = set(decision.__dataclass_fields__)
        self.assertNotIn("recommended_resistance", fields)
        self.assertNotIn("recommended_repetitions", fields)
        self.assertNotIn("workout_mutations", fields)
        self.assertEqual(
            SCENARIOS["improving_performance"].observations[0].resistance_value,
            5,
        )


if __name__ == "__main__":
    unittest.main()
