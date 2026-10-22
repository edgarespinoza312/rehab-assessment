# Revaliv — Software Validation and Release Readiness

**Status baseline:** `revaliv-current-review`  
**Purpose:** Distinguish completed software work from validations that require real hardware, representative recordings, or product/security decisions.

This is the current-state checklist for release planning. Earlier phase documents describe the scope and acceptance boundary at the time each phase was completed; later implementation work may supersede their deferred-item lists.

## Current software baseline

The review branch contains the Flask application, role-based portals, per-session runtime contexts, a shared camera-consumer guard, workout-plan/session persistence, progression-history APIs and chart, advisory classifications, append-only review events, password recovery, regression tests, and a GitHub Actions test workflow.

The default pose backend remains MediaPipe. The YOLO/TensorRT backend is opt-in and experimental. Its presence or successful initialization is not evidence of a measured performance gain or clinical accuracy.

## Completed in the software review

- Password reset uses expiring signed tokens tied to the current password hash; successful reset changes the hash and makes the reset link unusable.
- Login sessions now carry a keyed fingerprint tied to the account's current password hash. A password change invalidates previously issued session cookies when they are next presented. The browser completing the reset is explicitly logged out.
- A regression test covers invalidation of the resetting browser and a second browser session.
- The current review branch has automated CI; use the latest branch Actions result, not a result from an earlier commit, as the merge gate.

## Database migration behavior

The CI workflow now checks both an empty file-backed database upgrade and the full test suite on Python 3.10 and 3.11. The base migration bootstraps the legacy patient/assessment tables when absent. For older assessment rows that have a single `score` field, it carries that value into `average_score`; it does not infer repetitions, best score, or worst score, so those fields remain unknown. The patient profile and report display unknown values as unavailable instead of as zero or fabricated measurements.

The follow-up migration allows these historical fields to be nullable in databases that were already upgraded under the earlier schema. Its downgrade refuses to reinstate `NOT NULL` constraints while unknown values remain, rather than inventing replacement values.

## Release blockers or decisions still open

### Clinician-to-patient authorization scope

The review branch now includes a clinician-to-patient assignment workflow, persistence/migration support, and automated tests. This supersedes earlier phase notes that described assignments as entirely unimplemented. The existence of an assignment model and workflow does not, by itself, prove that every patient-specific route, API, export, history query, and mutation enforces the intended relationship.

The remaining release gate is an authorization-coverage audit: define the approved access policy (including shared patients, reassignment, unassigned patients, administrator access, and any clinic/tenant boundaries), trace every patient-specific read and write through the enforcement layer, and add cross-clinician isolation tests for each applicable route/API. Confirm that patient lists and indirect access paths follow the same policy. Do not assume the role `CLINICIAN` by itself establishes a treatment relationship, and do not claim multi-clinician production readiness until policy and route coverage are verified.

### Physical Jetson/camera acceptance test

This cannot be established by GitHub's Ubuntu CI. On the target Jetson, run the full application with the intended camera and record:
- camera initialization, stream startup, repeated capture failure, recovery/cleanup, and application shutdown;
- measured frame rate and end-to-end frame latency under a representative exercise session;
- successful assessment finish/save, workout completion/cancellation, and persistence after application restart;
- behavior under poor visibility, partial occlusion, out-of-frame joints, multiple people, and a temporary camera disconnect;
- CPU/GPU use and inference evidence if testing the experimental TensorRT path.

Use the existing performance instrumentation and pose benchmark where applicable. Change camera buffering, resolution, or backend configuration only in response to measured bottlenecks or accuracy failures.

### Movement-measurement validation

No code-only test can establish that the system's movement measurements are accurate enough for rehabilitation use. Create a small, consented, non-identifying validation set with human-annotated repetition counts and movement landmarks/angles. Include different body sizes, camera distances, lighting, clothing, exercise speeds, partial occlusion, left/right exercises, and incomplete repetitions.

Predefine metrics before reviewing the outputs: repetition-count absolute error, repetition detection precision/recall, joint-angle mean absolute error against annotation, usable-frame rate, side-identification error rate, and latency. Report sample sizes and failure cases. Keep MediaPipe and TensorRT comparisons on the same recordings. Do not tune and evaluate on the same clips without disclosure.

### Workout-history measurement granularity

The in-memory workout result contains one entry per completed repetition, including the overall score, six domain scores, and feedback. The persistence service currently reduces those entries to exercise-level aggregates (average domain scores and overall score) and concatenates repetition feedback into one JSON list. The database does not retain repetition order or the per-repetition score/domain-score association; the serialized `repetition_scores` list is also not stored. This limits later analysis of within-exercise variation and the traceability of a specific repetition's feedback.

Treat this as a known data-retention limitation, not a proven defect in the current summary UI. Before adding a schema migration, confirm the intended history/reporting use cases and data-retention policy. If repetition-level analysis is required, add ordered child records linked to `WorkoutExerciseResult`, persist the existing per-repetition fields without recomputing them, and test round-trip order, cancelled sessions, empty/partial results, migration behavior, and rollback. Preserve `None` as unavailable; do not silently coerce missing measurements to zero. Avoid storing raw video or additional identifying data unless explicitly required and approved.

### Advisory progression

Progression labels are software-validation heuristics, not clinically validated conclusions or prescriptions. Synthetic scenario tests validate deterministic software behavior only. Do not translate the classifications into exercise prescriptions, resistance changes, patient-facing clinical claims, or automated workout changes without domain-owner review and an appropriate clinical validation protocol.

### Runtime and deployment boundaries

The camera is shared physical infrastructure and the in-process runtime registry is not distributed. The implementation intentionally permits only one active consumer of the shared camera pipeline. Do not claim multi-camera concurrency, horizontal scalability, or high availability. Those require separate architecture and acceptance testing.

## Production configuration checklist

Before a production deployment:
- Set a stable, secret `REVALIV_SECRET_KEY`; do not rely on the development-generated secret.
- Set `REVALIV_ENV=production` and serve the application through HTTPS with secure cookies enabled.
- Configure `REVALIV_PUBLIC_BASE_URL` to the actual HTTPS origin.
- Configure and verify SMTP delivery, sender identity, TLS mode, and credential handling.
- Configure rate limits and abuse monitoring for login and password-reset requests; the application does not currently provide a distributed rate limiter.
- Keep all SMTP credentials and secrets out of source control and logs.
- Review database backups, retention, access logging, deployment/rollback, and operational monitoring.
- Resolve clinician-patient assignment policy and test isolation before using real patient records.

## Branch and merge hygiene

The review branch is intentionally separate from `main`. Compare the latest branch heads before integrating, inspect any main-only commit, run the full automated suite on the intended merge commit, and retain the hardware/measurement acceptance items as explicit release gates. A passing CI run means the tested software suite passed in that CI environment; it does not imply physical-device or clinical validation.

## Next recommended sequence

1. Confirm the latest branch CI result for the session-revocation and workout-persistence changes; do not substitute results from an earlier commit.
2. Audit clinician-to-patient authorization policy and enforcement across every patient-specific route/API, including cross-clinician isolation and patient-list visibility.
3. Review workout persistence for loss of repetition-level measurements; decide whether a structured repetition record is required before changing the schema, and preserve the distinction between zero and unavailable values.
4. Run physical Jetson/camera acceptance tests and preserve the measurements.
5. Conduct the annotated-recording movement validation.
6. Update historical phase documents only where their current-status statements are materially misleading; preserve their record of each phase's original boundary.
