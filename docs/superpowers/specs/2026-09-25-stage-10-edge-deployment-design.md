# Stage 10 — Production Edge Agent Deployment Design

## Goal

Make the existing SkyBeat agent repeatably deployable to supported production
Linux edge systems without changing telemetry, collector, heartbeat, or remote
control behavior. The deliverable is a reviewed local release bundle, secure
one-time enrollment, and an idempotent hardened systemd installation.

## Scope and non-goals

Stage 10 adds only packaging, secure enrollment, installation, verification,
and operator documentation. It does not add telemetry, remote commands,
self-healing, automatic updates, a remote artifact repository, certificate
bypass, or a source-tree/Git/PyPI production installation path.

The supported initial runtime is Ubuntu 24.04 LTS on `amd64`, systemd, and
Python 3.12. The installer rejects unsupported systems before modifying the
host. NVIDIA hardware is optional: missing tooling or access is diagnosed, not
repaired or hidden, and the existing agent's truthful GPU semantics remain
authoritative.

## Release bundle and package installation

A reviewed release is supplied locally, not downloaded:

```text
/srv/skybeat/releases/skybeat-agent-1.0.0/
├── skybeat_agent-1.0.0-py3-none-any.whl
├── requirements.lock
└── wheelhouse/
```

The explicitly supplied agent wheel is the canonical application artifact. The
installer requires its path, an explicit 64-hex SHA-256 value, the lockfile,
and the local wheelhouse. It verifies the checksum before creating/changing the
virtual environment, installs dependencies with `--no-index --require-hashes`
from the wheelhouse, then installs the wheel using `--no-index --no-deps`.
It does not discover wheels, accept source trees, or contact PyPI.

The release-builder verifies that every production dependency named by the
locked requirements file is available in the wheelhouse before publishing a
release bundle. A future artifact repository may supply the same immutable
bundle to the acquisition boundary only; verification, installation,
configuration, enrollment, and systemd behavior do not change.

## Host layout and service account

```text
/opt/skybeat/
├── venv/
└── VERSION

/etc/skybeat/
└── agent.env              # root:root, 0600

/var/lib/skybeat/
```

`VERSION` records only package name, normalized package version, verified wheel
SHA-256, and install time. It contains no credential, enrollment token, or
verification receipt. The `skybeat` system user/group owns only necessary
runtime state. `/opt/skybeat` and `/etc/skybeat` stay root-administered.

The systemd service runs as `skybeat`, reads its root-only `EnvironmentFile`
before executing the process, restarts with bounded backoff/crash-loop limits,
and applies compatible hardening (`NoNewPrivileges`, private temporary space,
protected home/system paths, no capabilities, restrictive umask, and limited
address families). It must not use `PrivateDevices` or arbitrary NVIDIA group
changes. GPU access is inspected and reported only.

## Enrollment and verification receipt

### Durable enrollment intent

The migration creates a durable `agent_enrollments` record containing an opaque
public ID; digests, never raw values, for the enrollment and verification
secrets; expiry/use timestamps; creator/audit attribution; and exactly one
target intent:

- `NEW`: a server-controlled project, device name, and GPU policy;
- `REPLACE`: one existing bound device whose credential may be rotated.

An Owner or Admin creates an intent through a same-origin dashboard API. The
token is returned exactly once as `sbe1.<intent-id>.<secret>`, is short lived,
and is not an agent credential. USER and unauthenticated callers cannot create
intents. Creating an intent does not create a device.

### Exchange

`POST /api/v1/agent-enrollments/exchange` accepts the enrollment token only in
the Authorization header over HTTPS. Under a row lock, it rejects missing,
expired, replayed, consumed, or mismatched tokens. A `NEW` intent invokes the
existing canonical enrollment path; a `REPLACE` intent invokes canonical
credential rotation for its bound device. The transaction marks the intent
consumed, emits an audit event, creates a short-lived verification receipt, and
returns once:

```json
{
  "device_id": "<uuid>",
  "credential": "sb1.<credential-id>.<secret>",
  "verification_token": "sbv1.<intent-id>.<secret>"
}
```

The consumed `sbe1` token is permanently unusable for every endpoint,
including status checks. An uncertain response is deliberately not retried:
the operator creates an explicit replacement intent. This prevents token reuse,
credential recovery through an old token, and accidental duplicate devices.

### Verification

`GET /api/v1/agent-enrollments/verification` accepts only the `sbv1` receipt
in the Authorization header. It has a short server-configured expiry, is stored
as a digest, and returns only whether the bound device has an accepted
post-exchange heartbeat. It cannot exchange, re-enroll, access telemetry or
device details, or authenticate any normal agent/dashboard endpoint.

The installer polls this bounded endpoint after starting the service. A fresh
accepted heartbeat is the server-authoritative state used by the dashboard;
the installer reports that fact rather than claiming to have opened a browser.

## Installer contract

The root-only installer accepts explicit `--server`, `--package`, `--sha256`,
`--wheelhouse`, `--lockfile`, and one of `--token` or `--token-file`.
`--token-file` is documented as the production default. `--token` is retained
for operator convenience with a clear warning about shell history and
privileged process inspection. The permanent `sb1` credential is never accepted
or passed through a command argument.

Before host modification, bounded preflight validates Ubuntu release, `amd64`,
systemd, Python 3.12, disk space, root-owned/non-symlink installation paths,
required tools, HTTPS URL, regular explicit wheel, lockfile/wheelhouse,
checksum syntax/match, and GPU availability/access diagnostics. Shell handling
uses arrays/quoted values, no `eval`, restrictive temporary files, cleanup
traps, and no shell tracing around secrets. Curl retains CA validation and uses
a root-only temporary config rather than exposing authorization headers to a
child command line.

The state machine is explicit:

| Condition | Result | Enrollment |
| --- | --- | --- |
| No valid installation/configuration | `INSTALLED` | exchange once |
| Same verified version and healthy service | `ALREADY_CURRENT` | none |
| Same version with invalid venv/unit/permissions/service | `REPAIRED` | none |
| Different verified version | `UPGRADED` | none |
| Explicit `--re-enroll` with bound replacement intent | `REPAIRED` | rotate bound credential |
| Any failed guard/action | `FAILED` | no automatic retry after uncertain exchange |

The credential response is parsed from a root-only temporary file and written
atomically to `/etc/skybeat/agent.env` as `root:root` mode `0600`. The unit is
installed root-owned, enabled, started, then verified through the narrow receipt
endpoint. Normal installer output, journald, systemd status, unit content,
VERSION, process construction, and exception messages must exclude all secrets.

## Operator lifecycle

Supported actions are fresh install, status/log review, service restart,
same-version repair, verified upgrade, explicit bound-device re-enrollment, and
careful uninstall. Uninstall stops/disables/removes only SkyBeat's unit and
application files after explicit confirmation; it never deletes unrelated host
data or creates a credential-recovery path.

## Test and acceptance strategy

Automated tests cover the full Owner/Admin/User/anonymous issuance matrix;
expired/replayed/consumed tokens; receipt scope/expiry; bounded exchange and
same-device replacement; secrets in output/error/unit/process/VERSION paths;
wheel/lock/wheelhouse/preflight validation; checksum-before-install; secure
filesystem behavior; service hardening; and install/repair/upgrade/re-enroll
state transitions.

Real acceptance requires a supported Ubuntu 24.04 `amd64` machine: release
bundle copy, preflight, installation, exchange, fresh heartbeat receipt,
dashboard ONLINE state, restart, reboot, temporary server outage/recovery, and
idempotent reinstall. NVIDIA telemetry acceptance is separately recorded when
compatible hardware is available. No unavailable hardware/infrastructure is
represented as verified.
