# Phase 6C.2 — Progression Evidence Validation

## 1. Objective

**Observed.** This report characterizes the progression evidence currently
available in the configured Revaliv database. It measures population, source,
side, repetition, resistance, metric, and temporal coverage without making a
clinical judgment.

**Explicit boundary.** This phase does not implement or validate progression
recommendations, prescription changes, clinical thresholds, adaptive rules, or
automatic decisions. A populated dataset would still require clinical and
domain validation before any such use.

## 2. Dataset provenance

**Observed.** The analysis was run against:

```text
dashboard/neuromotion.db
Alembic revision: 7d2c4e8a1f30
```

The database is structurally usable and contains the expected application
tables. At analysis time it contained no rows in `patients`,
`assessment_records`, `workout_sessions`, or
`workout_exercise_results`.

**Observed.** The retained recovery/test backups were also schema-only and
contained no progression rows. Therefore this report is based on an empty
available dataset, not on a clinical cohort and not on a synthetic validation
cohort with observations.

**Reproducible analysis.** The read-only inventory is implemented in
`scripts/phase6c2_evidence_inventory.py`. It uses SQLite queries only, does
not modify persisted data, does not normalize resistance units, and emits
JSON suitable for rerunning against a future database snapshot.

## 3. Dataset inventory

| Evidence dimension | Observed count |
| --- | ---: |
| Patients | 0 |
| Legacy assessments | 0 |
| Workout sessions | 0 |
| Completed workout sessions | 0 |
| Cancelled workout sessions | 0 |
| Workout exercise results | 0 |
| Distinct stable exercise IDs in results | 0 |
| Distinct explicit sides in results | 0 |
| Side-unspecified legacy records | 0 |
| Distinct resistance units | 0 |
| Distinct resistance types | 0 |

**Inference.** No current observation can support an exercise-level,
patient-level, temporal, bilateral, resistance, distributional, or
relationship analysis.

## 4. Exercise coverage

**Observed.** There are no stable exercise IDs with persisted workout results,
so no exercise-level coverage rows exist.

The following dimensions therefore have no observations:

- total observations;
- source mix;
- left/right/unspecified side mix;
- completed/cancelled session-status mix;
- resistance present versus absent;
- resistance units;
- resistance types;
- repeated observations over time.

**TBD.** No observation count is declared sufficient for clinical inference.
Future populated snapshots should describe histories as sparse, moderate, or
repeated only as descriptive labels, without treating those labels as clinical
sufficiency.

## 5. Metric completeness

### 5.1 Current result

**Observed.** Because there are zero observations, every metric has zero
present values and zero missing values. This is an empty-denominator result,
not evidence that the metrics are complete.

| Metric | Present | Missing | Current interpretation |
| --- | ---: | ---: | --- |
| Overall score | 0 | 0 | No observations |
| ROM score | 0 | 0 | No observations |
| Tempo score | 0 | 0 | No observations |
| Completion score | 0 | 0 | No observations |
| Stability score | 0 | 0 | No observations |
| Compensation score | 0 | 0 | No observations |
| Symmetry score | 0 | 0 | No observations |
| Target repetitions | 0 | 0 | No observations |
| Completed repetitions | 0 | 0 | No observations |
| Completion percentage | 0 | 0 | No observations |
| Resistance value | 0 | 0 | No observations |
| Resistance unit | 0 | 0 | No observations |
| Resistance type | 0 | 0 | No observations |
| Explicit side | 0 | 0 | No observations |
| Timestamp | 0 | 0 | No observations |
| Source type | 0 | 0 | No observations |
| Session status | 0 | 0 | No observations |

### 5.2 Schema and semantic distinctions

**Observed.** The current model permits the following distinctions when rows
exist:

- workout metric nulls are distinct from populated values;
- legacy records store repetitions, aggregate score, and creation time but do
  not store workout target repetitions, explicit side, resistance, or workout
  session status;
- workout session status is persisted as `completed` or `cancelled`;
- unfinished exercises are absent rather than fabricated as zero-result
  observations;
- completion percentage is derived only when completed and target repetitions
  are present and the target is positive.

**TBD.** The empty database cannot measure whether missing values in a future
snapshot are genuinely unavailable, not applicable, absent because an exercise
was incomplete, or absent because of legacy-schema limitations. A future
analysis must report those categories separately wherever source semantics
permit.

## 6. Temporal repetition

**Observed.** There are zero patient/exercise/side sequences, zero repeated
sequences, and no earliest/latest observation dates or inter-observation gaps.

| Temporal measure | Observed result |
| --- | ---: |
| Patient/exercise/side sequences | 0 |
| Sequences with more than one observation | 0 |
| Sequence lengths | Not applicable |
| Earliest observation | None |
| Latest observation | None |
| Time gaps | Not applicable |

**TBD.** No recency window, minimum sequence length, or acceptable gap has
been established. Those remain Phase 6C.1 unresolved validation questions.

## 7. Resistance history

**Observed.** There are zero resistance observations, zero units, and zero
resistance types. No same-unit sequence or change over time can be measured.

**Observed limitation.** The current workout result schema stores an observed
resistance value, unit, and type when supplied. It does not expose a separate
conceptual field that unambiguously records:

1. observed resistance;
2. prescribed resistance; and
3. future recommended resistance.

The progression projection therefore represents persisted resistance as
historical observed metadata. It must not be interpreted as a recommendation.

**TBD.** Unit compatibility, normalization, conversion, rounding, and
resistance-change interpretation require a separately validated contract.
This report performs no conversion and makes no progression interpretation.

## 8. Performance metric distributions

**Descriptive.** No descriptive statistics can be calculated from the current
dataset. The following metrics each have count zero:

- overall score;
- completion percentage;
- completed repetitions;
- target repetitions;
- ROM;
- tempo;
- stability;
- compensation;
- symmetry.

Minimum, maximum, mean, median, standard deviation, and interquartile range
are therefore not applicable.

**Inference.** No score range, repetition pattern, or metric combination can
be associated with readiness, progression, regression, or safety from this
snapshot.

## 9. Metric relationships

**Observed.** There are no paired observations with which to characterize:

- completion percentage and overall score;
- completed repetitions and overall score;
- resistance and overall score;
- resistance and completion percentage;
- ROM and overall score;
- compensation and overall score;
- stability and overall score;
- symmetry and overall score.

No correlations were calculated. There is no basis for causal or clinical
interpretation.

**TBD.** Future relationship analysis must report sample size, missingness,
source mix, side handling, unit handling, and whether repeated observations
come from the same patient. Sparse data must remain explicitly described as
insufficient for inference.

## 10. Bilateral and side analysis

**Observed.** There are no left observations, right observations, bilateral
patient/exercise sequences, side-specific score differences, completion
differences, repetition differences, resistance differences, or
side-availability differences.

**Observed semantic constraint.** Workout sides are explicit and limited by
the schema to `left` or `right`. Legacy assessments do not contain an explicit
side; the progression service preserves that as unspecified and does not infer
side from an exercise display name.

**TBD.** No clinically meaningful asymmetry threshold or side-comparison rule
has been established. Future bilateral analysis must keep left, right, and
side-unspecified evidence separate.

## 11. Cancelled-session analysis

**Observed.** There are zero cancelled sessions and zero workout results from
cancelled sessions. Consequently:

| Cancelled-session measure | Observed result |
| --- | ---: |
| Cancelled sessions | 0 |
| Cancelled sessions containing completed results | 0 |
| Completed results in cancelled sessions | 0 |
| Cancelled sessions with no result | 0 |
| Fabricated unfinished observations | 0 observed |

The final row reflects the absence of rows in the current database and the
existing persistence contract; it is not a claim about an unobserved future
dataset.

**Observed semantic constraint.** Existing persistence semantics retain
completed exercise results from a cancelled session and do not fabricate
unfinished exercise results. The effect of such retained results on a future
decision remains a policy question.

**TBD.** Whether cancelled-session results count, are down-weighted, or require
review cannot be determined from this empty snapshot and was not resolved by
Phase 6C.1.

## 12. Legacy/workout comparability

### 12.1 What the system can represent

**Observed.** The two sources have different contracts:

| Dimension | Legacy assessment | Workout result |
| --- | --- | --- |
| Stable exercise ID | Mapped only when display name exactly matches a registered profile | Persisted directly |
| Side | Unspecified (`None`) | Explicit left/right |
| Repetitions | One persisted repetition count | Target and completed repetitions |
| Completion percentage | Not available from the legacy record | Derived when target is valid |
| Overall score | Persisted | Persisted aggregate |
| Domain metrics | Not present in the legacy schema | ROM, tempo, completion, stability, compensation, symmetry when present |
| Resistance | Not present | Value/unit/type when supplied |
| Session status | No workout session status | Completed or cancelled |
| Timestamp | Assessment creation time | Workout session start time |
| Provenance | Assessment ID | Workout exercise-result ID and session |

### 12.2 Comparability conclusion

**Inference.** Matching field names such as `average_score` do not establish
that legacy and workout observations are clinically interchangeable. They
have different side, repetition, resistance, status, timestamp, and metric
semantics.

**TBD.** Comparability must be validated per exercise, metric, source, and
future decision use case. Missing legacy fields must not be manufactured.

## 13. Data-quality findings

### 13.1 Findings in the current snapshot

**Observed.**

- The database has no progression observations.
- No duplicated observations can be identified because there are no
  observations.
- No impossible values can be identified because there are no observations.
- No timestamp anomalies can be identified because there are no timestamps.
- No contradictory side, resistance, or metric records can be identified
  because there are no observations.
- No inconsistent resistance units are present in the current rows.

These are limits of observability, not evidence that future data will be
clean.

### 13.2 Structural limitations relevant to future analysis

**Observed.**

- Legacy records lack explicit side and resistance fields.
- Workout results preserve observed resistance but do not provide a separate
  recommended-resistance field.
- The current projection combines source histories for descriptive retrieval,
  while retaining source type and status; semantic comparability remains a
  validation question.
- The configured test/recovery workflow can leave a usable schema with no
  records after fixtures reset the database.

**TBD.** Duplicate detection policy, impossible-value policy beyond database
constraints, timestamp timezone policy, and contradictory-record resolution
remain to be specified for a populated evidence-validation dataset.

## 14. Evidence readiness matrix

| Evidence dimension | Current state | Supports future analysis? | Decision |
| --- | --- | --- | --- |
| Repeated observations | No observations or sequences | No, not from this snapshot | **TBD** |
| Side-specific history | No side observations | No, not from this snapshot | **TBD** |
| Resistance history | No resistance observations | No, not from this snapshot | **TBD** |
| Completion | No workout results | No, not from this snapshot | **TBD** |
| ROM | No values | No, not from this snapshot | **TBD** |
| Stability | No values | No, not from this snapshot | **TBD** |
| Compensation | No values | No, not from this snapshot | **TBD** |
| Symmetry | No values | No, not from this snapshot | **TBD** |
| Temporal history | No timestamps in observations | No, not from this snapshot | **TBD** |
| Legacy comparability | Schema differences are known; no rows to compare | Only as a future semantic-validation question | **TBD** |

The matrix does not define clinical sufficiency or a decision threshold.

## 15. Supported conclusions

### Supported by current data

- **Observed.** The configured database is structurally available at Alembic
  revision `7d2c4e8a1f30`.
- **Observed.** The current database contains zero patients and zero
  progression observations.
- **Observed.** The current snapshot cannot provide exercise coverage,
  temporal repetition, resistance history, bilateral evidence, cancellation
  frequencies, distributions, or metric relationships.
- **Observed.** The schema and progression architecture preserve important
  source distinctions, explicit workout sides, nullable legacy side, workout
  status, and resistance metadata.

### Plausible for future investigation

- **Descriptive.** A populated snapshot could characterize repeated
  patient/exercise/side sequences and time gaps.
- **Descriptive.** A populated snapshot could quantify metric missingness by
  source, session status, exercise, and side.
- **Descriptive.** A populated snapshot could describe compatible-unit
  resistance histories without converting units.
- **Descriptive.** A populated snapshot could compare left/right observations
  descriptively without defining an asymmetry threshold.
- **Descriptive.** A populated snapshot could explore metric relationships
  while reporting sparsity and avoiding causal interpretation.

### Not currently supported

- **Inference.** No recommendation, progression, regression, or no-change
  decision is supported.
- **Inference.** No readiness or safety conclusion is supported.
- **Inference.** No minimum observation count, recency window, score cutoff,
  repetition cutoff, or side-discrepancy threshold can be derived.
- **Inference.** No resistance increase can be interpreted as successful
  progression.
- **Inference.** Legacy and workout observations cannot be assumed clinically
  interchangeable.

### Requires external/clinical validation

- **Requires external/clinical validation.** Any clinical threshold or
  evidence-sufficiency rule.
- **Requires external/clinical validation.** Any interpretation of ROM, tempo,
  stability, compensation, symmetry, or overall score.
- **Requires external/clinical validation.** Any policy for cancelled-session
  evidence.
- **Requires external/clinical validation.** Any unit normalization or
  resistance recommendation.
- **Requires external/clinical validation.** Any automated or advisory
  prescription change.

## 16. Future validation requirements

**TBD.** A future evidence-validation snapshot should contain enough
non-identifying, representative records to evaluate:

1. multiple patients and exercises;
2. repeated left and right observations for the same patient/exercise;
3. side-unspecified legacy records alongside side-specific workouts;
4. completed and cancelled sessions, including cancelled sessions with and
   without completed exercise results;
5. populated and null domain metrics;
6. resistance observations with repeated compatible units and intentionally
   mixed units;
7. timestamp ordering and meaningful inter-observation gaps;
8. duplicate, contradictory, and boundary-value fixtures;
9. provenance and patient-isolation behavior;
10. reproducibility of all descriptive statistics.

**Requires external/clinical validation.** The future dataset must not be
treated as clinical evidence merely because it is larger. Clinical meaning,
thresholds, and decision policies require domain-owner and clinical review.

## 17. Phase 6C.2 verdict

**Observed.** The current database is usable but empty of progression data.

**Inference.** The current dataset is insufficient for any evidence-based
progression analysis beyond verifying that the schema and read-only analysis
path can represent the required dimensions.

**TBD.** Phase 6C.2 cannot resolve observation-count requirements, recency,
metric completeness rules, resistance-unit policy, side-discrepancy
boundaries, cancellation policy, confidence categories, or authorization
requirements.

**PASS — Phase 6C.2 evidence validation is complete as a dataset
characterization. No progression recommendation or clinical decision logic
was implemented.**
