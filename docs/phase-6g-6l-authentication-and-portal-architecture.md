# Phases 6G–6L: Authentication and Portal Architecture

## Status

This document separates work into **IMPLEMENTED**, **DEFERRED**, and
**FUTURE** boundaries. It builds on Phase 6F; it does not replace the
identity model or the progression, advisory, review, or workout services.

**Acceptance status: PASS / READY.** The legacy patient-specific route and
API bypass has been closed. Anonymous browser requests redirect to `/login`;
anonymous JSON/API requests receive `401`; authenticated but unauthorized
requests receive `403`.

## 6G — Authentication

**IMPLEMENTED:** application-controlled accounts use an email identifier and
Werkzeug's established password hashing implementation. `GET /login`,
`POST /login`, and `POST /logout` establish and clear a server-side Flask
session. Each request reloads the User and roles from the database, so disabled
users lose access even when an old session cookie exists. The login role
selector is only a UX check; it never changes persisted roles.

**DEFERRED:** account registration, password reset, MFA, email verification,
and external OIDC/OAuth providers. Authentication is isolated behind
`dashboard/services/authentication.py` so a future provider can replace the
credential verifier.

## 6H — Role-based routing

**IMPLEMENTED:** authenticated users are routed to `/patient` or
`/clinician` from server-loaded roles. The patient and clinician portal
boundaries deny unauthenticated and unauthorized access. Legacy assessment
routes remain available during migration and must not be treated as the new
identity boundary.

## 6I — Patient experience

**IMPLEMENTED:** `/patient`, `/patient/selection`, `/patient/results`, and
`/patient/progress` use the authenticated user's optional Patient relationship.
An unlinked patient account receives a safe setup state and cannot select an
arbitrary patient. Results and progress reuse `get_patient_progression`.
Patient pages do not expose advisory classifications or review metadata.

## 6J — Clinician experience

**IMPLEMENTED:** `/clinician` is the clinician portal entry point.
`/clinician/patients/<patient_id>` reuses the existing patient profile,
progression, advisory, and review presentation. Phase 6E review events remain
append-only and continue to use `reviewer_reference`.

## 6K — Fine-grained authorization

**IMPLEMENTED:** `IdentityContext` and `AuthorizationService` remain the
central policy boundary. Patient ownership requires the server-loaded
`patient_id` relationship. Clinician capabilities are prototype-wide because
organization and assignment policy are not implemented. Operators and admins
do not automatically receive clinician review access.

The intended matrix is:

| Capability | Patient | Clinician | Operator | Admin |
|---|---:|---:|---:|---:|
| Own patient data | Yes | Prototype policy | No | No |
| Other patient data | No | Prototype policy | No | No |
| Patient portal | Yes | No | No | No |
| Clinician portal | No | Yes | No | No |
| Progression | Own | Prototype policy | No | No |
| Advisory | No | Prototype policy | No | No |
| Review | No | Prototype policy | No | No |

## 6L — Organization and multi-clinic preparation

**FUTURE:** organizations, clinics, memberships, assignments, tenant
isolation, and organization-scoped policy. The current clinician policy is
not production clinic assignment and must be replaced before deployment to
multiple clinics.

## Shared clinical architecture

Patient and clinician views share the same database observations and
`dashboard/services/progression.py`. Advisory classifications remain
software-validation heuristics, not prescriptions. No perception, readiness,
biomechanics, scoring, SessionEngine, exercise definition, progression
calculation, or advisory heuristic was changed by this architecture.

## Security boundary

Authentication establishes identity, then server-side authorization determines
resource access. A role form field, URL patient ID, JSON payload, cookie, or
JavaScript state cannot create identity or ownership. CSRF tokens protect the
login and logout state-changing forms. Legacy patient selection is a
compatibility surface, not proof of patient ownership.

## Legacy Route Authorization Boundary

Patient selection is a workflow mechanism, not an identity system. The
server ignores a patient user's submitted or URL-selected patient ID and
uses the authenticated User's linked `patient_id`. Clinicians may use the
selection screen according to the current prototype-wide clinician policy.

The legacy selection, workout builder, workout start, assessment start, live
session, report, and result routes require an authenticated session. Patient
specific progression, context, advisory, and review APIs require
authenticated capability checks before looking up the requested patient.
Patients can access only their own progression and workflow; clinicians can
access prototype-authorized patient profiles and clinical APIs; operators and
admins do not inherit clinician capabilities.

State-changing routes require the server-issued CSRF token. Review
submissions derive `reviewer_reference` from the authenticated clinician
(`user:<user_id>`) rather than trusting browser input. Existing assessment
and workout runtime behavior remains unchanged; only the surrounding
authentication and authorization boundary was tightened.

## Explicit non-goals

No Google/Microsoft login, external provider, MFA, password reset, clinic
management, assignment management, tenant isolation, clinical prescription,
automatic resistance/repetition recommendation, or clinical threshold was
implemented.
