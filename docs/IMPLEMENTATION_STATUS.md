# SkyBeat V1 Implementation Status

Last updated: 2026-09-23
Current stage: Stage 02 - Heartbeat API + Agent
Current milestone: Stage 02 acceptance checkpoint
Status: COMPLETE / ACCEPTED. Do not begin Stage 03 in this session.

## Completed

- Stage 01 foundation, device identity, credential lifecycle, MySQL setup and local operator CLI remain verified.
- Implemented strict schema-v1 heartbeat parsing: 128 KiB body bound, duplicate-key/non-finite/invalid-Unicode/nesting rejection, bounded telemetry, canonical identity/timestamps, null-versus-zero preservation, and normalized SHA-256 idempotency hashing.
- Implemented authenticated `POST /api/v1/heartbeats` with safe errors, committed acknowledgements, credential revalidation, device-identity rejection, and per-device in-process rate limiting.
- Added transactional receipt, sample and latest-snapshot persistence. Identical retries return the original acknowledgement without refreshing liveness; conflicting retries return 409.
- Added a partial Stage 02 Python agent: immutable schema-v1 snapshots, HTTPS-only configuration, psutil host collection, fixed NVIDIA query parsing, basic retry transport, and latest-only runtime.
- Added agent snapshot/sender -> FastAPI -> real isolated MySQL vertical integration coverage. Stage 03 availability, incidents, events and notifications were not implemented.
- Resolved the prior critical request-body finding: chunked bodies are capped while streaming and a regression test proves an oversized chunk does not cause later chunks to be consumed.
- Resolved the prior critical process finding: stdout/stderr are read concurrently into a shared 64 KiB cap; timeout, overflow and cancellation perform bounded cleanup, with a Linux process-group path.
- Added bounded total transport attempts, 401/403 slow-probe pacing, capped Retry-After handling and 30-to-60-second outage pacing. Valid JSON-safe telemetry byte values up to `2^53 - 1` are accepted.
- Moved synchronous heartbeat persistence off the ASGI event loop and added a concurrent-request regression test. Added narrowly fixture-tested NVIDIA driver failure classification.
- Added cancellation-aware runtime handling for in-flight GPU collection and send operations, bounded startup/interval jitter, CPU priming, Linux OS telemetry semantics, controlled host/network failure coverage, and basic transport failure logging.
- Resolved the final Stage 02 acceptance findings: synchronous host collection now runs in a killable spawned process with bounded cleanup, and process-wide agent log records are redacted with safe categorical collector-failure logging.
- Completed the Windows-spawn-safe regression proving that a permanently stuck system collector does not prevent prompt agent shutdown.

## In Progress

- None. Stage 03 has not been started.

## Verification Completed

- Server strict heartbeat contract tests: 130 passed.
- Server API transport/error tests: 6 passed.
- Server real-MySQL ingestion, idempotency, concurrency, rollback and lock-timeout tests: 8 passed.
- Stage 02 vertical integration: real agent snapshot/sender -> FastAPI ASGI transport -> real isolated MySQL; committed latest telemetry and history row verified.
- Full server suite against isolated local MySQL 8.4.10/InnoDB: 217 passed, 0 failed, 0 skipped.
- Full agent suite: 40 passed, 0 failed, 0 skipped.
- Server and agent Ruff check/format passed. Agent mypy passed for 10 source files; server mypy completed successfully for 19 source files using a disposable system-temp cache.
- `uv pip compile` produced hash-locked `agent/requirements.lock` from `agent/pyproject.toml`.
- Post-fix focused verification: agent suite 51 passed; server heartbeat contract/API suite 139 passed; real MySQL heartbeat and vertical integration suite 9 passed; full server suite 220 passed.
- Post-fix Ruff check/format and strict mypy passed for server (19 source files) and agent (10 source files).
- Final attempted verification: agent suite 61 passed; server suite 220 passed; agent Ruff/format/mypy passed for 11 source files; server Ruff/format/mypy passed for 19 source files; isolated MySQL migration state is `1b2785bb39ef (head)`.
- Final fresh Stage 02 agent verification on Windows: `tests/test_runtime.py::test_agent_process_exits_promptly_when_system_collector_is_permanently_stuck` passed (1 passed); full agent suite passed (64 passed); Ruff check and format check passed (19 files already formatted); strict mypy passed (11 source files).

## Verification Pending

- The retained isolated MySQL instance could not be started in this final session because its existing data files are not writable. ACLs, retained data, initialization and reset were deliberately left untouched. The prior successful real-MySQL 8.4.10/InnoDB evidence above remains the accepted Stage 02 database/vertical verification; a fresh repeat is environment-specific pending.
- Linux host/systemd behavior, real NVIDIA hardware/driver behavior, actual HTTPS proxy/network transport, load/soak testing and production deployment remain unverified.

## Files Changed

- `docs/IMPLEMENTATION_STATUS.md`
- `server/app/api/heartbeats.py`, `server/app/heartbeats/`, `server/app/schemas/heartbeat.py`, `server/app/models/heartbeat.py`
- `server/app/models/__init__.py`, `server/app/devices/service.py`, `server/app/main.py`
- `server/migrations/versions/1b2785bb39ef_heartbeat_storage.py`, `server/tests/`
- `agent/pyproject.toml`, `agent/requirements.lock`, `agent/src/`, `agent/tests/`

## Migrations Applied/Tested

- Stage 01 revision `614a53a9e2cb` remains applied to isolated local `skybeat_test` on MySQL 8.4.10/InnoDB.
- Additive Stage 02 revision `1b2785bb39ef` applied successfully to that same isolated database and exercised by real-MySQL tests. It creates `heartbeat_receipts`, `heartbeat_samples` and `device_latest`.
- No production database was accessed. No downgrade, drop, reset or destructive database action occurred.

## Known Issues

- No Stage 02 acceptance blockers remain.
- Environment-specific pending: real Linux process-group child cleanup, actual NVIDIA hardware/driver, real HTTPS/Caddy/network/TLS, Linux systemd shutdown, and soak validation remain unexercised on this Windows laptop.
- The retained isolated MySQL data directory is currently not writable, so final-session real-MySQL rerun remains pending; no corrective or destructive action was taken.
- The initial authenticated per-device rate limiter is intentionally in-process for the single-VM V1 baseline; it resets on API restart and must be revisited before horizontal scaling.
- Starlette emits httpx and AnyIO deprecation warnings in tests; assess dependency compatibility before production rollout.

## Security Notes

- No production access, deployment, notifications, credential rotation or destructive operation was performed.
- Payloads are strict/bounded and do not echo secrets. Credentials are revalidated on retries before returning stored acknowledgements.
- A valid credential with a different payload device UUID returns 403 and cannot retrieve an acknowledgement.
- Agent transport does not place credentials in URLs and does not disable TLS verification. GPU collection uses a fixed `nvidia-smi` argument list through `asyncio.create_subprocess_exec`.

## Environment Limitations

- Windows PowerShell workspace; use `.venv/Scripts/python.exe`.
- Portable MySQL and isolated credentials remain ignored under `.tools/` and `.test-data/`; the unrelated local MySQL service on port 3306 was untouched.
- Windows cache ACLs require Ruff `--no-cache` and mypy temporary-system cache directories.
- Agent tests use controlled fixtures on Windows. No actual Linux systemd service, NVIDIA device, Caddy TLS endpoint or external network was exercised.
- The retained isolated MySQL data files are not writable in this environment, preventing startup. Their ACLs and contents were not changed, and MySQL was not reset or reinitialized.

## Next Action

- Next stage: Stage 03 - Availability + Incidents + Email.
- Stop after this Stage 02 acceptance checkpoint. A future Stage 03 session must follow the resume procedure, inspect the Git diff, and preserve `Local MySQL.session.sql`. Do not auto-commit.

## Latest Stage Completion

- Stage: 02 - Heartbeat API + Agent.
- Status: COMPLETE / ACCEPTED.
- Files changed: Stage 02 server heartbeat/persistence implementation and migration; Stage 02 agent collection, runtime, transport, safe logging and tests; this checkpoint updates `docs/IMPLEMENTATION_STATUS.md`.
- Migrations: additive Stage 02 revision `1b2785bb39ef` was previously applied and verified against isolated MySQL 8.4.10/InnoDB; no production database was accessed.
- Tests executed: final fresh stuck-collector regression (1 passed), full agent suite (64 passed), agent Ruff check/format check (passed), agent strict mypy (11 source files, passed). Prior retained evidence: server suite 220 passed; strict contract/API 139 passed; real-MySQL heartbeat plus vertical integration 9 passed; server Ruff/format/mypy passed.
- Passed: all fresh final-session checks. Failed: none. Skipped: none.
- Security implications: bounded child cleanup prevents a stuck synchronous collector from delaying shutdown; the agent logging boundary redacts secrets. No production credentials, deployment, notifications, destructive database work or commits occurred.
- Known limitations: final-session MySQL rerun is pending solely because the retained instance's data files are not writable; Linux/NVIDIA/systemd/TLS/soak validation remains environment-specific pending.
- Next stage: Stage 03 - Availability + Incidents + Email. Do not begin it in this session.
- Worktree intentionally remains dirty/uncommitted because no commit was requested.

## Resume Command / Guidance

Read AGENTS.md, this file, the Stage 03 section of `docs/IMPLEMENTATION_PLAN.md`, and only necessary availability/alerting/security specifications. Inspect the current Git diff and migrations before beginning Stage 03. Production operations remain separately gated.
