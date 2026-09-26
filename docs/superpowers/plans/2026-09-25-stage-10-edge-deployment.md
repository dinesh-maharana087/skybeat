# Stage 10 Edge Agent Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the existing SkyBeat agent as a verified local-wheel release bundle with strict single-use enrollment, a protected configuration, and an idempotent hardened Linux installation.

**Architecture:** A durable server enrollment intent creates a single-use `sbe1` exchange token and a distinct short-lived `sbv1` verification receipt. The root installer preflights a supported Ubuntu/Python runtime, verifies an explicit wheel and lock-backed local wheelhouse, preserves existing device credentials during repair/upgrade, and installs the existing agent under systemd as a non-root account.

**Tech Stack:** FastAPI, SQLAlchemy 2/Alembic/MySQL, Pydantic, Python 3.12, Bash, systemd, pip hash checking, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-25-stage-10-edge-deployment-design.md`

## Global Constraints

- Production runtime is Ubuntu 24.04 LTS, `amd64`, systemd, Python 3.12; preflight rejects other targets before host writes.
- The explicit reviewed wheel is canonical; no Git/source-tree/PyPI install or Stage 10 download path is permitted.
- `requirements.lock` plus an explicit local wheelhouse are mandatory and installed offline with hash verification.
- Enrollment and verification secrets are server-side digests; permanent `sb1` credentials remain only in root-owned `/etc/skybeat/agent.env` mode `0600`.
- `sbe1` enrollment tokens are strictly single use; only `sbv1` receipts may poll narrow heartbeat verification before expiry.
- Preserve existing telemetry, transport, collector bounds, agent behavior, and canonical credential lifecycle; no remote control, auto-update, or self-healing.
- Do not create a commit until the user has reviewed Stage 10 implementation/acceptance results.

## Review Focus

- An exchange response lost after commit must not permit old-token retry or duplicate-device creation; explicit replacement intent is required.
- A verification receipt must never authenticate exchange, heartbeat, telemetry, dashboard, or normal device routes.
- A path that changes between preflight and installation must fail safely instead of following an unsafe symlink or arbitrary wheel.
- Same-version repair and upgrade must preserve a valid existing credential without consuming an enrollment token.
- NVIDIA access failure must be visible and truthful without installation failure or driver/group modification.

### Task 1: Durable enrollment intent and receipt primitives

**Files:**
- Create: `server/migrations/versions/<revision>_stage10_agent_enrollments.py`, `server/app/enrollment/service.py`, `server/app/enrollment/__init__.py`, `server/tests/test_enrollment.py`.
- Modify: `server/app/models/auth.py`, `server/app/models/__init__.py`.

**Interfaces:**
- Produces: `EnrollmentMode`, `AgentEnrollmentService.create_intent(...)`, `exchange(...)`, and `verify_receipt(...)` for API consumers.

- [ ] Write failing service tests for normalized opaque token parsing, Owner/Admin creation metadata, expiry, single-use exchange, replay rejection, receipt expiry, and receipt-only heartbeat status.
- [ ] Run the new tests and confirm the missing service/model failure.
- [ ] Add the additive MySQL migration/table with token/receipt digests, public IDs, expiry/use timestamps, one `NEW` or `REPLACE` target, and constrained mode/state values.
- [ ] Implement token generation/digesting, row-locked intent/receipt lifecycle, and safe audit events without raw secret values.
- [ ] Run focused enrollment tests, Ruff, and mypy.

### Task 2: Canonical enrollment exchange and server authorization

**Files:**
- Create: `server/app/api/enrollment.py`, `server/app/schemas/enrollment.py`, `server/tests/test_enrollment_api.py`.
- Modify: `server/app/devices/service.py`, `server/app/main.py`, `server/app/api/dashboard.py`.

**Interfaces:**
- Consumes: Task 1 `AgentEnrollmentService` methods and existing `IdentityService` enrollment/rotation primitives.
- Produces: same-origin Owner/Admin issuance endpoints, anonymous bounded exchange, and receipt-only verification endpoint.

- [ ] Write failing API matrix tests for Owner/Admin/User/anonymous issuance, expired/replayed/consumed exchange, receipt isolation, and direct forged requests.
- [ ] Run the tests and confirm routes are absent.
- [ ] Refactor only the necessary canonical identity operations for one enclosing enrollment transaction; preserve existing CLI/dashboard behavior and audit semantics.
- [ ] Add strict Pydantic schemas, response projections, generic safe token errors, rate bounds, no-store headers, and reusable RBAC dependencies.
- [ ] Run focused API/service tests and inspect that no raw token/credential appears in errors or audit records.

### Task 3: Dashboard enrollment-intent operator flow

**Files:**
- Modify: `server/app/templates/dashboard.html`, `server/app/static/dashboard.js`, `server/app/static/dashboard-shell.css`, `server/tests/test_dashboard_page.py`, `server/tests/test_dashboard_api.py`.

**Interfaces:**
- Consumes: Task 2 create-intent endpoint and one-time safe response projection.
- Produces: Owner/Admin Devices-page intent creation and explicit one-time token copy/clear UI.

- [ ] Write failing page/API tests for ADMIN/OWNER visibility, USER absence/403, no token in markup/storage/URLs, and token clear-on-dismiss behavior.
- [ ] Run tests and confirm the UI identifiers/flow are absent.
- [ ] Implement a minimal Devices-page enrollment-token dialog that gathers the server-supported new-device or bound-device replacement intent fields and displays the returned token once.
- [ ] Run dashboard tests and JavaScript syntax/runtime regressions.

### Task 4: Versioned wheel and local release-bundle tooling

**Files:**
- Create: `scripts/build-agent-release.sh`, `scripts/verify-agent-release.py`, `server/tests/test_agent_release_artifacts.py`.
- Modify: `agent/pyproject.toml`, `agent/src/skybeat_agent/main.py`, `agent/tests/test_config.py`, `docs/DEPLOYMENT.md`.

**Interfaces:**
- Produces: `skybeat-agent --version`, a wheel whose version matches packaging metadata, `requirements.lock`, and a locally verifiable wheelhouse release bundle.

- [ ] Write failing artifact tests for explicit wheel metadata/version, release manifest/VERSION-safe fields, lockfile completeness, and no credential-like values in release files.
- [ ] Run tests and confirm the builder/verifier is absent.
- [ ] Add version output without altering runtime collection/sending, then implement release-bundle build/verification commands that use only pinned locked dependencies.
- [ ] Run artifact, agent, and static security tests; inspect generated release fixtures for secret absence.

### Task 5: Installer preflight and immutable package installation

**Files:**
- Modify: `scripts/install-agent.sh`, `deployment/systemd/skybeat-agent.service`, `deployment/systemd/agent.env.example`, `server/tests/test_deployment_artifacts.py`.
- Create: `scripts/lib/skybeat_agent_install.sh`, `server/tests/test_agent_installer.py`.

**Interfaces:**
- Consumes: Task 4 explicit wheel/wheelhouse/lock contract.
- Produces: `preflight`, `verify_package`, `install_package`, and `install_service` shell functions with safe terminal outcomes.

- [ ] Write failing mocked-shell/Python tests for unsupported platform/runtime, unsafe path/symlink, invalid wheel/lock/wheelhouse, HTTP URL, checksum mismatch-before-install, and secret-free command/output construction.
- [ ] Run tests and confirm the existing source installer cannot satisfy them.
- [ ] Replace source-tree installation with explicit option parsing, bounded preflight, SHA-256 verification, offline hash-locked venv installation, root-owned paths, VERSION recording, and secure `skybeat` account creation.
- [ ] Update the systemd unit with compatible non-root hardening and bounded restart limits without hiding NVIDIA devices.
- [ ] Run installer/security/unit regressions and inspect the generated command paths manually.

### Task 6: Secure exchange, verification, and idempotent lifecycle

**Files:**
- Modify: `scripts/install-agent.sh`, `scripts/lib/skybeat_agent_install.sh`, `server/tests/test_agent_installer.py`, `server/tests/test_enrollment_api.py`, `docs/DEPLOYMENT.md`.

**Interfaces:**
- Consumes: Task 2 exchange/verification APIs and Task 5 install state functions.
- Produces: atomic root-only config writes; `INSTALLED`, `ALREADY_CURRENT`, `REPAIRED`, `UPGRADED`, and `FAILED` results; explicit `--re-enroll` behavior.

- [ ] Write failing tests for root-only temporary exchange files, no secret stdout/stderr/unit/VERSION/process argument, no ordinary re-enrollment, explicit bound-device replacement, uncertain-response no-retry, and bounded heartbeat-receipt polling.
- [ ] Run tests and confirm secure exchange/lifecycle functions are absent.
- [ ] Implement curl config/temp-file handling with CA validation, atomic configuration replacement, post-start receipt polling, same-version repair, upgrade preservation, explicit re-enrollment, and safe partial-failure reporting.
- [ ] Run focused enrollment/installer tests plus agent transport/config regression tests.

### Task 7: Runbook, full verification, and acceptance checkpoint

**Files:**
- Modify: `docs/DEPLOYMENT.md`, `docs/API_SPEC.md`, `docs/SECURITY.md`, `docs/IMPLEMENTATION_STATUS.md`.
- Test: server, agent, installer/artifact, migration, lint, formatting, type checks, and isolated Ubuntu acceptance where available.

**Interfaces:**
- Consumes: all prior task contracts.
- Produces: operator-safe fresh install/repair/upgrade/re-enrollment/uninstall/troubleshooting/security runbook and factual acceptance status.

- [ ] Write documentation/source tests for the required release command, `/etc/skybeat/agent.env` permission model, `--token-file` recommendation, systemd/journal commands, outbound HTTPS, and no source/PyPI deployment path.
- [ ] Run tests and confirm missing Stage 10 documentation contracts.
- [ ] Document the exact release-bundle build, operator lifecycle, security model, supported platform, GPU diagnosis, and known recovery limits.
- [ ] Run complete available server/agent suites, Ruff/format/mypy, Alembic graph/migration checks, secret scans, and a real Ubuntu acceptance only if safe infrastructure is available.
- [ ] Update the implementation checkpoint with actual results and stop before Stage 11/final commit.

## Execution Notes

Tasks 1–2 share the enrollment interfaces; Task 3 consumes the issuance endpoint; Task 4 defines the wheel contract consumed by Tasks 5–6; Task 6 consumes both server receipt and installer contracts. If an enrollment exchange cannot retain canonical identity operations in one transaction without conflict, the implementation must stop and record the smallest safe redesign rather than issue a credential outside the consumed-token transaction.

No task commits until the user has reviewed Stage 10 implementation and acceptance results; use status checkpoints and targeted verification evidence instead.
