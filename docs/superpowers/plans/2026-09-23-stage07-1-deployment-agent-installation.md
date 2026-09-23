# Stage 07.1 Deployment Baseline and Agent Installation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the validated Stage 06 deployment procedure in an operator-safe runbook and provide a repeatable, least-privilege agent installation at `/opt/skybeat`.

**Architecture:** Stage 07.1 changes only active deployment documentation and artifacts. A root-operated Bash installer validates a checked-out agent source directory plus a pre-existing protected environment file, creates the service installation, and delegates service execution to the existing non-root `skybeat` systemd unit. Static/executable safety tests inspect the committed artifacts without changing host services, credentials, database state, or networking.

**Tech Stack:** Bash, systemd, Python 3.12 virtual environments, pytest, Ruff, mypy, Alembic, Caddy documentation.

**Spec:** `docs/superpowers/specs/2026-09-23-stage07-dashboard-runbook-design.md`

## Global Constraints

- Implement Stage 07.1 only; do not create dashboard APIs, dashboard UI, telemetry history, incident APIs, migrations, or Stage 07.2 work.
- Preserve accepted Stage 01-06 heartbeat, identity, availability, GPU, incident, notification, authentication, authorization, and TLS semantics.
- Standardize active agent deployment instructions and artifacts on `/opt/skybeat`; retain `/etc/skybeat-agent/agent.env` and `/etc/systemd/system/skybeat-agent.service`.
- The running service remains `User=skybeat`, never root, retains `Restart=on-failure`, `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectHome=true`, `ProtectSystem=full`, and `UMask=0077`.
- The installer takes exactly `<agent-source-directory> <protected-env-file>` and rejects token/credential/secret command options before any host-changing operation.
- The installer must not echo environment-file content, use shell tracing, create credentials, weaken TLS, alter firewall/database/server state, or perform destructive cleanup.
- Update only current operational deployment instructions; preserve historical Stage 06 plans/specs as historical records.
- Record operator-supplied Stage 06 real-device evidence without credentials, tokens, private addresses, raw telemetry, or `.env` data.
- Do not commit or push.

## Review Focus

- A positional argument that looks like `--token` or `--credential` must fail before root/service work begins; Task 2 pins it.
- A missing source directory or environment file must fail with a safe actionable message and no file creation; Task 2 pins it.
- The systemd unit must use `/opt/skybeat`, `User=skybeat`, and the protected environment path together; Task 1 and Task 3 pin it.
- Private-CA guidance must improve trust safely and never suggest `verify=False`; Task 1 pins it.
- The status document must mark Stage 07 as in progress and Stage 07.1 only as complete after fresh evidence; Task 3 owns this update.

---

### Task 1: Runbook and active-path documentation

**Files:**
- Create: `docs/DEPLOYMENT_RUNBOOK.md`
- Modify: `docs/DEPLOYMENT.md`
- Modify: `docs/AGENT_SPEC.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `AGENTS.md`
- Test: `server/tests/test_deployment_artifacts.py`

**Interfaces:**
- Consumes: existing Stage 06 Caddy, migration, health-endpoint, systemd, and environment-file artifacts.
- Produces: one operator-facing runbook with a canonical `/opt/skybeat` agent install path and active reference documentation consistent with it.

- [ ] **Step 1: Add failing runbook/path-invariant tests**

```python
def test_stage07_runbook_documents_safe_private_ca_and_agent_installation():
    runbook = (ROOT / "docs" / "DEPLOYMENT_RUNBOOK.md").read_text(encoding="utf-8")
    assert "/opt/skybeat" in runbook
    assert "/etc/skybeat-agent/agent.env" in runbook
    assert "SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt" in runbook
    assert "Never use `verify=False`" in runbook
    assert "python -m uvicorn app.main:create_app --factory" in runbook

def test_active_agent_unit_uses_standardized_path_and_least_privilege():
    unit = (ROOT / "deployment/systemd/skybeat-agent.service").read_text(encoding="utf-8")
    assert "/opt/skybeat/venv/bin/skybeat-agent" in unit
    assert "/opt/skybeat-agent" not in unit
    assert "User=skybeat" in unit
    assert "EnvironmentFile=/etc/skybeat-agent/agent.env" in unit
```

- [ ] **Step 2: Run the focused tests to confirm they fail**

Run: `..\\.venv\\Scripts\\python.exe -m pytest -p no:cacheprovider tests/test_deployment_artifacts.py -q`

Expected: FAIL because the Stage 07 runbook does not yet exist and the committed unit still references `/opt/skybeat-agent`.

- [ ] **Step 3: Write the runbook before application work**

Create `docs/DEPLOYMENT_RUNBOOK.md` with these exact sections:

```markdown
# SkyBeat Deployment Runbook

## Development-validation baseline
Windows development/server; isolated MySQL 8.4.10 on loopback port 3307;
FastAPI port 8000; Caddy HTTPS port 443. These are validation details, not
production address or port requirements.

## Server deployment
Prerequisites, protected `.env`, explicit Alembic current/upgrade/head commands,
`python -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000`,
Caddy-only public ports, firewall guidance, and internal `/livez`/`/readyz` checks.

## Agent deployment
Install agent package into `/opt/skybeat/venv`; store the one-time credential only
in `/etc/skybeat-agent/agent.env`; install/enable `skybeat-agent.service`; verify
service, journal, heartbeat, device/latest records, and GPU telemetry without
printing the credential.

## TLS
For trusted private-CA development/LAN testing only, install the Caddy root into
the Ubuntu trust store, refresh certificates, and use
`SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt` when Python requires it.
Never use `verify=False`; public/system-trusted certificates are preferred in production.
```

Document non-destructive backup, isolated restore, upgrade, disable, supported rollback, and smoke procedures. State that Caddy loss produces a bounded transient agent transport failure rather than a TLS bypass condition. Use placeholders in every secret-bearing command.

- [ ] **Step 4: Change active deployment references only**

Change the active agent installation paths in `deployment/systemd/skybeat-agent.service`, the Stage 06 operator section of `docs/DEPLOYMENT.md`, the active installation/systemd sections of `docs/AGENT_SPEC.md`, the active agent-deployment section of `docs/ARCHITECTURE.md`, and the preferred agent path in `AGENTS.md`:

```ini
WorkingDirectory=/opt/skybeat
ExecStart=/opt/skybeat/venv/bin/skybeat-agent
```

Do not change historical Stage 06 plans/specifications or the `/etc/skybeat-agent/agent.env` path. Preserve every existing unit hardening directive and the `skybeat` user/group.

- [ ] **Step 5: Run focused documentation/artifact tests**

Run: `..\\.venv\\Scripts\\python.exe -m pytest -p no:cacheprovider tests/test_deployment_artifacts.py -q`

Expected: PASS with current runbook content, safe TLS text, and the standardized active systemd path.

### Task 2: Idempotent root-operated installer and sandboxed safety tests

**Files:**
- Create: `scripts/install-agent.sh`
- Modify: `scripts/validate_deployment.py`
- Modify: `server/tests/test_deployment_artifacts.py`

**Interfaces:**
- Consumes: `scripts/install-agent.sh <agent-source-directory> <protected-env-file>`, the committed `deployment/systemd/skybeat-agent.service`, and a source directory containing `pyproject.toml`, `requirements.lock`, and `src/skybeat_agent/`.
- Produces: a repeatable installation in `/opt/skybeat`, protected `/etc/skybeat-agent/agent.env`, and enabled/restarted `skybeat-agent.service` only when all validation succeeds.

- [ ] **Step 1: Add failing installer safety tests**

```python
def test_installer_is_required_and_contains_safe_argument_guards():
    installer = ROOT / "scripts" / "install-agent.sh"
    assert installer.is_file()
    text = installer.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text
    assert "--token" in text and "--credential" in text
    assert "/opt/skybeat/venv" in text
    assert "/etc/skybeat-agent/agent.env" in text
    assert "set -x" not in text

def test_installer_rejects_unsafe_option_before_host_changes():
    result = subprocess.run(["bash", str(INSTALLER), "--token", "value"], ...)
    assert result.returncode != 0
    assert "credential command-line arguments are not accepted" in result.stderr
```

Skip the executable Bash assertion only when `bash` is unavailable; static assertions remain mandatory. Do not invoke the installer with valid paths in tests.

- [ ] **Step 2: Run installer tests to confirm they fail**

Run: `..\\.venv\\Scripts\\python.exe -m pytest -p no:cacheprovider tests/test_deployment_artifacts.py -q`

Expected: FAIL because `scripts/install-agent.sh` and its validator requirement do not exist.

- [ ] **Step 3: Implement the installer with validation before mutation**

Create `scripts/install-agent.sh` beginning with:

```bash
#!/usr/bin/env bash
set -euo pipefail

usage() { printf '%s\n' 'usage: sudo ./scripts/install-agent.sh <agent-source-directory> <protected-env-file>' >&2; }
fail() { printf '%s\n' "install-agent: $1" >&2; exit 1; }

for argument in "$@"; do
    case "$argument" in
        --token|--credential|--secret|--token=*|--credential=*|--secret=*)
            fail 'credential command-line arguments are not accepted'
            ;;
    esac
done
[[ "$#" -eq 2 ]] || { usage; exit 64; }
source_dir="$1"
environment_file="$2"
[[ -d "$source_dir" && -f "$source_dir/pyproject.toml" && -f "$source_dir/requirements.lock" && -d "$source_dir/src/skybeat_agent" ]] || fail 'agent source directory is invalid'
[[ -f "$environment_file" ]] || fail 'protected environment file is missing'
[[ "${EUID}" -eq 0 ]] || fail 'run this installer as root'
```

After validation: use `id -u skybeat || useradd --system --user-group --no-create-home --shell /usr/sbin/nologin skybeat`; create `/opt/skybeat` and `/etc/skybeat-agent`; create `/opt/skybeat/venv` with `python3.12 -m venv` only when absent; install the pinned requirements with `--require-hashes`; install the package with `--no-deps`; copy the supplied environment file using `install -m 0600 -o root -g root` without reading or printing it; copy the committed unit with `install -m 0644 -o root -g root`; run `systemctl daemon-reload` then `systemctl enable --now skybeat-agent.service`. Do not use `rm`, `set -x`, `eval`, token variables, firewall commands, database commands, or TLS bypasses.

- [ ] **Step 4: Extend static deployment validation**

Add `scripts/install-agent.sh` to `REQUIRED`. Validate the unit contains `/opt/skybeat/venv/bin/skybeat-agent`, lacks `/opt/skybeat-agent`, and retains `User=skybeat` plus the protected environment file. Validate the installer contains the root guard, safe positional usage, forbidden-option guard, venv path, protected destination, `install -m 0600`, and `systemctl daemon-reload`; reject a committed `set -x` or `verify=False` string.

- [ ] **Step 5: Run focused installer validation**

Run: `bash -n scripts/install-agent.sh`

Run: `..\\.venv\\Scripts\\python.exe -m pytest -p no:cacheprovider tests/test_deployment_artifacts.py -q`

Run: `..\\.venv\\Scripts\\python.exe scripts/validate_deployment.py`

Expected: syntax, static safety tests, and validator pass without calling systemctl, copying an environment file, or changing the host.

### Task 3: Operator evidence and Stage 07.1 checkpoint

**Files:**
- Modify: `docs/IMPLEMENTATION_STATUS.md`
- Test: `server/tests/test_deployment_artifacts.py`

**Interfaces:**
- Consumes: the completed runbook, installer, unit, test results, and the user-supplied Stage 06 device-validation facts.
- Produces: a recoverable checkpoint with Stage 06 retained as accepted, Stage 07 marked in progress, and Stage 07.1 marked complete only after fresh evidence.

- [ ] **Step 1: Add a failing status-content test**

```python
def test_status_records_operator_supplied_stage06_evidence_without_secrets():
    status = (ROOT / "docs" / "IMPLEMENTATION_STATUS.md").read_text(encoding="utf-8")
    assert "operator-supplied Stage 06 acceptance evidence" in status
    assert "NVIDIA GeForce RTX 5080" in status
    assert "Current stage: Stage 07" in status
    assert "Stage 07.1" in status
```

- [ ] **Step 2: Run the focused test to confirm failure**

Run: `..\\.venv\\Scripts\\python.exe -m pytest -p no:cacheprovider tests/test_deployment_artifacts.py -q`

Expected: FAIL because Stage 07.1 has not yet been recorded.

- [ ] **Step 3: Update status from observed evidence only**

Set `Current stage: Stage 07 - Dashboard, Operational Visibility & Deployment Runbook`, `Current milestone: Stage 07.1 - Deployment Baseline and Agent Installation`, and `Status: IN PROGRESS`. Add the user-supplied Stage 06 acceptance evidence exactly as an operator-supplied report: Ubuntu, RTX 5080, driver 595.84, CUDA 13.2, `/opt/skybeat`, HTTPS/Caddy/FastAPI/MySQL path, successful current telemetry records, ONLINE, GPU OK, CPU/memory/hostname/GPU-summary. Exclude credentials, tokens, addresses, raw dumps, and `.env` values.

After fresh checks pass, record Stage 07.1 as complete while retaining Stage 07 as in progress, no migration, no dashboard API/UI work, the exact results, unavailable Docker/systemd/real-MySQL checks, and the user-provided real-device evidence as distinct from locally executed verification.

- [ ] **Step 4: Run final focused status/artifact checks**

Run: `..\\.venv\\Scripts\\python.exe -m pytest -p no:cacheprovider tests/test_deployment_artifacts.py -q`

Expected: PASS and Stage 07 remains clearly in progress.

### Task 4: Stage 07.1 regression and acceptance verification

**Files:**
- Modify: `docs/IMPLEMENTATION_STATUS.md`

**Interfaces:**
- Consumes: all Stage 07.1 artifacts and focused evidence.
- Produces: an accurate Stage 07.1 completion checkpoint without marking Stage 07 complete.

- [ ] **Step 1: Run server tests and static checks**

Run from `server`:

```text
..\\.venv\\Scripts\\python.exe -m pytest -p no:cacheprovider -q
..\\.venv\\Scripts\\ruff.exe check --no-cache app tests migrations ..\\scripts
..\\.venv\\Scripts\\ruff.exe format --check --no-cache app tests migrations ..\\scripts
..\\.venv\\Scripts\\mypy.exe app --strict --cache-dir D:\\skybeat\\.stage07-mypy-cache
```

Expected: all non-MySQL tests pass; unavailable isolated MySQL tests are reported as skips rather than substituted.

- [ ] **Step 2: Run agent regressions and static checks**

Run from `agent`:

```text
..\\.venv\\Scripts\\python.exe -m pytest -p no:cacheprovider -q
..\\.venv\\Scripts\\ruff.exe check --no-cache src tests
..\\.venv\\Scripts\\ruff.exe format --check --no-cache src tests
..\\.venv\\Scripts\\mypy.exe src --strict --cache-dir D:\\skybeat\\.stage07-agent-mypy-cache
```

Expected: agent behavior and schema remain unchanged.

- [ ] **Step 3: Verify migration graph and deployment/static artifacts**

Run from `server`:

```text
..\\.venv\\Scripts\\python.exe -m alembic heads
..\\.venv\\Scripts\\python.exe -m alembic history
..\\.venv\\Scripts\\python.exe ..\\scripts\\validate_deployment.py
git -C .. diff --check
```

Run `docker compose config -q` and Docker build only when Docker/Compose is available. Do not start services, modify MySQL, or alter ACLs to make a check pass.

- [ ] **Step 4: Record acceptance and stop**

Update `docs/IMPLEMENTATION_STATUS.md` with fresh counts, skipped tests, static results, sole Alembic head, installer syntax/validator results, whitespace result, user-supplied Stage 06 evidence, and environment-pending checks. Report Stage 07 as `IN PROGRESS`, Stage 07.1 as complete only if these checks pass, and explicitly stop before Stage 07.2.

## Plan Self-Review

- Spec coverage: Task 1 implements the runbook and active path change; Task 2 implements the idempotent installer and safety validation; Task 3 records evidence/status; Task 4 executes every requested non-destructive verification gate.
- Placeholder scan: no deferred code, credentials, host values, database actions, or ambiguous installation inputs remain. Docker/systemd/MySQL runtime checks are explicitly environment-dependent.
- Type consistency: Stage 07.1 is Bash/documentation/static-test work; its only public interface is the exact two-argument installer invocation and existing systemd service name/path.
- Review focus: every listed safety failure has a direct Task 1, 2, or 3 assertion; tests never execute a valid installer path or contact infrastructure.
