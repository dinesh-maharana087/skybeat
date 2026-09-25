# Stage 09 RBAC Design

## Purpose

Stage 09 adds durable application users and server-enforced `OWNER`, `ADMIN`, and
`USER` roles while retaining Google OIDC as the sole authentication mechanism.
Environment allowlists remain an authentication-admission control; they do not
grant an application role.

## Durable user model

Add an `application_users` MySQL/InnoDB table. Each record has a normalized,
unique email, optional operator-provided display name, optional bound Google
subject, constrained role, active flag, creation/update timestamps, and an
actual successful-login timestamp. The role constraint permits only `OWNER`,
`ADMIN`, and `USER`. A generated, unique owner guard ensures the database can
contain at most one `OWNER`.

The initial migration creates no user and changes no current session into a
privileged role. Existing sessions resolve a user at request time; a session
for an identity without an active durable user is rejected rather than granted
an implicit role. This is the selected least-privilege behavior.

## Identity and login

Google OIDC continues to validate the identity. After the existing allowlist
policy admits that identity, the server normalizes its email and resolves the
active durable user. On that user's first successful sign-in the server binds
the verified Google subject; later sign-ins must match the binding. The role is
read from the durable user on every authenticated request, never from a cookie
or browser payload. Existing opaque sessions remain opaque and are not trusted
as a role cache.

An account must both be allowlisted (or accepted by the configured hosted
domain) and be an active durable user to sign in. Creating a user does not
modify environment allowlists.

## Bootstrap and owner safety

`python -m app.cli owner-bootstrap --email owner@company.com` is the only
initial ownership path. It normalizes email and is idempotent for the same
Owner. It refuses a different email once an Owner exists. There is no browser,
environment-variable, allowlist, or first-login ownership claim.

Stage 09 supports exactly one Owner. Browser/API role management cannot create,
promote, demote, disable, or delete an Owner. Ownership transfer is explicitly
out of scope and requires a future reviewed procedure.

## Authorization policy

Reusable FastAPI dependencies enforce roles server-side:

| Capability | OWNER | ADMIN | USER |
| --- | --- | --- | --- |
| Dashboard/device/project/diagnostic reads | yes | yes | yes |
| Create project; enroll, move, or toggle a device | yes | yes | no |
| View Users page and list users | yes | yes | no |
| Create or manage USER | yes | yes | no |
| Create or manage ADMIN | yes | no | no |
| Modify OWNER or grant OWNER | no browser/API path | no | no |

Unauthenticated requests retain the existing 401/redirect behavior. Authenticated
but insufficient roles receive no-store 403 responses. Same-origin checks remain
required for every mutation.

## Users experience

`/dashboard/users` is available to Owner and Admin only. It lists durable
display name (or unavailable), email, role, active status, creation time, and
actual last login when recorded. Owner can create/manage Admin and User
accounts; Admin can create/manage User accounts only. The same server policy
drives role-aware UI affordances: Users do not receive actionable project or
device controls, and only permitted management controls are rendered.

Administrative creation/update actions emit existing `AuditEvent` records with
actor, affected user email, prior role/status, resulting role/status, and time.
No tokens or secrets are logged.

## Upgrade sequence

1. Apply `alembic upgrade head`.
2. Ensure the future Owner's Google identity is admitted by the existing
   allowlist/domain configuration.
3. Run `python -m app.cli owner-bootstrap --email <google-email>` locally on
   the server.
4. Restart the application if required by deployment policy, then sign in via
   Google OIDC.

No production agent change, production deployment, ownership transfer, or git
commit is part of Stage 09.
