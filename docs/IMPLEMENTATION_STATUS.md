# SkyBeat V1 Implementation Status

Last updated: 2026-09-23
Current stage: Stage 05 - GPU Incidents + SMS Boundary
Current milestone: Stage 05 acceptance checkpoint
Status: COMPLETE / ACCEPTED. Stage 06 has not been started.

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
- Implemented Stage 03 server-authoritative availability evaluation with exact 75/180-second boundaries, trusted receipt-time baselines, late-heartbeat reconciliation under the existing device-row lock, and a five-second worker sweep configuration.
- Implemented durable availability incidents, offline/recovery events, MySQL-compatible one-active-incident enforcement, durable notification deliveries/attempts, recovery supersession, bounded retry/lease recovery, SMTP provider classification, and a separate worker entry point.
- Implemented Stage 04 Google OIDC authorization-code login/callback/logout through Authlib, with PKCE S256, state, nonce, a Secure/HttpOnly/SameSite=Lax host-only binding cookie, server-side short-lived single-use transactions, and opaque application-owned sessions.
- Implemented deny-by-default dashboard authorization using a normalized exact email allowlist and/or Google-verified hosted-domain claim, including session revalidation after an allowlist change.
- Added protected project, device, detail and alert-history APIs; a server-rendered Jinja Device Status page with safe DOM-only polling, stale telemetry labels, filters, and expandable detail/incident views.
- Completed Stage 05 GPU lifecycle handling: server-policy-aware effective state, two-observation degradation/recovery semantics, 75-second maximum confirmation gap, CPU-only suppression, durable GPU incidents/events, stale-outage supersession, and dashboard effective-state projection.
- Completed the provider-independent SMS boundary: validated server-controlled E.164 recipients, durable EMAIL/SMS queue jobs, channel-routed worker delivery/retry/idempotency reuse, deterministic fake provider, and a safe no-network disabled adapter pending a separately approved vendor.

## In Progress

- None. Stage 05 is complete; Stage 06 has not been started.

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
- Stage 03 focused Windows verification: availability/model/provider/worker tests passed (10 passed); Stage 03 MySQL lifecycle tests were collected and skipped (8) only because `SKYBEAT_TEST_DATABASE_URL` is unavailable; targeted configuration tests passed (18 passed); Stage 03 Ruff check passed; strict server mypy passed for 27 source files.
- Final Stage 03 acceptance verification: complete server suite passed (216 passed, 27 skipped, 0 failed); all skips require the unavailable isolated MySQL URL. Ruff check and format check passed (49 files already formatted); strict mypy passed (27 source files); migration history reports `625bfa1677df` as head; `git diff --check` passed.
- Stage 04 focused verification: dashboard authorization/configuration/session-model/API/page/read-projection tests passed (32 passed); three new MySQL session-lifecycle tests collected and skipped only because `SKYBEAT_TEST_DATABASE_URL` is unavailable.
- Final Stage 04 acceptance verification: complete server suite passed (231 passed, 30 skipped, 0 failed). Ruff check and format check passed (64 files already formatted); strict mypy passed for 36 source files; migration history reports `7d2e8a91c4bf` as the sole head; `git diff --check` passed.
- Stage 05 focused GPU/SMS/dashboard/configuration/worker/provider tests passed (38 passed).
- Final Stage 05 server verification: full suite passed (241 passed, 33 skipped, 0 failed). Every skip requires the unavailable isolated MySQL URL. Ruff check and format check passed (66 files already formatted); strict mypy passed for 39 source files; Alembic history has sole head `a58c71d904ef`; `git diff --check` passed.

## Verification Pending

- The retained isolated MySQL instance could not be started in this final session because its existing data files are not writable. ACLs, retained data, initialization and reset were deliberately left untouched. The prior successful real-MySQL 8.4.10/InnoDB evidence above remains the accepted Stage 02 database/vertical verification; a fresh repeat is environment-specific pending.
- Stage 03 real-MySQL migration, availability race, incident deduplication, delivery claiming and rollback verification are pending only because that retained instance cannot safely start. The tests are present; no substitute is treated as proof of MySQL behavior.
- Stage 04 real-MySQL migration and durable OAuth-transaction/session lifecycle verification are pending only because that retained instance cannot safely start. The tests are present; fake OIDC tests validate the application boundary but are not represented as real-Google or real-MySQL evidence.
- Stage 05 real-MySQL migration, GPU incident/event/delivery lifecycle, offline supersession, and independent EMAIL/SMS retry tests are present but pending only because that retained instance cannot safely start. The retained data, ACLs and initialization state were not modified.
- Linux host/systemd behavior, real NVIDIA hardware/driver behavior, actual HTTPS proxy/network transport, load/soak testing and production deployment remain unverified.

## Files Changed

- `docs/IMPLEMENTATION_STATUS.md`
- `server/app/api/heartbeats.py`, `server/app/heartbeats/`, `server/app/schemas/heartbeat.py`, `server/app/models/heartbeat.py`
- `server/app/models/__init__.py`, `server/app/devices/service.py`, `server/app/main.py`
- `server/migrations/versions/1b2785bb39ef_heartbeat_storage.py`, `server/tests/`
- `agent/pyproject.toml`, `agent/requirements.lock`, `agent/src/`, `agent/tests/`
- Stage 03: `server/app/health/`, `server/app/notifications/`, `server/app/worker.py`, `server/app/models/alerts.py`, heartbeat/configuration integration, migration `625bfa1677df`, focused Stage 03 tests, `.env.example`, and `server/pyproject.toml`.
- Stage 04: `server/app/dashboard/`, `server/app/api/auth.py`, `server/app/api/dashboard.py`, `server/app/api/dashboard_page.py`, `server/app/templates/`, `server/app/static/`, authentication/read integration in `server/app/main.py`, additive migration `7d2e8a91c4bf`, configuration/dependency updates, `.env.example`, and focused dashboard tests.
- Stage 05: `.env.example`, `server/app/gpu/`, GPU state model and heartbeat/availability/dashboard integration, notification worker/email routing, provider-neutral SMS adapter, additive migration `a58c71d904ef`, and focused GPU/SMS lifecycle tests.

## Migrations Applied/Tested

- Stage 01 revision `614a53a9e2cb` remains applied to isolated local `skybeat_test` on MySQL 8.4.10/InnoDB.
- Additive Stage 02 revision `1b2785bb39ef` applied successfully to that same isolated database and exercised by real-MySQL tests. It creates `heartbeat_receipts`, `heartbeat_samples` and `device_latest`.
- Additive Stage 03 revision `625bfa1677df` is the current Alembic head and chains from `1b2785bb39ef`; it has not been applied in this session because the retained isolated MySQL data files are not writable.
- Additive Stage 04 revision `7d2e8a91c4bf` chains from `625bfa1677df` and is the current Alembic head. It creates `admin_sessions` and `oauth_transactions`; it has not been applied in this session because the retained isolated MySQL data files are not writable.
- Additive Stage 05 revision `a58c71d904ef` chains from `7d2e8a91c4bf` and is the sole Alembic head. It adds durable device GPU confirmation state; its real-MySQL application is environment-pending because the retained data files are not writable.
- No production database was accessed. No downgrade, drop, reset or destructive database action occurred.

## Known Issues

- No Stage 02 acceptance blockers remain.
- Environment-specific pending: real Linux process-group child cleanup, actual NVIDIA hardware/driver, real HTTPS/Caddy/network/TLS, Linux systemd shutdown, and soak validation remain unexercised on this Windows laptop.
- The retained isolated MySQL data directory is currently not writable, so final-session real-MySQL rerun remains pending; no corrective or destructive action was taken.
- The initial authenticated per-device rate limiter is intentionally in-process for the single-VM V1 baseline; it resets on API restart and must be revisited before horizontal scaling.
- Starlette emits httpx and AnyIO deprecation warnings in tests; assess dependency compatibility before production rollout.
- No Stage 03 software acceptance blockers remain. Its MySQL-specific verification remains environment-pending rather than fabricated.
- No Stage 04 software acceptance blockers remain. Its real-MySQL migration/session verification, production Google OIDC credentials, and real browser/HTTPS proxy verification remain environment-specific pending.
- No Stage 05 software acceptance blockers remain. A production SMS vendor is intentionally not selected; the tested fake/no-network adapter records no external delivery and leaves vendor integration as an environment/product decision.

## Security Notes

- No production access, deployment, notifications, credential rotation or destructive operation was performed.
- Payloads are strict/bounded and do not echo secrets. Credentials are revalidated on retries before returning stored acknowledgements.
- A valid credential with a different payload device UUID returns 403 and cannot retrieve an acknowledgement.
- Agent transport does not place credentials in URLs and does not disable TLS verification. GPU collection uses a fixed `nvidia-smi` argument list through `asyncio.create_subprocess_exec`.
- Dashboard authentication uses Authlib validation rather than manually decoding JWTs. Google tokens are not persisted; only hashes of browser session/state/binding values and encrypted nonce/PKCE material are stored. Dashboard responses use `no-store`, the UI inserts dynamic values with `textContent`, and logout checks same-origin headers in addition to SameSite cookies.

## Environment Limitations

- Windows PowerShell workspace; use `.venv/Scripts/python.exe`.
- Portable MySQL and isolated credentials remain ignored under `.tools/` and `.test-data/`; the unrelated local MySQL service on port 3306 was untouched.
- Windows cache ACLs require Ruff `--no-cache` and mypy temporary-system cache directories.
- Agent tests use controlled fixtures on Windows. No actual Linux systemd service, NVIDIA device, Caddy TLS endpoint or external network was exercised.
- The retained isolated MySQL data files are not writable in this environment, preventing startup. Their ACLs and contents were not changed, and MySQL was not reset or reinitialized.

## Next Action

- Next stage: Stage 06 - Deployment + Production Hardening. Do not begin it in this checkpoint. Preserve `Local MySQL.session.sql` and leave the retained MySQL data directory untouched unless separately authorized.

## Latest Stage Completion

- Stage: 05 - GPU Incidents + SMS Boundary.
- Status: COMPLETE / ACCEPTED.
- Files changed: deterministic server GPU confirmation and durable state, heartbeat/availability/incident/event integration, GPU alert cancellation on offline/recovery, server-effective dashboard state, SMS recipient configuration, durable dual-channel jobs and worker routing, fake/no-network SMS providers, focused tests, and additive migration `a58c71d904ef`.
- Migrations: `a58c71d904ef` is the additive sole head and has not been applied in this final session because the retained isolated MySQL data files are not writable. Previous successful Stage 02 real-MySQL 8.4.10/InnoDB and agent-to-API-to-MySQL vertical evidence remains recorded above. No production database was accessed.
- Tests executed: focused Stage 05 tests 38 passed; final server suite 241 passed, 33 MySQL-dependent tests skipped, 0 failed; Ruff check/format passed; strict mypy passed for 39 source files; migration history and diff check passed.
- Security implications: SMS recipients are validated server-controlled E.164 configuration, destinations are hashed in queue uniqueness fields, no vendor credentials or network adapter were added, provider failures are isolated per channel, and stable delivery UUIDs are retained for provider idempotency correlation.
- Known limitations: fresh Stage 03–05 MySQL migration/concurrency/lifecycle verification, production Google OIDC credentials, real browser/HTTPS/Caddy behavior, Linux/systemd, real NVIDIA hardware, real SMTP/SMS delivery and soak validation remain environment-specific pending. No SMS vendor has been selected.
- Next stage: Stage 06 - Deployment + Production Hardening. Do not begin it in this session.
- Worktree: dirty/uncommitted by request, containing the accepted Stage 05 implementation and status checkpoint.

## Resume Command / Guidance

Read AGENTS.md, this file, the Stage 06 section of `docs/IMPLEMENTATION_PLAN.md`, and the deployment/security specifications. Inspect the current Git diff and existing deployment assets before continuing. Production operations remain separately gated.
