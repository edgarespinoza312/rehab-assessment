# Phase 7F — Authentication UX and Account Creation

## Status

**Implemented:** polished login and registration screens, patient
self-registration, and administrator-only account management.

**Unchanged:** authentication sessions, password hashing, CSRF protection,
server-side role loading, patient ownership, runtime isolation, and clinical
pipeline behavior.

## Login

`/login` no longer presents a role selector. The submitted identity is loaded
from the server-side User record, and `role_landing` continues to determine the
destination from persisted roles. The handler retains generic credential
failure behavior and disabled-user rejection. A legacy submitted role, if
present from an older client, can only cause rejection; it cannot grant
authorization.

## Patient registration

`GET /register` and `POST /register` provide public patient account creation.
The route accepts display name, email, password, and confirmation only. It
always calls `create_patient_account`, which creates a Patient record, calls
the authoritative provisioning service for a PATIENT User, and establishes the
User → Patient relationship server-side. The browser cannot submit a patient
ID or role.

Successful registration logs the new user in only after both records and the
linkage are committed, then redirects to `/patient`.

## Administrator account management

`/admin/accounts` is protected by the centralized `MANAGE_ACCOUNTS` capability,
which is granted only to ADMIN identities. It supports controlled creation of
PATIENT, CLINICIAN, and ADMIN accounts, optional linkage to an existing unlinked
patient, account listing, and disabling accounts. OPERATOR remains a schema role
for compatibility but is not offered for new accounts until its workspace and
capabilities are specified.

The route delegates creation and disabling to
`dashboard/services/user_provisioning.py`; it does not implement a second
identity or authorization system. Clinicians and patients cannot access the
surface.

## Security and non-goals

Registration and account management require CSRF tokens. Passwords remain
hashed. Roles and patient ownership are server-controlled. Public users cannot
create privileged accounts. Organizations, assignments, OIDC/OAuth, MFA,
password-reset email, email verification, and schema changes remain deferred.
