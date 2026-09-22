# SkyBeat V1 Implementation Status

Last updated: 2026-09-22
Current stage: Stage 02 - Heartbeat API + Agent
Current milestone: Stage 02 incomplete - bounded system-collector shutdown and enforced safe logging
Status: Blocked from safe Stage 02 completion by review findings; do not begin Stage 03.

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

## In Progress

- Resolve the two final independent-review acceptance blockers before relying on the agent implementation or beginning Stage 03.

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

## Verification Pending

- Independent final review found no remaining critical defect in streaming body limits, bounded subprocess handling, driver classification, numeric ranges, transport deadlines/pacing, or asynchronous DB offload.
- Final independent review found two Stage 02 acceptance blockers; the passing suite is insufficient evidence for Stage 02 completion.
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

- Blocking Stage 02: `build_snapshot()` runs synchronous host collection through `asyncio.to_thread`. Runtime task cancellation does not terminate a stuck worker thread; a blocked psutil/filesystem call can therefore keep the agent process alive past the approved 15-second shutdown target. The new runtime tests cover blocked async GPU/send work but not a blocked synchronous host collector.
- Blocking Stage 02: agent logging is not an enforced secret-redaction boundary. `logging.basicConfig` does not filter dependency/root output at DEBUG, and collector exceptions are converted to fallback telemetry without a safe operator-visible category. The current test covers one sender message only.
- Environment-specific pending: real Linux process-group child cleanup, actual NVIDIA hardware/driver, real HTTPS/Caddy/network/TLS, Linux systemd shutdown, and soak validation remain unexercised on this Windows laptop.
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
- Recommended fresh-session action: read AGENTS.md, this file, only Stage 02 sections 10-17 of `docs/IMPLEMENTATION_PLAN.md` and the necessary API/agent/security specifications. Inspect `git status`, `git diff`, migrations and Stage 02 tests. First design and test a bounded system-collector execution boundary that cannot keep process shutdown alive; then add enforced log redaction and safe collector-failure logging tests. Preserve `Local MySQL.session.sql`; do not auto-commit or begin Stage 03.

## Latest Stage Completion

- Stage: 01 - Foundation + Database + Device Identity.
- Status: complete and verified locally. Stage 02 is not accepted: the prior critical defects and most remaining findings are fixed, but bounded synchronous host-collection shutdown and enforced safe logging remain blocking.
- Stage 02 attempted verification: agent 61 passed; server 220 passed; contract/API 139 passed; real-MySQL and vertical integration 9 passed; Ruff/format/mypy passed; isolated migration is at `1b2785bb39ef (head)`. Two upstream TestClient deprecation warnings remain.
- Worktree intentionally remains dirty/uncommitted because no commit was requested.

## Resume Command / Guidance

Read AGENTS.md, this file, Stage 02 sections 10-17 of `docs/IMPLEMENTATION_PLAN.md` and only necessary API/agent/security specifications. Inspect the Git diff and migrations before continuing. Resume with a design/test for bounded synchronous host collection and shutdown, followed by enforced log redaction and collector-failure diagnostics; do not begin Stage 03. Production operations remain separately gated.
