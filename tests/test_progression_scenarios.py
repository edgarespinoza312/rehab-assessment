import sqlite3
import unittest
from dataclasses import asdict
from pathlib import Path

from tests.support.progression_scenarios import (
    SCENARIOS,
    get_scenario,
)


class ProgressionScenarioTests(unittest.TestCase):
    def test_registry_contains_all_required_stable_ids(self):
        expected = {
            "no_history",
            "single_observation",
            "consistent_performance",
            "improving_performance",
            "declining_performance",
            "inconsistent_performance",
            "observed_resistance_increase",
            "observed_resistance_decrease",
            "mixed_resistance_units",
            "missing_resistance",
            "left_right_independent_history",
            "side_unspecified_legacy_history",
            "mixed_legacy_workout_history",
            "cancelled_session_with_completed_result",
            "cancelled_session_without_completed_result",
            "multiple_exercises",
            "multiple_patients",
            "sparse_irregular_timeline",
            "missing_metric_fields",
            "conflicting_data_quality",
        }
        self.assertEqual(set(SCENARIOS), expected)
        self.assertEqual(
            set(SCENARIOS),
            {scenario.id for scenario in SCENARIOS.values()},
        )

    def test_every_scenario_matches_its_descriptive_characteristics(self):
        for scenario in SCENARIOS.values():
            expected = scenario.expected_characteristics
            observations = scenario.observations
            self.assertEqual(len(observations), expected.observation_count)
            self.assertEqual(
                tuple(sorted({item.source_type for item in observations})),
                expected.source_types,
            )
            self.assertEqual(
                tuple(sorted(
                    {item.side for item in observations},
                    key=lambda side: "" if side is None else side,
                )),
                expected.sides,
            )
            self.assertEqual(
                tuple(sorted({
                    item.resistance_unit
                    for item in observations
                    if item.resistance_unit is not None
                })),
                expected.resistance_units,
            )
            self.assertEqual(
                expected.patient_ids,
                tuple(sorted({item.patient_id for item in observations})),
            )
            self.assertEqual(
                expected.exercise_ids,
                tuple(sorted({item.exercise_id for item in observations})),
            )
            self.assertEqual(
                expected.repeated_observations,
                len(observations) > 1,
            )

    def test_scenario_construction_is_deterministic(self):
        for scenario_id in SCENARIOS:
            self.assertEqual(
                asdict(get_scenario(scenario_id)),
                asdict(get_scenario(scenario_id)),
            )

    def test_observation_semantics_are_preserved(self):
        self.assertEqual(
            [item.side for item in
             SCENARIOS["side_unspecified_legacy_history"].observations],
            [None, None],
        )
        self.assertEqual(
            [
                (item.resistance_value, item.resistance_unit)
                for item in SCENARIOS["mixed_resistance_units"].observations
            ],
            [(5, "lb"), (2.5, "kg"), (5, "lb")],
        )
        self.assertIsNone(
            SCENARIOS["missing_resistance"].observations[1].resistance_value
        )
        self.assertIsNone(
            SCENARIOS["missing_metric_fields"].observations[0].overall_score
        )
        self.assertEqual(
            {
                item.source_type
                for item in SCENARIOS["mixed_legacy_workout_history"].observations
            },
            {"legacy_assessment", "workout"},
        )

    def test_cancelled_without_result_has_no_fabricated_observation(self):
        scenario = get_scenario("cancelled_session_without_completed_result")
        self.assertEqual(scenario.observations, ())
        self.assertEqual(
            scenario.expected_characteristics.cancelled_sessions_without_results,
            1,
        )

    def test_patient_and_exercise_isolation_are_explicit(self):
        patients = SCENARIOS["multiple_patients"].observations
        self.assertEqual(
            {item.patient_id for item in patients},
            {"synthetic-patient-001", "synthetic-patient-002"},
        )
        exercises = SCENARIOS["multiple_exercises"].observations
        self.assertEqual(
            {item.exercise_id for item in exercises},
            {"bicep_curl", "shoulder_abduction"},
        )

    def test_registry_construction_does_not_write_configured_database(self):
        database = Path("dashboard/neuromotion.db")
        before = database.read_bytes()
        _ = tuple(SCENARIOS.values())
        after = database.read_bytes()
        self.assertEqual(before, after)



if __name__ == "__main__":
    unittest.main()
