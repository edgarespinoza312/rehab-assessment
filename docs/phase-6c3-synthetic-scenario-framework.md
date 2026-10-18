# Phase 6C.3 — Synthetic Progression Scenario Framework

## 1. Purpose

**Synthetic test behavior.** This phase adds a deterministic registry of
in-memory progression observations for validating future evidence and decision
software.

The framework represents historical observations only. It does not produce
recommendations, prescription changes, thresholds, clinical interpretations,
or decision outputs.

## 2. Why synthetic scenarios are necessary

**Observed.** Phase 6C.2 found that the configured database currently has no
patients, assessments, workout sessions, or workout exercise results.

**Synthetic test behavior.** The scenario registry supplies controlled
histories for software tests when no empirical dataset is available. The
scenarios make source, side, timestamp, resistance, cancellation, missingness,
and patient-isolation behavior reproducible.

## 3. Explicit non-clinical status

**Observed.** No scenario is sourced from a patient or clinical outcome.

**Synthetic test behavior.** Every identifier uses a `synthetic-patient-*`
label, every timestamp is fixed, and every value is deliberately constructed
for software validation.

Synthetic scenarios are **not**:

- clinical evidence;
- patient data;
- rehabilitation outcomes;
- validated progression criteria;
- recommendations or prescriptions.

**Future proposed behavior.** A future decision engine may consume these
scenarios as test inputs, but scenario characteristics must never be treated
as clinical validation.

## 4. Scenario registry

The registry is defined in:

```text
tests/support/progression_scenarios.py
```

It exposes:

```python
SCENARIOS: Mapping[str, ProgressionScenario]
get_scenario(scenario_id: str) -> ProgressionScenario
```

The stable scenario IDs are:

| ID | Synthetic characterization |
| --- | --- |
| `no_history` | No observations |
| `single_observation` | One complete right-sided workout observation |
| `consistent_performance` | Three repeated stable observations |
| `improving_performance` | Descriptively increasing completion and scores |
| `declining_performance` | Descriptively decreasing completion and scores |
| `inconsistent_performance` | Alternating strong and weak observations |
| `observed_resistance_increase` | Observed 5 lb then 7.5 lb |
| `observed_resistance_decrease` | Observed 7.5 lb then 5 lb |
| `mixed_resistance_units` | Separate `lb` and `kg` observations |
| `missing_resistance` | Resistance omitted from one observation |
| `left_right_independent_history` | Explicit left and right histories |
| `side_unspecified_legacy_history` | Legacy observations with `side=None` |
| `mixed_legacy_workout_history` | Both source types with provenance |
| `cancelled_session_with_completed_result` | Cancelled session retaining one result |
| `cancelled_session_without_completed_result` | Cancelled session with no result |
| `multiple_exercises` | Separate exercise identifiers for isolation tests |
| `multiple_patients` | Two synthetic patient identifiers |
| `sparse_irregular_timeline` | Fixed observations at irregular intervals |
| `missing_metric_fields` | Null scores, domain metrics, and resistance |
| `conflicting_data_quality` | Mixed units, null metrics, legacy data, cancellation |

## 5. Scenario representation

**Synthetic test behavior.** `ProgressionScenario` contains:

- stable `id`;
- human-readable `description`;
- immutable `observations`;
- descriptive `expected_characteristics`.

Each `SyntheticObservation` preserves:

- synthetic patient identifier;
- stable exercise identifier;
- explicit `left`/`right` side or null;
- deterministic timestamp;
- source type;
- session status;
- target and completed repetitions;
- optional aggregate/domain metrics;
- resistance value/unit/type;
- source/session identifiers.

No field represents a recommendation.

## 6. Data-generation rules

**Synthetic test behavior.**

- No randomness is used.
- Timestamps are deterministic relative to `2026-01-01 09:00:00`.
- Patient IDs are synthetic and non-identifying.
- Missing values remain `None`.
- Legacy observations retain `side=None`.
- Resistance units are preserved exactly as supplied.
- `lb` and `kg` are never converted or combined.
- Workout statuses are preserved as `completed` or `cancelled`.
- A cancelled session without a completed result is represented by no
  observation, preventing fabricated progression history.
- Stable scenario IDs are used instead of duplicating raw records in tests.

## 7. Expected characteristics

**Synthetic test behavior.** Each scenario derives descriptive expectations
from its immutable observations, including:

- observation count;
- source types;
- sides;
- resistance units;
- whether observations repeat;
- whether metrics are missing;
- cancelled-session counts;
- patient IDs;
- exercise IDs.

These are test assertions only. They do not state that any amount, pattern,
score, or resistance is sufficient for a clinical decision.

## 8. Isolation strategy

**Observed.** The configured database remains schema-only and is not a source
or destination for scenario construction.

**Synthetic test behavior.** The scenario module imports only Python standard
library modules. It does not import Flask, SQLAlchemy, application models,
progression services, or persistence helpers. Constructing or reading
`SCENARIOS` therefore cannot write to `dashboard/neuromotion.db`.

The contract test snapshots the configured database bytes and verifies that
construction leaves them unchanged. The test also verifies zero progression
rows.

No temporary database is required for this pure-domain fixture. If a future
adapter needs persistence integration, it must use an in-memory or temporary
SQLite database and must never target the configured file.

## 9. Testing strategy

Tests are in:

```text
tests/test_progression_scenarios.py
```

They verify:

1. all required stable scenario IDs exist;
2. every scenario is self-consistent with its expected characteristics;
3. repeated construction is deterministic;
4. patient and exercise identifiers remain isolated;
5. legacy sides remain null;
6. resistance units remain unchanged;
7. missing values remain null;
8. cancelled unfinished exercises do not become observations;
9. source provenance remains intact;
10. the configured database is not modified.

## 10. Future use by the decision engine

**Future proposed behavior.** A future evidence or decision layer may use the
registry to test:

- evidence sufficiency handling;
- source and side isolation;
- missing-metric behavior;
- resistance-unit refusal behavior;
- cancellation policy handling;
- deterministic explanations and provenance.

**Not implemented.** No scenario has an expected decision. The framework does
not contain values such as `increase_resistance`, `decrease_repetitions`, or
any other recommendation.

## 11. Limitations

**Observed.** The current built-in exercise registry exposes only
`bicep_curl`. The `multiple_exercises` scenario includes
`shoulder_abduction` as a stable synthetic fixture identifier for testing
exercise-key isolation, but that identifier is not currently registered by
the production exercise registry.

**TBD.** Before integrating that scenario with production exercise-registry
validation, the project must either add an approved stable exercise identity
through a separate feature phase or narrow the scenario to the currently
registered exercise set. This phase does not modify the production registry.

**Requires external/clinical validation.** Scenario patterns do not validate
clinical thresholds, progression criteria, appropriate resistance, or
rehabilitation outcomes.

## 12. Phase 6C.3 verdict

**Observed.** The framework is pure-domain, deterministic, and isolated from
the configured database.

**Synthetic test behavior.** All required scenario categories are represented
with stable IDs and descriptive expectations.

**Future proposed behavior.** The scenarios are ready to support future
software validation of evidence and decision boundaries, but they do not
authorize or implement any decision.

**PASS — Phase 6C.3 synthetic progression scenario framework is complete.**
