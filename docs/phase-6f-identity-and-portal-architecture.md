# Phase 6F — Identity, Patient/Clinician Domain, and Portal Architecture

## 1. Product vision

**Proposed future boundary.**

```text
/ → Login → Authenticated User → Role-based routing
                         ├── PATIENT → Patient Home
                         └── CLINICIAN → Clinician Portal
```

Phase 6F establishes the internal domain and authorization boundaries needed
for that future flow. The current patient-selection-first workflow remains
functional:

```text
Current: Patient Selection → Assessment
Future:  Login → Role → Patient/Clinician Experience
```

## 2. User model

**Implemented.** `User` is a minimal application identity with:

- `user_id`;
- `display_name`;
- `status` (`ACTIVE` or `DISABLED`);
- optional `patient_id`;
- timestamps.

It intentionally has no password, token, OAuth identifier, login session, or
authentication fields.

## 3. Patient model

**Existing.** `Patient` remains the rehabilitation/assessment subject and
existing clinical profile entity. It is not an account and was not replaced or
retrofitted with authentication behavior.

## 4. Clinician model

**Implemented boundary.** A clinician is a `User` with the `CLINICIAN` role.
There is no separate Clinician table.

**Not implemented.** Organizations, clinics, tenants, assignments, and
multi-tenant membership remain future work.

## 5. Role model

**Implemented.** Roles are normalized through:

```text
users
roles
user_roles
```

The initial roles are:

```text
PATIENT
CLINICIAN
ADMIN
OPERATOR
```

Users may have multiple roles. `ADMIN` has no broad capabilities yet.
`OPERATOR` does not automatically gain clinician review authority.

Role names do not establish identity or clinical authority.

## 6. Patient-user relationship

**Implemented.** `users.patient_id` is an optional, unique foreign key to
`patients.patient_id`.

This supports:

- a Patient without a User;
- a User without a Patient;
- at most one linked User per Patient in the current minimal model;
- a future patient-facing user accessing only the linked patient profile.

This relationship does not imply authentication. It is a domain relationship
available to a future authenticated identity adapter.

## 7. IdentityContext

**Implemented.** `dashboard/services/identity.py` defines immutable
`IdentityContext` with:

- user ID;
- roles;
- trust state;
- optional patient ID;
- user status.

Available constructors include:

- `anonymous_identity()`;
- `trusted_development_identity(...)`;
- `identity_from_user(...)`.

The trusted development constructor is a server/domain test mechanism. It is
not populated from arbitrary browser JSON, URL parameters, or a claimed role.

## 8. Authorization boundary

**Implemented.** `AuthorizationService` centralizes capability checks:

```text
IdentityContext → AuthorizationService.can(...) → resource access decision
```

Capabilities include:

- `VIEW_OWN_PATIENT_DATA`;
- `START_OWN_ASSESSMENT`;
- `VIEW_ASSIGNED_PATIENT`;
- `VIEW_PATIENT_PROGRESSION`;
- `VIEW_ADVISORY`;
- `REVIEW_ADVISORY`.

Patient capabilities require the identity's linked patient ID to match the
requested patient. Clinician capabilities require the `CLINICIAN` role and a
target patient. Assignment and organization policy are intentionally deferred;
the current trusted prototype treats the clinician role as the explicit
capability boundary.

Disabled and anonymous identities are denied protected operations.

The current patient-selection routes do not yet invoke this future identity
boundary because authentication is not implemented. A patient ID in a URL is
not authorization.

## 9. Patient experience

**Future proposed architecture.**

```text
Patient Home
├── Start Exercise
└── My Progress / My Results
```

Patient-facing progression should reuse the existing progression service and
visualization architecture and should expose only the linked patient's own
results, repetitions, completion, scores, resistance observations, and
session history.

The patient view must not expose clinician-only advisory classifications,
evidence, review history, reviewer references, or reviewer notes.

No new patient-facing routes or UI redesign were added in Phase 6F.

## 10. Clinician experience

**Future proposed architecture.**

```text
Clinician Portal
└── Patients
    └── Patient Profile
        ├── Overview
        ├── Progression
        ├── Advisory
        └── Human Review
```

The existing patient profile remains the foundation for the future clinician
experience. It continues to consume the canonical progression service and
Phase 6D/6E advisory-review surfaces.

## 11. Existing patient portal reuse

**Existing.** Progression extraction, context, advisory, and review remain
shared service/domain layers. No competing patient or clinician progression
model was introduced.

The future distinction is presentation and authorization, not duplicated
historical truth.

## 12. Existing patient-selection compatibility

**Existing.** The patient-selection-first flow remains in place and was not
removed or redirected to a login page.

The selection page may later serve as a clinician-portal patient list, but
that routing and authorization integration belong to a future phase.

## 13. Patient progression architecture

**Existing.** The canonical chain remains:

```text
Progression extraction
  → progression API/UI
  → context
  → advisory engine
  → human review
```

Patient and clinician views must consume the same progression source. Phase 6F
does not duplicate calculations or alter progression semantics.

## 14. Clinician-only advisory/review data

**Existing boundary.** Advisory classifications, evidence explanations,
limitations, review events, reviewer references, and review notes remain
reviewer-facing data.

They are not automatically exposed to a patient identity. A future
patient-facing interpretation layer would require separate product and
clinical validation.

## 15. Security limitations

Phase 6F does **not** provide authentication.

- Trusted development identity is not production authentication.
- A role is not proof of identity.
- Patient selection is not authorization.
- A patient ID in a URL is not proof that the requester owns that patient.
- No browser-controlled role or identity input is trusted.

The eventual secure flow is:

```text
Authentication → Identity → Authorization → Resource access
```

not:

```text
URL patient_id → assume access
```

## 16. Explicit non-goals

Phase 6F does not implement:

- login or authentication;
- passwords or password hashes;
- authentication sessions;
- OAuth/OIDC;
- RBAC middleware;
- organizations, clinics, tenants, or memberships;
- patient credentials;
- clinical prescription;
- workout runtime changes;
- changes to scoring, perception, readiness, biomechanics, or advisory
  heuristics.

## 17. Phase 6G authentication boundary

**Future boundary.** Phase 6G may provide authentication and inject an
`IdentityContext` from a verified identity provider. It should then call the
central authorization service before patient, advisory, or review access.

Phase 6G must not infer identity from Patient records or URL parameters and
must not merge Patient and User concepts.

## 18. Future patient account model

**Proposed.** A future authenticated patient User may link to one Patient
profile through the existing optional relationship. Existing Patients without
accounts must remain valid.

The account lifecycle, recovery, consent, and patient-data access policy
require a later security/product phase.

## 19. Future organization/multi-tenancy boundary

**TBD.** Organization, clinic, tenant, clinician assignment, and patient
authorization scope are intentionally absent. They must be designed before
multi-clinic deployment and must not be inferred from the current
`CLINICIAN` role.

**PASS — Phase 6F establishes the internal identity, role, authorization, and
portal architecture. It does not implement authentication.**
