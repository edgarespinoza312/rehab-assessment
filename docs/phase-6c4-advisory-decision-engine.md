# Phase 6C.4 — Advisory Progression Decision Engine

## 1. Purpose

**Existing.** Revaliv already exposes descriptive progression observations.

**Software-validation heuristic.** This phase adds a pure service that
classifies a selected history into a conservative advisory category and
explains which observations were used.

The service answers:

> What does the available historical data appear to indicate?

It does not answer what a patient should be prescribed.

## 2. Advisory status

**Software-validation heuristic.** All classifications are experimental
software outputs based on deterministic rules chosen to exercise the synthetic
scenario framework.

**Requires external/clinical validation.** The rules, minimum history, score
behavior, completion behavior, cancellation handling, and all classifications
must be reviewed before clinical or patient-facing use.

**Explicit limitation.** Every result includes:

> This classification is based on software-validation heuristics and has not
> been clinically validated.

## 3. Decision categories

The service defines the stable enum:

```text
INSUFFICIENT_DATA
NO_CHANGE
REVIEW_REQUIRED
POSSIBLE_PROGRESSION
POSSIBLE_REGRESSION
```

**Software-validation heuristic.** These labels describe the shape of the
available synthetic/software evidence. `POSSIBLE_PROGRESSION` and
`POSSIBLE_REGRESSION` do not authorize progression, regression, or a
prescription change.

## 4. Evidence model

The pure service module is:

```text
dashboard/services/advisory_progression.py
```

It consumes immutable `AdvisoryEvidenceRecord` values containing:

- patient ID;
- stable exercise ID;
- explicit side or null;
- observation timestamp;
- source type and source ID;
- session status;
- target and completed repetitions;
- completion percentage derived only from valid repetition pairs;
- overall score;
- optional domain metrics;
- resistance value/unit/type.

**Existing.** `from_progression_result(...)` adapts the existing progression
projection without changing its semantics.

**Not implemented.** No database query, API endpoint, persistence mutation,
Workout Builder integration, SessionEngine integration, or prescription
adapter is included.

## 5. Software-validation heuristics

### 5.1 Minimum-history gate

**Software-validation heuristic.** `MINIMUM_HISTORY_OBSERVATIONS = 2`.

Histories with zero or one matching observation classify as
`INSUFFICIENT_DATA`. This value is intentionally small so the controlled
scenarios can exercise the engine. It is not a clinical minimum.

### 5.2 Directional patterns

**Software-validation heuristic.**

- `POSSIBLE_PROGRESSION` requires repeated observations with nondecreasing
  completion percentages, nondecreasing overall scores, and at least one
  completion increase.
- `POSSIBLE_REGRESSION` requires repeated observations with nonincreasing
  completion percentages, nonincreasing overall scores, and at least one
  completion decrease.
- Stable completion with no unfavorable directional pattern is classified as
  `NO_CHANGE`.
- Conflicting or non-directional signals classify as `REVIEW_REQUIRED`.

These are descriptive software rules. They do not define score cutoffs,
clinical pass/fail values, or treatment criteria.

### 5.3 Conservative gates

**Software-validation heuristic.**

- Mixed resistance units produce `REVIEW_REQUIRED`.
- Mixed legacy and workout sources produce `REVIEW_REQUIRED`.
- Missing overall scores produce `REVIEW_REQUIRED`.
- Missing target/completed repetition pairs produce
  `INSUFFICIENT_DATA`.
- Multiple explicit sides without a side-specific request produce
  `REVIEW_REQUIRED`.

**TBD.** The final evidence model, missingness policy, source comparability
policy, and uncertainty transitions require future validation.

## 6. Resistance handling

**Existing.** Resistance values, units, and types are retained as observations.

**Software-validation heuristic.** The engine reports resistance observations
in its explanation and refuses numeric classification when more than one unit
is present in the selected history.

**Not implemented.** There is no unit conversion, resistance normalization,
recommended resistance, prescribed resistance, or automatic workout change.

**Requires external/clinical validation.** Any interpretation of an observed
resistance increase or decrease.

## 7. Side handling

**Existing.** Workout sides are explicit and legacy side may be null.

**Software-validation heuristic.**

- A requested side filters to that exact side.
- Left and right are never merged for a side-specific request.
- A side-unspecified legacy history remains `None`.
- Multiple explicit sides without a requested side require review.
- Side is never inferred from an exercise name.

**TBD.** Any bilateral comparison or asymmetry interpretation requires
separate validation and is not implemented.

## 8. Cancellation handling

**Existing.** Completed exercise results from cancelled sessions are retained;
unfinished exercises do not create observations.

**Software-validation heuristic.** A retained cancelled-session result may be
included in the evidence records and is labeled with `session_status="cancelled"`.
Its presence is also reported as a limitation.

**TBD.** Whether cancelled observations should contribute to a future clinical
decision remains unresolved. This phase introduces no new cancellation policy.

## 9. Legacy handling

**Existing.** Legacy observations preserve source provenance, null side, and
missing resistance.

**Software-validation heuristic.** A legacy-only history lacking valid target
and completed repetition pairs remains `INSUFFICIENT_DATA`. Mixed legacy and
workout histories require review rather than being treated as interchangeable.

**Requires external/clinical validation.** Whether any legacy metric is
comparable to a workout metric for a particular exercise or use case.

## 10. Explainability

Every immutable `ProgressionDecision` contains:

- classification;
- patient, exercise, and side;
- ordered evidence records;
- observation count and dates;
- source types;
- score values;
- completion percentages;
- resistance observations;
- reasons for classification;
- limitations.

**Software-validation heuristic.** Reasons describe the observed pattern, for
example that repeated observations had nondecreasing completion and scores.
They do not use patient-facing language such as “ready to progress.”

## 11. Provenance

**Existing.** Each evidence record retains patient ID, stable exercise ID,
side, source type, source ID, timestamp, and session status.

**Software-validation heuristic.** The result returns references to the
selected immutable evidence records rather than duplicating a new historical
truth store.

## 12. Synthetic scenario validation

Tests in:

```text
tests/test_advisory_progression.py
```

exercise the Phase 6C.3 registry, including:

- no history and single-observation gates;
- consistent, improving, declining, and inconsistent patterns;
- observed resistance changes;
- mixed resistance units;
- missing resistance and metrics;
- left/right filtering;
- side-unspecified legacy data;
- mixed source history;
- cancelled results and absent unfinished results;
- multiple exercises and patients;
- conflicting evidence;
- deterministic repeated evaluation;
- absence of prescription or mutation fields.

The scenarios remain pure in-memory test data and are never inserted into
`dashboard/neuromotion.db`.

## 13. Explicit limitations

**Observed.** Phase 6C.2 found zero real progression observations in the
configured database.

**Software-validation heuristic.** The engine can demonstrate deterministic
classification and explanation behavior using controlled synthetic patterns.

**Not supported.** The engine cannot establish clinical sufficiency, clinical
readiness, safe progression, appropriate regression, or treatment impact.

**Requires external/clinical validation.** All clinical thresholds, decision
semantics, source-comparability rules, cancellation policies, resistance
interpretations, and human-review requirements.

## 14. Non-goals

This phase does not:

- prescribe resistance;
- prescribe repetitions;
- modify workouts;
- integrate with the Workout Builder;
- integrate with `SessionEngine`;
- add an API endpoint;
- modify scoring, biomechanics, perception, readiness, or calibration;
- modify persistence schemas or migrations;
- normalize resistance units;
- add clinical thresholds;
- claim clinical validity.

## 15. Future clinical-validation requirements

**TBD.** Before any patient-facing or clinical use, future work must validate:

1. evidence minimums and recency;
2. metric completeness and missingness semantics;
3. source comparability;
4. side-specific and bilateral reasoning;
5. cancelled-session treatment;
6. resistance-unit compatibility;
7. explanation and provenance requirements;
8. human review and authorization;
9. prospective validation against appropriate external evidence.

**Proposed.** Any future integration should remain a separate advisory
boundary and must not mutate prescriptions implicitly.

## 16. Phase 6C.4 verdict

**Observed.** A deterministic, immutable, service-level advisory classifier is
implemented without runtime integration.

**Software-validation heuristic.** The controlled scenarios exercise all five
decision categories and conservative ambiguity handling.

**PASS — Phase 6C.4 advisory progression decision engine is complete for
software validation only.**
