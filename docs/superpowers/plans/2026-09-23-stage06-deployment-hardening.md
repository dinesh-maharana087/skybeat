# Stage 06 Deployment and Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the accepted SkyBeat V1 application reproducibly deployable without automatic schema changes or new product behavior.

**Architecture:** One non-root Python image serves the separately run API, worker, and explicitly invoked migration job. Compose places Caddy alone on public host ports and keeps MySQL on an internal data network. Existing API health endpoints and durable notification state are retained; settings expose the documented timing policy and the worker receives bounded signal-aware shutdown.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/Alembic, Docker Compose, Caddy, systemd, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-23-stage06-deployment-hardening-design.md`

## Global Constraints

- Preserve accepted Stages 01–05 and Alembic head `a58c71d904ef`; add no migration unless a schema change is unavoidable.
- Never auto-run migrations from API or worker startup; never reset, drop, initialize, or repair a database.
- Caddy is the only public central-server service; MySQL, API, and worker have no host port publication.
- Keep secrets out of Git, command-line examples, logs, Docker image layers, and test output.
- Agent remains a direct systemd installation under a least-privilege `skybeat` user.
- Do not change retained local MySQL data, ACLs, initialization, or configuration.
- Do not commit changes; the user explicitly prohibited automatic commits.

## Review Focus

- A production setting containing a safe-looking placeholder must fail before any service starts; Task 1 pins this.
- An offline threshold equal to or below the suspect threshold must fail instead of changing availability semantics; Task 1 pins this.
- A worker receiving SIGTERM must stop its loop and dispose the database without losing persisted work; Task 2 pins this.
- Compose must not accidentally expose API/MySQL or invoke migration as a dependency; Task 3 pins this.
- Proxy health endpoints and OAuth-bearing query strings must not become public/sensitive logs; Task 3 pins Caddy policy and Task 4 documents verification.

---

### Task 1: Validated timing and production configuration

**Files:**
- Modify: `server/app/config.py`
- Modify: `server/app/health/service.py`
- Modify: `server/app/heartbeats/service.py`
- Modify: `server/app/api/heartbeats.py`
- Modify: `.env.example`
- Modify: `server/tests/test_config.py`
- Modify: `server/tests/test_health.py`

**Interfaces:**
- Produces `Settings.suspect_after_seconds: int`, `Settings.offline_after_seconds: int`, and `Settings.notification_poll_seconds: int`.
- Extends `availability_state(baseline, now, *, suspect_after_seconds=75, offline_after_seconds=180)` without changing default results.
- Extends `AvailabilityService(..., suspect_after_seconds=75, offline_after_seconds=180)` and `HeartbeatService(..., suspect_after_seconds=75, offline_after_seconds=180)`.

- [ ] **Step 1: Write failing configuration and boundary tests**

```python
def test_production_rejects_placeholder_secrets_and_invalid_availability_order():
    with pytest.raises(ValidationError):
        Settings(..., suspect_after_seconds=180, offline_after_seconds=180)
    with pytest.raises(ValidationError):
        Settings(..., smtp_password="REPLACE_WITH_PROTECTED_SECRET")

def test_availability_state_uses_configured_boundaries():
    assert availability_state(now - timedelta(seconds=10), now,
                              suspect_after_seconds=10, offline_after_seconds=20) == SUSPECT
```

- [ ] **Step 2: Run focused tests to confirm failure**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests/test_config.py tests/test_health.py -q`

Expected: failure because configuration fields and injected thresholds do not exist.

- [ ] **Step 3: Implement validated settings and dependency propagation**

```python
suspect_after_seconds: int = Field(default=75, ge=1, le=3600)
offline_after_seconds: int = Field(default=180, ge=2, le=86400)
notification_poll_seconds: int = Field(default=2, ge=1, le=60)

if self.offline_after_seconds <= self.suspect_after_seconds:
    raise ValueError("Offline threshold must exceed suspect threshold.")
```

Pass settings values from heartbeat API and worker construction into `AvailabilityService`; retain 75/180 defaults for direct service callers. Reject `REPLACE`, `CHANGEME`, and equivalent protected-secret placeholders only in production mode.

- [ ] **Step 4: Update safe environment documentation and rerun focused tests**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests/test_config.py tests/test_health.py -q`

Expected: pass, retaining exact 75/180 default boundary behavior.

### Task 2: Worker scheduling and graceful termination

**Files:**
- Modify: `server/app/worker.py`
- Modify: `server/tests/test_worker.py`

**Interfaces:**
- Produces `run_loop(settings, database, providers, stop, *, monotonic, wait)` that schedules availability and notification work independently.
- Retains `run_once(settings, database, *, provider)` as a bounded compatibility helper.

- [ ] **Step 1: Write failing scheduling and stop tests**

```python
def test_worker_loop_uses_notification_poll_interval_and_stops_without_new_claims(monkeypatch):
    stop = Event()
    run_loop(settings, database, providers, stop, monotonic=fake_clock, wait=fake_wait)
    assert calls == ["sweep", "deliver", "deliver", "deliver"]
```

- [ ] **Step 2: Run focused worker tests to confirm failure**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests/test_worker.py -q`

Expected: failure because `run_loop` is absent.

- [ ] **Step 3: Implement bounded independent scheduling and signal handling**

```python
def run_loop(..., stop: Event, *, monotonic: Callable[[], float] = time.monotonic,
             wait: Callable[[float], bool] | None = None) -> None:
    # perform due availability and delivery work, then wait only until next due time
```

Install SIGINT/SIGTERM handlers only in `main`, use `threading.Event`, log safe startup/shutdown categories, and always dispose `Database` in `finally`. Do not call providers inside heartbeat transactions or change durable retry/lease behavior.

- [ ] **Step 4: Run focused worker tests**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests/test_worker.py -q`

Expected: pass, including SMS no-network fallback coverage.

### Task 3: Compose, Caddy, Docker image, and agent service artifacts

**Files:**
- Create: `deployment/docker/Dockerfile.server`
- Create: `deployment/caddy/Caddyfile`
- Create: `deployment/systemd/skybeat-agent.service`
- Create: `deployment/systemd/agent.env.example`
- Create: `docker-compose.yml`
- Create: `scripts/validate-deployment.sh`
- Create: `server/tests/test_deployment_artifacts.py`

**Interfaces:**
- Compose services are named `caddy`, `api`, `worker`, `mysql`, and profile-gated `migrate`.
- API health is checked internally at `/livez`; Caddy rejects `/livez` and `/readyz` from public routing.
- The shared image supports `python -m uvicorn app.main:create_app --factory` and `python -m app.worker`.

- [ ] **Step 1: Write failing artifact-invariant tests**

```python
def test_compose_keeps_mysql_and_api_off_host_ports():
    compose = _read("docker-compose.yml")
    assert "3306:3306" not in compose
    assert "8000:8000" not in compose
    assert "migrate:" in compose and "profiles:" in compose

def test_caddy_limits_bodies_and_keeps_health_endpoints_internal():
    caddy = _read("deployment/caddy/Caddyfile")
    assert "128KB" in caddy
    assert "/livez" in caddy and "respond" in caddy
```

- [ ] **Step 2: Run artifact tests to confirm failure**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests/test_deployment_artifacts.py -q`

Expected: failure because deployment artifacts do not exist.

- [ ] **Step 3: Create hardened artifacts**

Use named MySQL/Caddy volumes, `edge`/`data` networks, `restart: unless-stopped`, non-root shared application containers, read-only application filesystems, bounded temporary storage, Compose log rotation, MySQL 8.4 health check, Caddy-only 80/443 publication, Caddy HTTPS reverse proxy and 128 KiB request limit. Make `migrate` an explicit profile with `SKYBEAT_MIGRATION_DATABASE_URL`, never an API/worker dependency.

Create a conservative agent systemd unit using `Restart=on-failure`, `RestartSec=5`, `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectHome=true`, `ProtectSystem=full`, and `UMask=0077`. Include only safe placeholders in the environment example. The validation script runs `docker compose config -q` and confirms required artifacts without contacting a database.

- [ ] **Step 4: Run focused artifact tests and available Compose validation**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests/test_deployment_artifacts.py -q`

Run: `docker compose config -q`

Expected: tests pass; Compose result is recorded as verified or tooling-unavailable.

### Task 4: Deployment runbook, checklist, and local smoke evidence

**Files:**
- Modify: `docs/DEPLOYMENT.md`
- Modify: `README.md`
- Modify: `docs/IMPLEMENTATION_STATUS.md`
- Create: `docs/PRODUCTION_CHECKLIST.md`
- Modify: `server/tests/test_deployment_artifacts.py`

**Interfaces:**
- Produces an operator-safe deployment, migration, backup, isolated restore, agent install, upgrade, rollback, and smoke-test procedure.
- Separates automatic verification from environment-required checks.

- [ ] **Step 1: Write failing documentation/artifact safety tests**

```python
def test_runbook_requires_backup_before_explicit_migration_and_never_documents_volume_deletion():
    deployment = _read("docs/DEPLOYMENT.md")
    assert "backup" in deployment.lower()
    assert "docker compose --profile migrate run --rm migrate" in deployment
    assert "down -v" in deployment
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests/test_deployment_artifacts.py -q`

Expected: failure until the concrete Stage 06 runbook text exists.

- [ ] **Step 3: Add the operational runbook and smoke procedure**

Document restrictive secret-file permissions; externally exposed ports; explicit migration/current/head commands; no-reset rule; API/worker/Caddy health checks; agent installation, canary upgrade, and disable procedure; daily backup plus 30-day/off-host retention; isolated restore first; no automatic database downgrade; real-environment acceptance matrix; and the known MySQL limitation. Update README to describe Stage 06 artifacts rather than the obsolete Stage 01-only state.

- [ ] **Step 4: Run focused artifact tests**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests/test_deployment_artifacts.py -q`

Expected: pass.

### Task 5: Full verification and acceptance checkpoint

**Files:**
- Modify: `docs/IMPLEMENTATION_STATUS.md`

- [ ] **Step 1: Run focused Stage 06 tests**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests/test_config.py tests/test_health.py tests/test_worker.py tests/test_deployment_artifacts.py -q`

- [ ] **Step 2: Run complete suites and static gates**

Run: `..\\.venv\\Scripts\\python.exe -m pytest -q`

Run: `cd ..\\agent; ..\\.venv\\Scripts\\python.exe -m pytest -q`

Run: `..\\.venv\\Scripts\\ruff.exe check --no-cache app tests migrations`

Run: `..\\.venv\\Scripts\\ruff.exe format --check --no-cache app tests migrations`

Run: `..\\.venv\\Scripts\\mypy.exe --cache-dir C:\\Users\\mahar\\AppData\\Local\\Temp\\skybeat-stage06-mypy app`

Run: `..\\.venv\\Scripts\\ruff.exe check --no-cache src tests` and `..\\.venv\\Scripts\\ruff.exe format --check --no-cache src tests` from `agent`.

Run: `..\\.venv\\Scripts\\mypy.exe --cache-dir C:\\Users\\mahar\\AppData\\Local\\Temp\\skybeat-stage06-agent-mypy src` from `agent`.

- [ ] **Step 3: Verify migration graph and deployment artifacts**

Run: `..\\.venv\\Scripts\\python.exe -m alembic heads`

Run: `..\\.venv\\Scripts\\python.exe -m alembic history`

Run: `docker compose config -q` and, when a local Docker daemon is available, `docker compose build`.

Run: `git diff --check`

- [ ] **Step 4: Update status with observed evidence only**

Record test counts, skipped tests, static results, sole head, artifact validation, and every environment-pending check. Mark Stage 06 accepted only if all executable requirements pass. Do not start a new stage or commit.

## Plan Self-Review

- Spec coverage: Tasks 1–4 cover timing/configuration, API/worker behavior, Compose/Caddy/systemd, documentation, backups, smoke procedure, and hardening; Task 5 covers every requested executable gate.
- Placeholders: No deferred implementation or unspecified interface remains. The operationally unavailable checks are explicitly environment-pending rather than implementation placeholders.
- Type consistency: Settings names, service constructor keyword names, and `run_loop` signature are defined before consumers use them.
- Review focus: Every listed failure mode has a named test in its owning task.
