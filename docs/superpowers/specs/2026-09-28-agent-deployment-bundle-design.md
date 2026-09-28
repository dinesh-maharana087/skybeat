# Agent Deployment Bundle Design

## Goal

Make the authenticated SkyBeat dashboard the primary safe operator workflow for
issuing a device enrollment and obtaining one immutable, offline-installable
agent release bundle, without weakening the existing OIDC, RBAC, one-time
enrollment, release-integrity, or production-transport controls.

## Scope and constraints

- The server serves only a configured, already-built agent release. It never
  builds wheels, archives source, or accepts an artifact path from a request.
- A generic release archive contains no enrollment token, device credential,
  API secret, certificate private key, or server wheel.
- The existing short-lived, digest-only `sbe1` enrollment authorization remains
  single-use and is disclosed only in the authenticated create-intent response.
  It is never recoverable from durable storage.
- OWNER and ADMIN authorization is enforced by the existing
  `ManagementUserDependency` on every artifact and enrollment-management route.
- Production agent endpoints remain HTTPS-only. A development-only private-IP
  HTTP exception requires both server configuration and an explicit installer
  flag.
- No migration is needed: `AgentEnrollment` already persists the target,
  expiry, use time, issued device, verification receipt state, and audit
  attribution required for status and revocation.

## Canonical release artifact

`scripts/build-agent-release.sh` remains the sole producer of a release. It
creates a versioned directory and a sibling immutable archive:

```text
skybeat-agent-<version>/
  install-agent.sh
  lib/skybeat_agent_install.sh
  verify-agent-release.py
  deployment/systemd/skybeat-agent.service
  skybeat_agent-<version>-*.whl
  requirements.lock
  wheelhouse/
  wheel.sha256
  SHA256SUMS
  release-manifest.json
  README.txt

skybeat-agent-<version>-linux.zip
```

The builder copies the existing hardened installer, helper, verifier, and unit
into the bundle so installation does not require a repository checkout or a
second tooling archive. It must select exactly one wheel matching
`skybeat_agent-<version>-*.whl`; zero or multiple matches fail the build. A
`skybeat_server` wheel is rejected. The release verifier validates the agent
wheel identity/version, its hash, lockfile, wheelhouse hashes, and the hashes
of the bundled installation tooling. The archive is created only after the
directory verifies and contains the exact safe directory members under one
versioned root.

The installer continues to require explicit package, wheelhouse, lockfile, and
wheel SHA-256 arguments. The dashboard supplies the real expected hash from
the validated manifest, and uses that manifest's exact wheel filename rather
than constructing a wheel tag, so an operator does not calculate or infer it.
The installer verifies that explicit hash and the complete release manifest
before modifying the target host.

## Runtime release configuration and serving

Add protected runtime configuration for:

- `SKYBEAT_AGENT_RELEASE_DIR`: absolute path to the one approved unpacked
  release directory. Its sibling archive name is derived only after strict
  manifest/version validation.
- `SKYBEAT_AGENT_SERVER_URL`: agent-facing server origin. It defaults to
  `PUBLIC_BASE_URL` only when omitted.
- `SKYBEAT_ALLOW_INSECURE_LOCAL_AGENT_SERVER`: defaults to false. It is valid
  only in `development` and only for an HTTP private/loopback IP origin.

`AgentReleaseService` owns all release inspection. It validates the configured
directory with the existing release contract, derives metadata only from the
validated manifest, and checks that the archive contains exactly the validated
release members before returning it. Invalid, missing, ambiguous, symlinked,
or tampered artifacts produce a safe unavailable response. No route accepts a
filename, directory, or arbitrary filesystem path.

Authenticated routes are:

```text
GET /api/v1/agent-releases/current
GET /api/v1/agent-releases/current/download
```

They return no secrets and use `Cache-Control: no-store`. The download is an
attachment with a fixed allowlisted archive name.

## Enrollment deployment workflow

The existing `POST /api/v1/agent-enrollments` creates the intent and exposes
its token once. The dashboard keeps that value only in JavaScript memory while
the deployment dialog is open. It offers a local Blob download named
`enrollment.token`; this is not a server retrieval endpoint, is not retained
in browser storage, is not placed in a URL, and disappears when the dialog
closes. The authenticated response is already `no-store`.

The deployment dialog combines the create-intent response with release
metadata and displays:

- device name and project;
- pending enrollment state and expiry;
- release version and agent-facing server origin;
- a release-package download;
- a sensitive token-file download with `0600` guidance;
- a copyable command referring to `./enrollment.token`, not the raw token;
- refreshable evidence-driven enrollment status; and
- revoke/reissue controls.

The generated instructions name the archive root explicitly, so an operator
does not need to infer it after extraction:

```text
unzip skybeat-agent-<version>-linux.zip
cd skybeat-agent-<version>
chmod +x ./install-agent.sh
sudo ./install-agent.sh --server <validated-origin> \
  --package ./<manifest-wheel-filename> \
  --sha256 <manifest-wheel-hash> \
  --wheelhouse ./wheelhouse \
  --lockfile ./requirements.lock \
  --token-file ./enrollment.token
```

For a configured valid local-development HTTP origin only, the command also
includes `--allow-insecure-local-server`. No token appears in the command.

Add management routes:

```text
GET    /api/v1/agent-enrollments/{enrollment_id}
DELETE /api/v1/agent-enrollments/{enrollment_id}
```

The read route returns safe target, expiry, release-independent lifecycle, and
issued-device data. It returns no token, credential, verification receipt, or
digest. The delete route is same-origin and locks the intent before expiring an
unused authorization and auditing `agent_enrollment.revoked`. It does nothing
to a device or credential after exchange; an already-used authorization cannot
be used as a credential-revocation path.

Lifecycle is derived from durable evidence:

- `PENDING`: unused authorization with `expires_at` in the future.
- `ENROLLED`: exchange completed and a device identity was issued, but no
  sufficiently recent accepted heartbeat exists.
- `ONLINE`: the issued device has a valid, sufficiently recent heartbeat under
  the existing server availability policy.
- `EXPIRED` / `REVOKED`: no longer usable authorization; the client uses the
  response-safe status without exposing reason-sensitive token details.

## Local HTTP guard

The installer continues to reject HTTP by default. It gains
`--allow-insecure-local-server`, which is meaningful only for an `http` URL
whose host is an IP address classified as loopback or private. It rejects
public, hostname-based, credential-bearing, path-bearing, and arbitrary HTTP
origins. The dashboard emits the flag only if the server configuration has
already passed the development-only validator. Production configuration rejects
both HTTP agent origins and the override setting.

## Error handling and audit

Expected authorization, validation, conflict, unavailable-release, and
already-used/revoked outcomes use safe status codes and no-store responses.
Unexpected failures do not return paths, manifest contents, tokens, or
exception details. Audit records retain canonical authenticated actor email and
safe enrollment identifiers/actions only; raw enrollment tokens, device
credentials, receipt tokens, and artifact paths never enter audit metadata or
logs.

## Test and verification requirements

Tests cover release selection/manifest/archive integrity, no server-wheel
selection, installer self-containment and transport guard, metadata/download
authorization, transient token-file behavior, lifecycle derivation, safe
revocation, existing one-time exchange semantics, dashboard controls, and
existing enrollment/auth/installer regressions. Verification includes focused
and relevant full server tests, agent tests, release/installer tests, Ruff,
format, strict mypy, Alembic-head, JavaScript syntax, and `git diff --check`.

Real browser/device acceptance remains a separate human procedure: create a
project and enrollment, download the immutable package, save the transient
token, install on the Ubuntu target with the generated command, verify systemd
and exchange, then verify the first heartbeat and telemetry in the dashboard.
