# SkyBeat V1 Implementation Status

Last updated: 2026-09-22
Current stage: Stage 02 - Heartbeat API + Agent
Current milestone: Stage 02 incomplete - bounded request/process execution and agent runtime hardening
Status: Blocked from safe Stage 02 completion by review findings; do not begin Stage 03.

## Completed

- Stage 01 foundation, device identity, credential lifecycle, MySQL setup and local operator CLI remain verified.
- Implemented strict schema-v1 heartbeat parsing: 128 KiB body bound, duplicate-key/non-finite/invalid-Unicode/nesting rejection, bounded telemetry, canonical identity/timestamps, null-versus-zero preservation, and normalized SHA-256 idempotency hashing.
- Implemented authenticated `POST /api/v1/heartbeats` with safe errors, committed acknowledgements, credential revalidation, device-identity rejection, and per-device in-process rate limiting.
- Added transactional receipt, sample and latest-snapshot persistence. Identical retries return the original acknowledgement without refreshing liveness; conflicting retries return 409.
- Added a partial Stage 02 Python agent: immutable schema-v1 snapshots, HTTPS-only configuration, psutil host collection, fixed NVIDIA query parsing, basic retry transport, and latest-only runtime.
- Added agent snapshot/sender -> FastAPI -> real isolated MySQL vertical integration coverage. Stage 03 availability, incidents, events and notifications were not implemented.

## In Progress

- Correct the Stage 02 review findings before relying on the current partial agent/API implementation or beginning Stage 03.

## Verification Completed

- Server strict heartbeat contract tests: 130 passed.
- Server API transport/error tests: 6 passed.
- Server real-MySQL ingestion, idempotency, concurrency, rollback and lock-timeout tests: 8 passed.
- Stage 02 vertical integration: real agent snapshot/sender -> FastAPI ASGI transport -> real isolated MySQL; committed latest telemetry and history row verified.
- Full server suite against isolated local MySQL 8.4.10/InnoDB: 217 passed, 0 failed, 0 skipped.
- Full agent suite: 40 passed, 0 failed, 0 skipped.
- Server and agent Ruff check/format passed. Agent mypy passed for 10 source files; server mypy completed successfully for 19 source files using a disposable system-temp cache.
- `uv pip compile` produced hash-locked `agent/requirements.lock` from `agent/pyproject.toml`.

## Verification Pending

- Critical review findings remain unaddressed; the passing suite is insufficient evidence for Stage 02 completion.
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

- Critical: `server/app/api/heartbeats.py` buffers a chunked/no-`Content-Length` body through `await request.body()` before the 128 KiB parser check. Enforce the body limit as bytes are received to prevent unauthenticated memory exhaustion.
- Critical: `agent/src/skybeat_agent/collectors/process.py` uses `process.communicate()` and only limits output after it has been fully captured. Replace it with bounded concurrent stream readers and process-group cleanup.
- Important: the agent lacks the approved total-attempt deadline, slow probe/outage pacing, bounded `Retry-After`, system collection deadline, driver-failure classification, runtime graceful-stop coverage, useful secret-safe logging, and required collector/transport failure tests.
- Important: artificial 100 GiB disk and 24 GiB GPU limits in the contract/agent contradict the approved `2^53 - 1` byte range and exclude valid hardware.
- Important: synchronous MySQL work currently runs inline from the async heartbeat handler and can block the event loop during database waits.
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

## Next Action

- Exact next stage after Stage 02 acceptance: Stage 03 - Availability + Incidents + Email.
- Recommended fresh-session action: read AGENTS.md, this file, only Stage 02 sections 10-17 of `docs/IMPLEMENTATION_PLAN.md` and the necessary API/agent/security specifications. Inspect `git status`, `git diff`, migrations and Stage 02 tests. First write red tests for streaming request-size enforcement and bounded subprocess output; then address the documented transport/runtime gaps sequentially. Preserve `Local MySQL.session.sql`; do not auto-commit or begin Stage 03.

## Latest Stage Completion

- Stage: 01 - Foundation + Database + Device Identity.
- Status: complete and verified locally. Stage 02 code is present and tests pass, but it is not accepted because review found the critical and important issues recorded above.
- Stage 02 attempted verification: server 217 passed and agent 40 passed; focused contract/API/MySQL/vertical tests and static checks passed. Two upstream TestClient deprecation warnings remain.
- Worktree intentionally remains dirty/uncommitted because no commit was requested.

## Resume Command / Guidance

Read AGENTS.md, this file, Stage 02 sections 10-17 of `docs/IMPLEMENTATION_PLAN.md` and only necessary API/agent/security specifications. Inspect the Git diff and migrations before continuing. Resume at the first unverified Stage 02 safety finding; do not begin Stage 03. Production operations remain separately gated.
