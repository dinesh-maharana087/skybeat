# SkyBeat V1 Implementation Status

Last updated: 2026-09-23
Current stage: Stage 07 - Dashboard, Operational Visibility & Deployment Runbook
Current milestone: Stage 07.4 - Operational Device Detail
Status: IN PROGRESS. Stage 07.4 is COMPLETE / ACCEPTED; Stage 07.5 history visualization has not started.

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
- Completed Stage 06 Compose deployment artifacts: non-root read-only API/worker image, MySQL 8.4 persistent volume and health check, Caddy-only 80/443 publication, private API/worker/MySQL ports, log rotation, and an explicit profile-gated migration service that never runs at API/worker startup.
- Added fresh-volume-only bootstrap of the distinct scoped MySQL migration account, with explicit documentation that retained volumes require approved operator provisioning rather than reset/reinitialization.
- Added the Stage 06 operator runbook, production checklist, agent systemd unit/configuration template, deployment artifact validator, production configuration rejection of placeholders/weak session keys/unsafe timing, and independent two-second notification polling.
- Completed Stage 07.1 deployment baseline: a dedicated deployment runbook, active agent-path standardization to `/opt/skybeat`, a root-operated idempotent installer that accepts only a source directory and protected environment file, and static safety validation.
- Completed Stage 07.2 bounded dashboard read APIs: canonical overview counts, effective-GPU filtered device keyset pagination, display-safe device/detail additions, durable incident projections, and capped server-side heartbeat history. No monitoring lifecycle or schema behavior changed.
- Completed Stage 07.3 operational dashboard UI: server-rendered semantic overview/project/filter/table sections, Stage 07.2-backed safe DOM rendering, opaque keyset pagination, non-overlapping visibility-aware polling, explicit refresh-stale/partial-error states, and responsive accessible presentation. Stage 07.2 API semantics remain unchanged.
- Completed Stage 07.4 operational device detail: bounded server-side per-device incident filtering; an accessible, responsive canonical-detail drawer; safe structured rendering of identity, freshness, system, storage, GPU inventory, expected policy, and recent incidents; request abort/generation race control; and retained stale detail on refresh failure. It uses 20 recent incidents without changing the endpoint default or maximum.

## In Progress

- Stage 07 remains IN PROGRESS. Stages 07.1 through 07.4 are complete. Stage 07.5 history visualization remains explicitly not started.

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
- Stage 06 focused configuration/availability/worker/deployment-artifact tests: 38 passed. Full server suite: 248 passed, 33 real-MySQL-dependent tests skipped, 0 failed; the only warnings were upstream FastAPI/Starlette/Authlib deprecations.
- Stage 06 full agent suite: 64 passed, 0 failed, 0 skipped. Server Ruff check/format passed (73 files); agent Ruff check/format passed (19 files). Strict mypy passed for 39 server source files and 11 agent source files using dedicated writable workspace caches because the default Windows cache path is ACL-restricted.
- Stage 06 Alembic graph verification: sole head `a58c71d904ef`; complete linear history from `614a53a9e2cb`. `python scripts/validate_deployment.py` passed and `git diff --check` passed without whitespace errors.
- Operator-supplied Stage 06 acceptance evidence: an Ubuntu agent on an NVIDIA GeForce RTX 5080 (driver 595.84; CUDA 13.2 reported by `nvidia-smi`) installed under `/opt/skybeat` successfully sent HTTPS heartbeats through Caddy, FastAPI, and MySQL. Current device/latest/receipt/sample data showed ONLINE, GPU OK, CPU, memory, hostname, and GPU-summary telemetry. This report contains no credentials, tokens, private addresses, or raw telemetry and is distinct from local executable verification.
- Stage 07.1 focused deployment artifact/status tests: final fresh run passed (7 passed, 2 Bash-execution checks skipped because Bash is unavailable on this Windows host). Full server suite: 253 passed, 35 skipped (33 isolated-MySQL-dependent tests plus 2 Bash-unavailable installer tests), 0 failed; upstream FastAPI/Starlette/Authlib deprecation warnings remain. Full agent suite: 64 passed, 0 skipped, 0 failed.
- Stage 07.1 static verification: server Ruff/format passed (73 files) and strict mypy passed for 39 source files; agent Ruff/format passed (19 files) and strict mypy passed for 11 source files. Alembic `heads`/`history` confirms sole head `a58c71d904ef`; deployment validator and `git diff --check` passed.
- Stage 07.2 focused dashboard read/API/page tests passed (19 passed). Full server suite passed (264 passed, 35 skipped, 0 failed): 33 skips require the unavailable isolated MySQL URL and 2 require unavailable Bash. Full agent suite passed (64 passed, 0 skipped, 0 failed). Server Ruff/format passed (74 files) and strict mypy passed for 39 source files; agent Ruff/format passed (19 files) and strict mypy passed for 11 source files. Alembic `heads`/`history` confirms sole head `a58c71d904ef`; deployment validator and `git diff --check` passed.
- Stage 07.3 focused dashboard page/UI plus Stage 07.2 API/read regression tests: 23 passed. Final server suite: 268 passed, 35 skipped, 0 failed; 33 skips require the unavailable isolated MySQL URL and 2 require unavailable Bash. Server Ruff, formatting, and strict mypy passed for 39 source files; Alembic `heads`/`history` confirms sole head `a58c71d904ef`; deployment validation and `git diff --check` passed. The agent suite was not rerun because this stage changed only server dashboard template/static/test assets and no agent code, heartbeat contract, shared API schema, or deployment artifact.
- Stage 07.4 focused dashboard page/API/read regression tests: 30 passed, 0 failed (three upstream FastAPI/Starlette/Authlib deprecation warnings only). Final server suite: 275 passed, 35 skipped, 0 failed; 33 skips require the unavailable isolated MySQL URL and 2 require unavailable Bash. Ruff check passed; formatting check passed (74 files); strict mypy passed for 39 source files; Alembic `heads`/`history` confirms sole head `a58c71d904ef`; deployment validation and `git diff --check` passed. The agent suite was not rerun because this stage changed only dashboard server/read/template/static/test/documentation files and no agent code, heartbeat contract, or deployment artifact.

## Verification Pending

- The retained isolated MySQL instance could not be started in this final session because its existing data files are not writable. ACLs, retained data, initialization and reset were deliberately left untouched. The prior successful real-MySQL 8.4.10/InnoDB evidence above remains the accepted Stage 02 database/vertical verification; a fresh repeat is environment-specific pending.
- Stage 03 real-MySQL migration, availability race, incident deduplication, delivery claiming and rollback verification are pending only because that retained instance cannot safely start. The tests are present; no substitute is treated as proof of MySQL behavior.
- Stage 04 real-MySQL migration and durable OAuth-transaction/session lifecycle verification are pending only because that retained instance cannot safely start. The tests are present; fake OIDC tests validate the application boundary but are not represented as real-Google or real-MySQL evidence.
- Stage 05 real-MySQL migration, GPU incident/event/delivery lifecycle, offline supersession, and independent EMAIL/SMS retry tests are present but pending only because that retained instance cannot safely start. The retained data, ACLs and initialization state were not modified.
- Linux host/systemd behavior, real NVIDIA hardware/driver behavior, actual HTTPS proxy/network transport, load/soak testing and production deployment remain unverified.
- Stage 06 Docker image build/run, Compose rendering/network isolation/volume/log behavior, Caddy configuration/TLS/DNS/firewall behavior, Linux systemd sandbox compatibility, backup restore, and production smoke/load/soak verification remain environment-pending because Docker/Compose and Linux production infrastructure are unavailable locally.
- Stage 07.1 Bash syntax validation and rejected-input execution tests remain environment-pending because this Windows host has no Bash. The installer itself was not run with valid inputs, so no user/service/directory/configuration change occurred. Linux systemd installation remains a real-host verification item.
- Stage 07.2 real-MySQL query execution for overview aggregation, keyset pagination, incident ordering, and bounded heartbeat-history reads remains environment-pending because the retained isolated MySQL data files are not writable. No ACL, data, initialization, or reset action was taken.
- Stage 07.3 browser-level interaction validation remains environment-pending because this Windows environment has no browser/JavaScript runtime test harness. Static page/UI tests cover the existing repository testing model; no browser framework was added solely for this stage.
- Stage 07.4 browser-level drawer interaction, responsive-layout, and real-MySQL filtered-query execution remain environment-pending because this Windows environment has no browser/JavaScript runtime harness and the retained isolated MySQL data files are not writable. Static and service-level tests cover the implemented bounded/read-only contract; no browser framework, ACL, data, initialization, or reset action was added.

## Files Changed

- `docs/IMPLEMENTATION_STATUS.md`
- `server/app/api/heartbeats.py`, `server/app/heartbeats/`, `server/app/schemas/heartbeat.py`, `server/app/models/heartbeat.py`
- `server/app/models/__init__.py`, `server/app/devices/service.py`, `server/app/main.py`
- `server/migrations/versions/1b2785bb39ef_heartbeat_storage.py`, `server/tests/`
- `agent/pyproject.toml`, `agent/requirements.lock`, `agent/src/`, `agent/tests/`
- Stage 03: `server/app/health/`, `server/app/notifications/`, `server/app/worker.py`, `server/app/models/alerts.py`, heartbeat/configuration integration, migration `625bfa1677df`, focused Stage 03 tests, `.env.example`, and `server/pyproject.toml`.
- Stage 04: `server/app/dashboard/`, `server/app/api/auth.py`, `server/app/api/dashboard.py`, `server/app/api/dashboard_page.py`, `server/app/templates/`, `server/app/static/`, authentication/read integration in `server/app/main.py`, additive migration `7d2e8a91c4bf`, configuration/dependency updates, `.env.example`, and focused dashboard tests.
- Stage 05: `.env.example`, `server/app/gpu/`, GPU state model and heartbeat/availability/dashboard integration, notification worker/email routing, provider-neutral SMS adapter, additive migration `a58c71d904ef`, and focused GPU/SMS lifecycle tests.
- Stage 06: `docker-compose.yml`, `deployment/docker/Dockerfile.server`, `deployment/caddy/Caddyfile`, `deployment/mysql/01-create-migration-user.sh`, `deployment/systemd/`, `deployment/production.env.example`, `scripts/validate_deployment.py`, `docs/PRODUCTION_CHECKLIST.md`, deployment/readme documentation, configuration/availability/heartbeat/worker integration, and focused deployment tests.
- Stage 07.1: `docs/DEPLOYMENT_RUNBOOK.md`, active agent installation references in `AGENTS.md`, `docs/AGENT_SPEC.md`, and `docs/DEPLOYMENT.md`, `deployment/systemd/skybeat-agent.service`, `scripts/install-agent.sh`, deployment validator/static tests, and this checkpoint.
- Stage 07.2: `server/app/dashboard/read.py`, `server/app/api/dashboard.py`, dashboard read/API tests, `docs/API_SPEC.md`, and this checkpoint.
- Stage 07.3: `server/app/templates/dashboard.html`, `server/app/static/dashboard.js`, `server/app/static/dashboard.css`, focused dashboard page tests, and this checkpoint.
- Stage 07.4: `server/app/dashboard/read.py`, `server/app/api/dashboard.py`, `server/app/templates/dashboard.html`, `server/app/static/dashboard.js`, `server/app/static/dashboard.css`, dashboard API/read/page tests, `docs/API_SPEC.md`, and this checkpoint.

## Migrations Applied/Tested

- Stage 01 revision `614a53a9e2cb` remains applied to isolated local `skybeat_test` on MySQL 8.4.10/InnoDB.
- Additive Stage 02 revision `1b2785bb39ef` applied successfully to that same isolated database and exercised by real-MySQL tests. It creates `heartbeat_receipts`, `heartbeat_samples` and `device_latest`.
- Additive Stage 03 revision `625bfa1677df` is the current Alembic head and chains from `1b2785bb39ef`; it has not been applied in this session because the retained isolated MySQL data files are not writable.
- Additive Stage 04 revision `7d2e8a91c4bf` chains from `625bfa1677df` and is the current Alembic head. It creates `admin_sessions` and `oauth_transactions`; it has not been applied in this session because the retained isolated MySQL data files are not writable.
- Additive Stage 05 revision `a58c71d904ef` chains from `7d2e8a91c4bf` and is the sole Alembic head. It adds durable device GPU confirmation state; its real-MySQL application is environment-pending because the retained data files are not writable.
- Stage 06 requires no schema change and adds no Alembic revision. Fresh Alembic `heads`/`history` verification confirms `a58c71d904ef` remains the sole linear head.
- Stage 07.1 adds no schema change or Alembic revision; `a58c71d904ef` remains the verified sole head.
- Stage 07.2 adds no schema change or Alembic revision; it uses the existing `heartbeat_samples(device_id, received_at)` index and `a58c71d904ef` remains the verified sole head.
- Stage 07.3 adds no schema change or Alembic revision; `a58c71d904ef` remains the verified sole head.
- Stage 07.4 adds no schema change or Alembic revision; `a58c71d904ef` remains the verified sole head.
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
- No Stage 06 software acceptance blockers remain. Docker/Compose/Caddy/Linux/backup execution and MySQL migration application are environment-specific operational verification, not fabricated as local evidence.
- No Stage 07.1 software acceptance blockers remain. Bash/systemd runtime execution is environment-pending; Stage 07 remains in progress pending explicitly deferred dashboard work.
- No Stage 07.2 software acceptance blockers remain. Real-MySQL execution is environment-pending; Stage 07 remains in progress pending explicitly deferred dashboard UI work.
- No Stage 07.3 software acceptance blockers remain. Browser-level interaction testing is environment-pending; Stage 07 remains in progress pending explicitly deferred device detail and history visualization work.
- No Stage 07.4 software acceptance blockers remain. Browser-level drawer interaction and real-MySQL execution are environment-pending; Stage 07 remains in progress pending explicitly deferred Stage 07.5 history visualization.

## Security Notes

- No production access, deployment, notifications, credential rotation or destructive operation was performed.
- Payloads are strict/bounded and do not echo secrets. Credentials are revalidated on retries before returning stored acknowledgements.
- A valid credential with a different payload device UUID returns 403 and cannot retrieve an acknowledgement.
- Agent transport does not place credentials in URLs and does not disable TLS verification. GPU collection uses a fixed `nvidia-smi` argument list through `asyncio.create_subprocess_exec`.
- Dashboard authentication uses Authlib validation rather than manually decoding JWTs. Google tokens are not persisted; only hashes of browser session/state/binding values and encrypted nonce/PKCE material are stored. Dashboard responses use `no-store`, the UI inserts dynamic values with `textContent`, and logout checks same-origin headers in addition to SameSite cookies.
- Stage 06 keeps API/worker containers non-root and read-only, avoids automatic migrations, does not publish MySQL/API ports, bounds the Caddy request body to 128 KiB, rejects production placeholder/weak secrets, and does not trust arbitrary forwarded headers.
- Stage 07.1 installer rejects token/credential/secret options, requires root only after safe input validation, never reads or prints the protected environment file, installs it root-owned mode 0600, and keeps the running agent under `skybeat`. The runbook preserves mandatory TLS verification and treats private-CA trust only as a development/LAN procedure.
- Stage 07.2 endpoints require the existing dashboard session dependency, use no-store responses, validate bounded inputs/cursors, expose projections rather than ORM records, and omit credentials, sessions, token digests, notification destinations, and provider data.
- Stage 07.3 preserves same-origin requests, no-store API behavior, opaque cursors, text-only DOM insertion, restrictive CSP compatibility, and browser-session isolation. It does not put credentials/session data into browser storage or derive monitoring states in JavaScript.
- Stage 07.4 validates the optional canonical incident UUID server-side and filters before pagination; it preserves dashboard authorization/no-store responses and exposes only existing incident projections. The drawer uses same-origin requests, `AbortController` plus request generations, `textContent`/DOM construction only, no browser credential storage, and no client-derived availability or GPU state.

## Environment Limitations

- Windows PowerShell workspace; use `.venv/Scripts/python.exe`.
- Portable MySQL and isolated credentials remain ignored under `.tools/` and `.test-data/`; the unrelated local MySQL service on port 3306 was untouched.
- Windows cache ACLs require Ruff `--no-cache` and mypy temporary-system cache directories.
- Agent tests use controlled fixtures on Windows. No actual Linux systemd service, NVIDIA device, Caddy TLS endpoint or external network was exercised.
- The retained isolated MySQL data files are not writable in this environment, preventing startup. Their ACLs and contents were not changed, and MySQL was not reset or reinitialized.
- Docker CLI/Compose is unavailable on this Windows environment; no image build, container, proxy, volume, or Caddy runtime check was attempted through an alternative or destructive path.

## Next Action

- Stage 07.4 is COMPLETE / ACCEPTED. Do not begin Stage 07.5 history visualization without separate authorization; preserve `Local MySQL.session.sql` and leave the retained MySQL data directory untouched unless separately authorized.

## Latest Stage Completion

- Stage: 07.4 - Operational Device Detail.
- Status: COMPLETE / ACCEPTED.
- Files changed: bounded incident read/API extension, dashboard template/static drawer, API/read/page tests, API specification, and this checkpoint. Existing availability/GPU/heartbeat/incident lifecycle and database schema behavior were not changed.
- Migrations: no Stage 07.4 revision is required. `a58c71d904ef` remains the existing sole Alembic head; no database operation occurred.
- Tests executed: focused Stage 07.4 suite 30 passed; full server suite 275 passed, 35 environment-dependent skips; Ruff check, format check, strict mypy, Alembic heads/history, deployment validator, and diff check passed. Agent verification was not rerun because this stage changed no agent/shared-contract/deployment file.
- Security implications: server-authoritative availability/GPU values remain text-only DOM output; the optional incident filter is authenticated, validated, bounded, and applied before pagination. No browser storage, unsafe dynamic HTML, external script, session/credential exposure, chart/history endpoint, or Stage 07.5 implementation was added.
- Known limitations: real-MySQL execution, Bash/systemd, Docker/Compose, Linux, Caddy, real hardware, browser-level UI interaction execution, and production integration remain environment-pending as separately documented. No data or ACL was changed to make any check pass.
- Next stage: Stage 07.5 history visualization is explicitly not started and requires separate authorization.
- Worktree: uncommitted Stage 07.4 implementation/documentation/test changes; no commit was created by request.

## Resume Command / Guidance

Stage 07.4 is accepted. Stop before Stage 07.5 unless the user supplies separate authorization. Any production operation remains separately gated.
