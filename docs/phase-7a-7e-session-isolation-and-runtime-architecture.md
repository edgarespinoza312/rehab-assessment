# Phases 7A–7E: Session Isolation and Runtime Architecture

## Status

**Implemented:** controlled provisioning service, authenticated patient/clinician
workflow boundaries, and per-application-session runtime contexts.

**Deferred:** distributed runtime storage, multi-camera support, organizations,
assignments, MFA, OIDC/OAuth, and public registration.

## 7A — Account provisioning

`dashboard/services/user_provisioning.py` provides server-side
`create_user`, `disable_user`, `assign_role`, `link_patient`, and
`unlink_patient` operations. There is no public registration endpoint. Passwords
are hashed through the authentication service, roles are resolved from the
server-side role table, and a patient can have at most one linked user.

## 7B/7C — Patient and clinician workflows

Patient identity remains derived from the authenticated User → Patient
relationship. Patient results and progression use the existing canonical
services. Clinicians retain prototype-wide patient-record access and can
navigate persisted profile, progression, advisory, and review data. Clinicians
do not acquire control of a patient's active runtime.

## 7D — Runtime ownership and lifecycle

`dashboard/runtime_context.py` stores mutable assessment/workout state in a
`RuntimeContext` keyed by a server-generated runtime ID held in the Flask
session. The context records `user_id`, optional `patient_id`, mode, lifecycle,
per-runtime perception/calibration state, biomechanics, exercise state,
assessment state, repetition history, workout adapter, and pose-display
continuity.

Lifecycle transitions are server-controlled:
`CREATED → ACTIVE → COMPLETING → COMPLETED`, with `ACTIVE → CANCELLED` or
`ACTIVE → EXPIRED` also permitted. Terminal contexts may be replaced by a new
runtime for a later activity.

The module-level assessment/workout engines are no longer used by production
request routes. They are retained only as a compatibility surface for the
established test suite.

## 7E — Concurrent runtime and camera boundary

Runtime state is isolated by authenticated Flask application session and the
registry verifies the owning user before returning a context. A guessed
runtime ID, patient ID, or persisted session identifier does not grant access.
Logout clears the Flask session; disabled users are rejected when identity is
reloaded.

The physical camera remains shared process infrastructure. `VideoConsumerGuard`
intentionally permits one active camera consumer, so this implementation does
not claim simultaneous multi-camera capture or horizontal scalability. When
the camera lease is available, downstream mutable processing is performed by
the requesting runtime context rather than a process-global patient runtime.

## Runtime state classification

| State | Scope |
| --- | --- |
| exercise registry, immutable profiles | shared configuration |
| camera capture and diagnostics | shared hardware/infrastructure |
| performance counters | shared diagnostics |
| perception calibration/readiness | runtime |
| biomechanics/analyzer temporal state | runtime |
| exercise phase and repetition state | runtime |
| workout lifecycle and results | runtime |
| persisted sessions and assessment records | database/domain |

## Persistence and security

Completed and cancelled workout persistence remains authoritative in the
existing persistence service. Patient ownership is still enforced by the
central authorization service. Runtime ownership is separate from clinician
read access to historical records, preventing a clinician request from
mutating a patient's active runtime.

## Future distributed architecture

If true horizontal scaling is required, move runtime contexts to a dedicated
runtime worker or broker-backed store such as Redis, route camera frames through
a session-aware worker, and make video delivery session-aware. This is future
work, not a claim made by the current in-process registry.

## Explicit non-goals

No clinical scoring, readiness, calibration, biomechanics, perception,
progression, advisory, review semantics, or progression graph behavior was
redesigned. No organizations, tenant isolation, patient assignments, public
registration, password-reset email, MFA, distributed infrastructure, or
multi-camera hardware support was added.
