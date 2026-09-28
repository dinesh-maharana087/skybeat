# Agent Deployment Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver an Owner/Admin dashboard workflow that issues a one-time enrollment and a verified, self-contained immutable agent deployment bundle.

**Architecture:** The existing release builder produces a complete signed-by-contract directory and archive; the server validates and allowlists only a configured prebuilt release. The dashboard combines that metadata with the existing transient enrollment token, while status and revocation reuse the durable `AgentEnrollment` model and preserve device-credential boundaries.

**Tech Stack:** FastAPI, Pydantic Settings, SQLAlchemy/MySQL, Jinja2, browser JavaScript, Python `zipfile`, Bash, existing release manifest verifier.

**Spec:** `docs/superpowers/specs/2026-09-28-agent-deployment-bundle-design.md`

## Global Constraints

- Do not dynamically build wheels, package source, or accept artifact paths from HTTP requests.
- Never place enrollment tokens, credentials, API secrets, or server wheels in generic release artifacts, URLs, logs, browser storage, or audit metadata.
- Retain `ManagementUserDependency` on every Owner/Admin deployment, artifact, and enrollment-management route.
- Production uses HTTPS only; HTTP requires development configuration, private/loopback IP origin validation, and installer `--allow-insecure-local-server`.
- Use the exact validated manifest wheel filename and hash in instructions; do not construct wheel tags.
- Do not add a migration or alter device/credential revocation semantics.
- Do not commit unless the user expressly asks for it.

## Review Focus

- Archive member/path or symlink tricks must not let the server serve an unvalidated artifact.
- A valid-looking server wheel or ambiguous agent wheel must never become the package input.
- An HTTP URL that is public, hostname-based, or lacks either opt-in must fail before token exchange.
- A used enrollment intent must not be revocable into a credential/device operation.
- Browser rendering and error paths must never retain or disclose a token after the deployment dialog closes.

---

### Task 1: Self-contained release contract

**Files:**
- Modify: `scripts/build-agent-release.sh`, `scripts/install-agent.sh`, `scripts/lib/skybeat_agent_install.sh`, `scripts/verify-agent-release.py`
- Modify: `server/tests/test_agent_release_artifacts.py`, `server/tests/test_agent_installer.py`

**Interfaces:**
- Produces: a validated `skybeat-agent-<version>/` directory and sibling `skybeat-agent-<version>-linux.zip`; an installer whose bundled relative paths resolve without a repository checkout.

- [ ] **Step 1: Write failing release-builder/verifier tests**
  Assert exactly one canonical `skybeat_agent` wheel is selected; bundled installer/helper/verifier/unit and `SHA256SUMS` are required and hashed; server wheels, ambiguous/missing wheels, tampered tooling, and unsafe archive entries fail.
- [ ] **Step 2: Run focused release tests and confirm expected failures**
  Run: `pytest server/tests/test_agent_release_artifacts.py server/tests/test_agent_installer.py -q`
- [ ] **Step 3: Extend builder and verifier minimally**
  Copy required non-secret tooling into the release directory, extend the manifest/verification contract to integrity-check them, create the deterministic archive only after validation, and derive bundle-local installer paths.
- [ ] **Step 4: Add installer local-HTTP guard tests, then implement it**
  Test default HTTP rejection; accept only explicit private/loopback IP HTTP with `--allow-insecure-local-server`; retain HTTPS behavior. Implement the bounded parser/validator without accepting public or hostname HTTP origins.
- [ ] **Step 5: Run focused release/installer tests**
  Run: `pytest server/tests/test_agent_release_artifacts.py server/tests/test_agent_installer.py -q`

### Task 2: Validated release configuration and read service

**Files:**
- Create: `server/app/releases/service.py`, `server/app/releases/__init__.py`
- Modify: `server/app/config.py`, `server/app/main.py`
- Create/Modify: `server/tests/test_agent_release_service.py`, `server/tests/test_config.py`

**Interfaces:**
- Produces: `AgentReleaseService.current() -> ReleaseMetadata` and `AgentReleaseService.archive() -> Path`; safe `ReleaseUnavailable` failure; validated agent-facing origin configuration.

- [ ] **Step 1: Write failing service/config tests**
  Cover configured valid metadata, exact manifest wheel filename/hash, archive membership equality, missing/tampered release failure, and production/development transport validation.
- [ ] **Step 2: Run targeted tests and confirm expected failures**
  Run: `pytest server/tests/test_agent_release_service.py server/tests/test_config.py -q`
- [ ] **Step 3: Implement release service and configuration**
  Validate only the configured absolute directory and its sibling archive; derive safe metadata from the manifest; reject missing/tampered/symlinked/ambiguous artifacts; permit HTTP only under both configuration guards.
- [ ] **Step 4: Run targeted release/config tests**
  Run: `pytest server/tests/test_agent_release_service.py server/tests/test_config.py -q`

### Task 3: Protected deployment metadata, archive, status, and revocation API

**Files:**
- Create: `server/app/api/releases.py`
- Modify: `server/app/api/enrollment.py`, `server/app/enrollment/service.py`, `server/app/main.py`
- Modify: `server/tests/test_dashboard_api.py`, `server/tests/test_enrollment.py`, `server/tests/test_dashboard_mysql.py`

**Interfaces:**
- Produces: Owner/Admin-only current-release metadata/download routes and safe enrollment `GET`/same-origin `DELETE` routes.

- [ ] **Step 1: Write failing API/service tests**
  Assert Owner/Admin metadata/download access, USER/unauthenticated denial, fixed attachment/no-store headers, safe unavailable artifact response, pending/enrolled/online derivation, and unused-only audit-backed revocation.
- [ ] **Step 2: Run targeted API/enrollment tests and confirm expected failures**
  Run: `pytest server/tests/test_dashboard_api.py server/tests/test_enrollment.py server/tests/test_dashboard_mysql.py -q`
- [ ] **Step 3: Implement routes and lifecycle service methods**
  Reuse `ManagementUserDependency`, lock enrollment rows for revocation, preserve exchange semantics, and return only safe status/projection data. Register routes in the app factory.
- [ ] **Step 4: Run targeted API/enrollment tests**
  Run: `pytest server/tests/test_dashboard_api.py server/tests/test_enrollment.py server/tests/test_dashboard_mysql.py -q`

### Task 4: Dashboard deployment experience

**Files:**
- Modify: `server/app/templates/dashboard.html`, `server/app/static/dashboard.js`, relevant dashboard CSS
- Modify: `server/tests/test_dashboard_page.py`

**Interfaces:**
- Consumes: current release metadata, current enrollment response, enrollment status/revoke APIs.
- Produces: no-secret generic package download, local token-file Blob, exact archive-root-aware command/instructions, and safe lifecycle UI.

- [ ] **Step 1: Write failing dashboard source/runtime tests**
  Assert exact manifest filename and SHA use, archive-root `cd`, `chmod +x`, token-file rather than raw-token command, token cleanup, protected download wiring, and safe state/error presentation.
- [ ] **Step 2: Run dashboard tests and confirm expected failures**
  Run: `pytest server/tests/test_dashboard_page.py -q`
- [ ] **Step 3: Implement the deployment dialog changes**
  Fetch protected metadata, combine it with the in-memory token only after issuance, create the local sensitive token file, and clear it when closed/revoked. Do not add browser storage or token URLs.
- [ ] **Step 4: Run dashboard tests and JavaScript syntax validation**
  Run: `pytest server/tests/test_dashboard_page.py -q`
  Run: `node --check server/app/static/dashboard.js`

### Task 5: Documentation, release fixture, and full verification

**Files:**
- Modify: `.env.example`, `docs/DEPLOYMENT.md`, `docs/API_SPEC.md`, `docs/SECURITY.md`, `docs/IMPLEMENTATION_STATUS.md`
- Modify/Regenerate only when verified: `release-final/skybeat-agent-1.0.0/` and its sibling archive

**Interfaces:**
- Consumes: final release/API/dashboard behavior.
- Produces: exact secure operator workflow and documented local-only HTTP exception.

- [ ] **Step 1: Write/update documentation and artifact contract tests**
  Pin supported configuration, no-secret bundle expectations, extraction/root/permission instructions, token-file handling, and real acceptance limits.
- [ ] **Step 2: Regenerate and validate the checked-in release fixture only through the builder**
  Verify the bundle before including it; do not hand-edit wheel, manifest, hash, or archive artifacts.
- [ ] **Step 3: Run focused and complete verification**
  Run focused release/installer/config/API/dashboard/enrollment tests, full relevant server suite, agent suite, Ruff/format, strict mypy, Alembic heads, JavaScript syntax, and `git diff --check`.
- [ ] **Step 4: Record factual completion status**
  Update the implementation checkpoint with only tests actually run, environment skips, existing baseline failures, and the browser/device acceptance procedure.
