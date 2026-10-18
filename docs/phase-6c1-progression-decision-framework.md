# Phase 6C.1 — Progression Decision Framework Specification

## 1. Purpose

**Proposed.** This document defines the evidence, safety, provenance, uncertainty,
and review boundaries that a future progression-decision layer would need to
follow.

**Existing / implemented.** Revaliv currently reports historical observations
through `ProgressionResult`, `get_patient_progression(...)`,
`ProgressionContext`, `get_patient_progression_context(...)`, and their
read-only HTTP APIs.

**Proposed.** A future decision layer may interpret those observations only
after the evidence and validation requirements in this document have been
implemented and clinically reviewed.

**Explicit boundary.** The current system is descriptive:

> This is what happened previously.

It does not conclude what the patient should do next.

## 2. Current capabilities

| Status | Capability |
| --- | --- |
| **Existing / implemented** | Persisted workout sessions and exercise results |
| **Existing / implemented** | Legacy `AssessmentRecord` history |
| **Existing / implemented** | Stable exercise IDs |
| **Existing / implemented** | Explicit workout side |
| **Existing / implemented** | Legacy side may be `None` |
| **Existing / implemented** | Target and completed repetitions |
| **Existing / implemented** | Completion percentage where the target is valid |
| **Existing / implemented** | Aggregate and domain assessment metrics where persisted |
| **Existing / implemented** | Resistance value, unit, and type where supplied |
| **Existing / implemented** | Completed exercise results from cancelled sessions |
| **Existing / implemented** | Deterministic chronological ordering |
| **Existing / implemented** | Patient-specific progression and context retrieval |
| **Existing / implemented** | Read-only progression and context APIs |
| **Existing / implemented** | Descriptive Builder history UI |
| **Proposed** | A separate decision service consuming the existing projections |
| **TBD / requires validation** | Any rule, threshold, recommendation, or automatic action |

## 3. Terminology

| Term | Status | Definition |
| --- | --- | --- |
| Observation | **Existing / implemented** | One projected historical result from a legacy assessment or workout exercise result |
| Observed resistance | **Existing / implemented** | Resistance recorded as used or persisted for an observation |
| Prescribed resistance | **Proposed** | Resistance assigned by a workout plan or prescription for a future decision input |
| Recommended resistance | **Proposed** | A future advisory output; it is not present in the current system |
| Target repetitions | **Existing / implemented** | Repetitions prescribed for a persisted workout result |
| Completed repetitions | **Existing / implemented** | Repetitions actually persisted as completed |
| Prescribed repetitions | **Proposed** | The repetitions assigned before execution, potentially from a future prescription source |
| Recommended repetitions | **Proposed** | A future advisory output; it must not be inferred from target completion |
| Decision | **Proposed** | A future, explainable advisory classification based on validated evidence |
| Clinical threshold | **TBD / requires validation** | Any numerical or categorical boundary with clinical meaning |

## 4. Evidence model

### 4.1 Required evidence dimensions

The following dimensions should be considered by a future decision service.
Their availability does not by itself authorize a decision.

| Evidence | Status | Required handling |
| --- | --- | --- |
| Patient identity | **Existing / implemented** | Every query and decision must be patient-scoped |
| Stable exercise ID | **Existing / implemented** | Group observations by stable identity, never display-name parsing |
| Explicit side | **Existing / implemented** | Preserve `left`, `right`, or unknown; do not infer missing side |
| Observation date/time | **Existing / implemented** | Use the canonical deterministic order |
| Number of observations | **Existing / implemented** | Expose count and require a future validated minimum |
| Completed vs cancelled status | **Existing / implemented** | Preserve session status for workout observations |
| Completion percentage | **Existing / implemented** | Consume the persisted repetition values and canonical calculation |
| Overall score | **Existing / implemented** | Consume the persisted aggregate score without recalculation |
| ROM | **Existing / implemented** | Use only when persisted and present |
| Tempo | **Existing / implemented** | Use only when persisted and present |
| Stability | **Existing / implemented** | Use only when persisted and present |
| Compensation | **Existing / implemented** | Use only when persisted and present |
| Symmetry | **Existing / implemented** | Use only when persisted and present |
| Repetition consistency | **Proposed** | Define and validate a method for comparing repeated observations |
| Resistance consistency | **Proposed** | Compare only compatible units and clearly identified observations |
| Recency | **Existing / implemented** | Dates are available; recency windows and meaning are not established |
| Minimum observation count | **TBD / requires validation** | No validated count currently exists |
| Metric completeness requirement | **TBD / requires validation** | Missing metrics must not be silently treated as zero |
| Recency window | **TBD / requires validation** | No clinically validated time window exists |

### 4.2 Evidence sufficiency

**Proposed.** A future decision request should produce an evidence assessment
before producing any candidate category. That assessment should state:

- how many observations were available;
- how many were completed workout exercise results;
- how many came from cancelled sessions;
- how many were legacy assessments;
- which side values were known;
- which metrics were present or missing;
- which resistance units were present;
- the date range and age of the latest observation;
- whether observations were internally consistent.

**TBD / requires validation.** The minimum count, acceptable proportion of
cancelled observations, acceptable metric completeness, and acceptable recency
must be established through validation. No current implementation may assume
that one successful observation is sufficient.

## 5. Candidate decision categories

**Proposed.** A future decision layer may use categories such as:

```text
NO_CHANGE
CONSIDER_PROGRESSION
CONSIDER_REGRESSION
INSUFFICIENT_DATA
REVIEW_REQUIRED
```

These are advisory classifications, not clinical conclusions.

**TBD / requires validation.** The evidence rules that distinguish these
categories are not established. In particular:

- `CONSIDER_PROGRESSION` must not mean that progression is safe or required;
- `CONSIDER_REGRESSION` must not mean that a treatment change is indicated;
- `NO_CHANGE` must not imply that the current prescription is clinically optimal;
- `REVIEW_REQUIRED` must be available whenever evidence conflicts or safety
  gates cannot be evaluated;
- `INSUFFICIENT_DATA` must be preferred over guessing.

**Explicit non-implementation.** No category, evaluator, or recommendation is
implemented by Phases 6A–6C.1.

## 6. Resistance progression

### 6.1 Distinct concepts

| Concept | Status | Meaning |
| --- | --- | --- |
| Observed resistance | **Existing / implemented** | Value, unit, and type persisted with a workout result when available |
| Prescribed resistance | **Proposed** | Value assigned by a workout plan or future prescription record |
| Recommended resistance | **Proposed** | Future advisory output requiring validation and review |

**Proposed.** A future service must retain these as separate fields and must
never derive a recommendation merely because an observed value was completed.

### 6.2 Unit handling

**Existing / implemented.** The current system preserves resistance value, unit,
and type without conversion.

**Proposed.** A future decision layer may compare resistance observations only
when their units are explicitly compatible under a validated contract.

**TBD / requires validation.** Unit normalization, conversion accuracy, source
trust, rounding, and mixed-unit comparison rules are not defined.

**Safety rule.** `5 lb` and `2.5 kg` must not be treated as numerically
comparable by default. Null resistance and unknown units remain unknown.

## 7. Repetition progression

| Field | Status | Handling |
| --- | --- | --- |
| Target repetitions | **Existing / implemented** | Historical workout target |
| Completed repetitions | **Existing / implemented** | Historical persisted completion |
| Prescribed repetitions | **Proposed** | Future input representing an assigned prescription |
| Recommended repetitions | **Proposed** | Future advisory output |

**Proposed.** A future system should compare target and completed repetitions
as separate observations and should account for session status, consistency,
side, and metric completeness.

**Safety rule.** Completing a target does not automatically justify increasing
the target. A future decision must not infer recommended repetitions from one
completion percentage or one session.

**TBD / requires validation.** Minimum repetition consistency, acceptable
completion patterns, and any relationship between repetition performance and
future prescription remain undefined.

## 8. Clinical safety gates

**Proposed.** The following conditions should block automatic progression or
route the case to review:

- insufficient observation count;
- stale or outside-window history;
- low overall performance;
- poor ROM;
- excessive compensation;
- instability;
- meaningful left/right discrepancy;
- inconsistent repeated performance;
- recent cancellation or repeated cancellations;
- missing required metrics;
- conflicting observations;
- unknown or incompatible resistance units;
- ambiguous or unknown side;
- mixed legacy and workout evidence whose semantics are not comparable;
- missing provenance for a source observation.

**Existing / implemented.** The data layer preserves many of the signals
needed to evaluate these gates, including source type, session status, side,
metric nulls, and resistance units.

**TBD / requires validation.** No numerical threshold, discrepancy boundary,
recency window, or cancellation policy is currently clinically validated.
Until such validation exists, these gates may only be represented as
unresolved review conditions, not automated rules.

## 9. Side handling

**Existing / implemented.** Workout sides are explicit. Legacy assessments may
have `side=None`. The progression service filters sides structurally.

**Proposed.** A future decision key should include:

```text
patient_id + exercise_id + side
```

Left and right histories must remain separate whenever side-specific evidence
matters.

| Situation | Status | Required future behavior |
| --- | --- | --- |
| Only left history | **Proposed** | Evaluate left only; do not infer right |
| Only right history | **Proposed** | Evaluate right only; do not infer left |
| Both sides | **Proposed** | Evaluate independently and compare only under a validated comparison rule |
| Side unspecified | **Existing / implemented** | Preserve as unknown; do not assign left or right |
| Side-independent prescription | **Proposed** | Present available side-specific and unspecified evidence separately |
| Side ambiguity | **Proposed** | Block automatic side-specific action and require review |
| Side discrepancy threshold | **TBD / requires validation** | No validated numerical boundary exists |

## 10. Legacy data handling

**Existing / implemented.** Legacy `AssessmentRecord` history can provide
exercise identity where the display name maps exactly to a registered profile,
completed repetitions, overall score, and observation time.

**Existing / implemented.** Legacy records do not safely provide:

- explicit side;
- resistance value;
- resistance unit;
- resistance type;
- workout target repetitions;
- workout session status.

These fields remain null or use the established legacy status semantics.

**Proposed.** A future decision layer may use legacy records as historical
context only when the metric semantics are comparable to the decision being
considered. It must label legacy evidence separately from workout evidence.

**Safety rule.** Missing legacy fields must remain missing. Side must not be
parsed from labels such as `"Left Bicep Curl"` or `"Right Bicep Curl"`.

**TBD / requires validation.** Whether any legacy score or repetition field is
comparable to a particular workout metric requires explicit validation per
exercise and use case.

## 11. Cancelled-session handling

**Existing / implemented.** A cancelled session persists only exercise results
that actually completed. Unfinished exercises have no fabricated result.

| Record | Status | Future interpretation |
| --- | --- | --- |
| Completed exercise in completed session | **Existing / implemented** | Valid historical workout observation, subject to future evidence gates |
| Completed exercise in cancelled session | **Existing / implemented** | Historical observation retains `session_status=cancelled` |
| Cancelled exercise with no completed result | **Existing / implemented** | No observation exists |
| Unfinished exercise | **Existing / implemented** | Must not become a zero-result or failed-result observation |
| Cancellation as a safety signal | **Proposed** | May contribute to review evidence, subject to validation |
| Cancellation threshold | **TBD / requires validation** | No automatic rule is defined |

**Proposed.** A future decision layer should distinguish the exercise result
from the session outcome. It should not discard a valid completed result solely
because the surrounding session was cancelled, but should retain the cancelled
status as context.

## 12. Uncertainty

**Proposed.** Future decisions should expose categorical uncertainty rather than
an invented numerical confidence score unless a validated scoring model exists.

Suggested dimensions:

- `evidence_quantity`: `unknown`, `limited`, `sufficient`, or `not_evaluated`;
- `evidence_consistency`: `unknown`, `inconsistent`, `mixed`, or `consistent`;
- `metric_completeness`: `missing`, `partial`, or `complete`;
- `recency`: `unknown`, `stale`, `recent`, or `not_evaluated`;
- `side_certainty`: `unknown`, `explicit`, or `not_applicable`;
- `resistance_unit_certainty`: `unknown`, `single_compatible_unit`,
  `mixed_units`, or `not_applicable`.

**TBD / requires validation.** The categories, transitions, and minimum
evidence required for each uncertainty state require validation. They must not
be presented as clinical confidence.

## 13. Human review

| Layer | Status | Meaning |
| --- | --- | --- |
| Descriptive history | **Existing / implemented** | Reports persisted observations without interpretation |
| Advisory decision | **Proposed** | Presents a candidate category and evidence explanation |
| Clinician/user review | **Proposed** | Human evaluates the advisory output and context |
| Automatic prescription | **Proposed** | Separate, higher-risk capability requiring explicit authorization and validation |

**Proposed.** Human review should remain required when evidence is insufficient,
metrics conflict, side is ambiguous, resistance units are incompatible,
performance is unstable, or any safety gate is unresolved.

**TBD / requires validation.** The role, authorization, audit requirements,
override behavior, and approval workflow for human review are not defined.

## 14. Explainability

**Proposed.** Any future advisory output should include an explanation object
with a structure conceptually similar to:

```text
decision_category
summary
observations_used[]
metrics_considered[]
metrics_missing[]
safety_gates[]
uncertainty[]
unit_handling
review_required
```

Each item in `observations_used[]` should identify the patient, stable exercise
ID, side, source type, source/session ID where available, observation date, and
metric values used.

**TBD / requires validation.** The exact wording, localization, display
requirements, and clinician audit format are not established.

**Safety rule.** Explanations must describe evidence and uncertainty. They must
not overstate causation, clinical validity, or certainty.

## 15. Data provenance

**Existing / implemented.** Current projections retain patient identity,
exercise identity, side, source type, observation date, session status, and
metric values exposed by the source.

**Proposed.** A future decision result should retain references to every source
observation used:

```text
patient_id
exercise_id
side
source_type
source_id or session/result identity
observation_at
session_status
metric values
resistance value/unit/type
```

**Proposed.** Provenance should be references or immutable snapshots in the
decision output, not duplicated historical truth in a new progression table.

**TBD / requires validation.** The final source-ID contract for legacy and
workout observations must be made public by the service boundary before a
decision engine is implemented.

## 16. Validation requirements

**Proposed.** Before implementing any decision logic, validation should cover:

1. deterministic unit-compatible resistance comparisons;
2. mixed-unit refusal behavior;
3. left/right isolation and missing-side handling;
4. legacy/workout semantic comparability;
5. completed versus cancelled session treatment;
6. missing metric behavior;
7. inconsistent and conflicting histories;
8. stale history behavior;
9. patient isolation;
10. deterministic repeated evaluations;
11. provenance completeness;
12. explanation completeness;
13. human-review routing;
14. regression protection for all descriptive APIs and Builder history UI.

**TBD / requires validation.** Clinical thresholds, decision category rules,
confidence/uncertainty transitions, and any prescription impact require
domain-owner and clinical validation before production implementation.

## 17. Explicit non-goals

**Existing / implemented boundary.** The current system does not perform any of
the following:

- change workout prescriptions;
- modify `SessionEngine`;
- modify exercise profiles;
- modify scoring;
- modify biomechanics;
- modify readiness or calibration;
- create recommendation UI;
- run adaptive algorithms;
- apply clinical thresholds;
- claim clinical validity;
- convert resistance units;
- use machine learning;
- add progression database tables;
- modify persistence schemas;
- perform automatic treatment decisions.

**Proposed boundary.** A future decision layer must remain separate from the
domain workout engine and descriptive persistence/progression projections.

## 18. Future implementation boundary

**Proposed.** A future implementation should introduce a separate service
boundary, conceptually:

```text
Progression projections
        ↓
Evidence assessment
        ↓
Safety gates and uncertainty
        ↓
Advisory decision classification
        ↓
Human review / explicit authorization
        ↓
Optional separately approved prescription workflow
```

**Proposed.** The future service should consume
`get_patient_progression(...)` or
`get_patient_progression_context(...)`, never duplicate their database
queries, and never move database dependencies into `core/workout/engine.py`.

**TBD / requires validation.** The service interface, persistence of advisory
decisions, authorization model, audit trail, clinical validation protocol, and
integration point with the Workout Builder are intentionally undefined.

**Existing / implemented.** Phase 6C.1 adds no decision service, no
recommendation endpoint, no prescription mutation, and no UI change.
