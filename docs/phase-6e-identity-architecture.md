# Phase 6E — Identity Architecture Options

## 1. Boundary

**Implemented.** Phase 6E stores a bounded `reviewer_reference` abstraction.
It does not authenticate or authorize that reference.

Patient and reviewer identities remain separate:

- **Patient:** clinical/assessment subject and existing profile entity.
- **Reviewer/User:** person operating Revaliv and future identity/account
  boundary.

The Patient model must not become an authentication account.

## 2. Option A — Trusted/local reviewer environment

### Identity assurance

**Observed limitation.** Low. A trusted environment supplies an opaque
reviewer reference, but the application does not verify who supplied it.

### Implementation complexity

**Observed.** Lowest. It requires no account system or provider integration.

### Auditability

**Observed.** The application can preserve the supplied reference, timestamps,
dispositions, notes, and append-only history. It cannot prove identity.

### Security implications

**Requires validation.** Suitable only where the surrounding environment is
trusted and access is controlled externally. Reviewer references must not be
represented as authentication.

### Patient-data implications

**Requires validation.** Weak identity assurance makes attribution of access
and review actions limited. Patient access policy remains external to this
option.

### Deployment implications

**Observed.** Simple for local Jetson or tightly controlled deployments.

### Suitability for current Revaliv stage

**Proposed.** Appropriate as the current Phase 6E test/local boundary only.

### Migration implications

**Proposed.** Later authenticated identities can map their stable account
identifier into the existing reviewer-reference field or introduce a
versioned identity mapping.

## 3. Option B — Application user accounts

### Identity assurance

**Proposed.** Authenticated application users provide stable identities under
application-controlled account policy.

### Implementation complexity

**Proposed.** Medium to high: account lifecycle, password/session security,
recovery, roles, permissions, and audit controls are required.

### Auditability

**Proposed.** Stronger attribution because reviewer references derive from
authenticated users. Role and display-name snapshots may be added to review
events if justified.

### Security implications

**Requires validation.** Revaliv would own credential and session risk unless
delegated. Authorization must protect patient data and review mutation.

### Patient-data implications

**Proposed.** Supports explicit reviewer-to-patient authorization without
equating patients and users.

### Deployment implications

**Proposed.** Adds operational requirements for account administration,
secrets, recovery, and monitoring.

### Suitability for current Revaliv stage

**TBD.** Requires a product and deployment decision; it is not implemented in
Phase 6E.

### Migration implications

**Proposed.** Existing opaque references need a controlled mapping to account
IDs. Historical events should remain immutable and retain their original
reference.

## 4. Option C — External identity provider

### Identity assurance

**Proposed.** OAuth/OIDC or equivalent provides an external identity
authority, subject to provider configuration and token validation.

### Implementation complexity

**Proposed.** High integration complexity but potentially less custom
credential handling. Provider mapping, token validation, role claims, tenant
boundaries, and outage behavior are required.

### Auditability

**Proposed.** Strong stable provider subject identifiers can improve
attribution, with application-side reviewer-role and display-name snapshots.

### Security implications

**Requires validation.** Trust configuration, claim validation, token
handling, account-linking, logout, and provider compromise must be addressed.

### Patient-data implications

**Proposed.** Can support organization-level access controls and separation of
patient data if claims and authorization mapping are designed correctly.

### Deployment implications

**Proposed.** Requires network/provider availability, configuration, callback
URLs, operational ownership, and contingency behavior.

### Suitability for current Revaliv stage

**TBD.** More appropriate for a multi-user or production deployment than the
current local validation stage.

### Migration implications

**Proposed.** Existing reviewer references need a durable mapping to provider
subjects. Provider changes require an identity migration plan; historical
review references must not be rewritten silently.

## 5. Comparison

| Dimension | Option A: Trusted/local | Option B: Application accounts | Option C: External provider |
| --- | --- | --- | --- |
| Identity assurance | Low | Medium/high | Medium/high, provider-dependent |
| Complexity | Low | Medium/high | High integration |
| Auditability | Reference only | Authenticated account | Authenticated provider subject |
| Security ownership | Deployment environment | Revaliv account system | Shared/provider plus Revaliv mapping |
| Patient-data access policy | External/manual | Application roles | Claims plus application roles |
| Current-stage fit | Highest for local validation | TBD | TBD |
| Migration effort | Baseline reference | Mapping required | Provider mapping required |

## 6. Recommendation

**Proposed.** Retain Option A as the explicit local/test boundary for Phase 6E
and do not describe it as authentication.

Before any multi-user or clinical deployment, choose between Option B and
Option C through a separate security and product architecture phase. The
choice should be driven by deployment ownership, organizational access
requirements, identity-provider availability, audit obligations, and patient
data governance.

No authentication system is implemented by this document.

## 7. Migration considerations

**TBD.** A future identity migration should:

1. preserve all existing review event IDs and timestamps;
2. preserve original opaque reviewer references;
3. map references to authenticated subjects explicitly;
4. avoid rewriting historical reviewer identity;
5. add authorization checks before exposing or mutating review history;
6. test patient isolation and audit reconstruction.

## 8. Security implications

**Requires external/clinical validation.** Review disposition is a human
interaction with software evidence, not clinical approval. Authentication,
authorization, access logging, note privacy, retention, and patient-data
governance remain future requirements.
