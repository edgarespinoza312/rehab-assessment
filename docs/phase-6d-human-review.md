# Phase 6D — Human Review / Advisory Presentation

## 1. Purpose

Phase 6D presents the existing Phase 6C.4 advisory classification in a
read-only, provenance-preserving review surface.

**Phase 6D provides human-readable presentation of a deterministic
software-validation heuristic. It does not establish clinical validity or
provide clinical recommendations.**

## 2. Existing 6C.4 advisory architecture

**Existing.** `dashboard/services/advisory_progression.py` remains the sole
source of classification. It produces immutable decisions with:

- patient, exercise, and side;
- one of the five stable classifications;
- evidence summary;
- evidence records;
- limitations.

**Existing.** The service remains independent of Flask, SQLAlchemy,
persistence, and workout execution.

**Implemented in Phase 6D.** The read-only endpoint
`GET /api/patients/<patient_id>/progression/advisory` adapts canonical
progression results into advisory evidence records and serializes the
authoritative decision. It does not duplicate classification heuristics.

## 3. Review workflow

**Implemented.** The existing patient progression page now includes
`Progression Advisory Review`. A reviewer selects the existing exercise and
side controls, then sees:

1. selected exercise, side, and observation count;
2. software classification;
3. classification reasons;
4. observed evidence in a semantic table;
5. source provenance and session status;
6. explicit limitations.

The surface is descriptive and read-only. It does not update patient records,
plans, prescriptions, SessionEngine state, or live workout state.

## 4. Observed evidence vs software interpretation

**Observed data.** The evidence table displays:

- observation date/time;
- stable exercise identifier;
- explicit side or `Unspecified`;
- source type;
- session status;
- completed and target repetitions;
- completion percentage;
- overall score;
- observed resistance exactly as supplied;
- source identifier where available.

**Software interpretation.** The classification and reasons are displayed in
a separate `Software Classification` section. The UI does not recalculate
directional patterns or otherwise reproduce the advisory service heuristics.

**Limitations.** Engine-generated limitations are displayed separately from
observations and classification.

## 5. Classification presentation

The five categories are presented as software classifications:

- `INSUFFICIENT_DATA` — the selected history does not meet the configured
  software-validation evidence gate;
- `NO_CHANGE` — no directional pattern was detected by the software heuristic;
- `REVIEW_REQUIRED` — ambiguity or conflicting evidence requires human review;
- `POSSIBLE_PROGRESSION` — a possible software-detected pattern, not approval
  to change a workout;
- `POSSIBLE_REGRESSION` — a possible software-detected pattern, not a
  clinical regression statement.

**Software-validation heuristic.** Color and layout provide visual grouping
only; the exact classification and explanatory text remain available as text.
No category is represented as a prescription or clinical fact.

## 6. Provenance

**Existing.** The endpoint obtains records through
`get_patient_progression(...)` and adapts them with
`from_progression_result(...)`.

**Implemented.** Each displayed evidence row preserves:

- patient-scoped request;
- stable exercise ID;
- explicit workout side or legacy `None`;
- source type;
- source ID where available;
- observation timestamp;
- session status;
- persisted repetition, score, and resistance observations.

Different resistance units remain separate text observations. No conversion or
numeric combination occurs.

## 7. Limitations

The endpoint and UI preserve limitations produced by the authoritative
advisory engine, including:

- software-validation-only status;
- insufficient history;
- missing resistance;
- cancelled-session context;
- mixed resistance units;
- mixed legacy/workout sources;
- missing scores or repetition pairs;
- side ambiguity.

An empty selected history is displayed as an insufficient/no-history review
state rather than as fabricated evidence.

## 8. Human-review boundary

**Implemented.** The review surface allows a human to inspect what the
software classified and why.

**Not implemented.** There is no approval workflow, decision persistence,
clinical authorization, override action, or automatic follow-up.

**TBD / requires external/clinical validation.** Any future use of an
advisory classification in a clinical workflow requires external validation,
review policy, authorization, audit requirements, and explicit separation
from prescription execution.

## 9. Explicit non-goals

Phase 6D does not:

- recommend resistance or repetitions;
- recommend exercise changes;
- modify workout plans;
- modify SessionEngine or Builder state;
- create prescription fields;
- add thresholds or decision rules;
- claim medical efficacy or clinical validity;
- alter scoring, perception, readiness, biomechanics, or live assessment;
- persist advisory decisions as clinical records;
- add database tables or migrations;
- add synthetic production records;
- infer legacy side;
- fabricate unfinished cancelled-session results;
- convert resistance units.

## 10. Validation results

**Observed.** Focused API, UI, advisory, and progression tests pass. The API
tests cover valid requests, unknown patients, invalid side/exercise values,
determinism, patient isolation, side isolation, legacy side-unspecified
history, and provenance. UI contract tests cover classification, evidence,
limitations, empty/error states, mixed-source/unit handling, and absence of
prescription language.

The configured database remains schema-only after testing:

- Alembic revision: `7d2c4e8a1f30`;
- application row counts: zero;
- SQLite integrity: `ok`;
- foreign-key violations: none.

## 11. Known limitations

**Observed.** The current configured database contains no progression
observations, so live human review of populated production history was not
possible from that file.

**Observed.** Browser visual automation remains subject to the existing
Chromium/Snap environment limitation. The UI contract is validated through
template and JavaScript tests.

**TBD.** The review surface does not yet provide user-authored annotations,
approval status, audit history, or clinician authorization. Those require a
separate design and persistence decision.

## 12. Future clinical-validation boundary

**Requires external/clinical validation.** Before any patient-facing or
clinical use, future work must validate:

1. interpretation of each classification;
2. evidence sufficiency and recency;
3. source comparability;
4. side-specific handling;
5. cancellation treatment;
6. resistance-unit policy;
7. reviewer responsibilities and authorization;
8. audit and override behavior;
9. prospective clinical validity.

**PASS — Phase 6D provides a read-only, provenance-preserving human review
presentation of the deterministic advisory engine without clinical
prescription or runtime integration.**
