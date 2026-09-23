# Deployment and Operations Design

Status: approved V1 deployment baseline.

This document defines the deployment and operational model for the standalone SkyBeat monitoring platform.

V1 targets:

* one central Ubuntu 24.04 LTS VM
* up to approximately 100 Linux monitoring agents
* Python 3.12
* FastAPI
* SQLAlchemy 2
* Alembic
* Pydantic 2
* MySQL 8.x / InnoDB
* Docker Engine + Docker Compose
* Caddy
* direct systemd deployment for agents

The deployment should remain simple enough to install, operate, troubleshoot, back up, and restore without requiring a distributed infrastructure platform.

---

# 1. Deployment Architecture

Central deployment:

```text
Internet / Edge Devices
          │
          │ HTTPS :443
          ▼
       Caddy
          │
          ▼
       FastAPI
          │
          ▼
       MySQL 8.x
          ▲
          │
        Worker
          │
          ├── SMTP
          └── SMS Provider
```

Edge deployment:

```text
Linux / GPU Device
        │
        └── skybeat-agent.service
                │
                └── HTTPS → Central Server
```

---

# 2. Central VM

Recommended operating system:

```text
Ubuntu 24.04 LTS
```

Initial VM sizing:

```text
CPU:
2–4 vCPU

Memory:
4–8 GB RAM

Storage:
80+ GB SSD
```

This is a starting point, not a permanent capacity guarantee.

Actual sizing must be verified from:

* heartbeat payload size
* MySQL storage growth
* index growth
* retention cleanup
* notification backlog
* Docker logs
* backups
* real fleet behavior

---

# 3. Why One VM

V1 intentionally uses one central VM.

At:

```text
100 devices
×
1 heartbeat / 30 seconds
```

normal ingestion is approximately:

```text
3.33 requests/second
```

This does not justify:

* Kubernetes
* Kafka
* RabbitMQ
* Redis
* Celery
* microservices
* distributed databases
* separate frontend servers

The priority is operational reliability with minimum infrastructure complexity.

---

# 4. Docker Compose

Central services run through Docker Compose.

Required services:

```text
proxy

api

worker

mysql
```

Optional operational job:

```text
migrate
```

Conceptually:

```text
docker-compose.yml

services:
    proxy
    api
    worker
    mysql
```

The API and worker use the same server application image with different entry points.

---

# 5. Service Responsibilities

| Service   | Responsibility                                          |
| --------- | ------------------------------------------------------- |
| `proxy`   | HTTPS/TLS and reverse proxy                             |
| `api`     | Heartbeat ingestion, dashboard, Google authentication   |
| `worker`  | Availability sweep, incidents, notifications, retention |
| `mysql`   | Authoritative persistent database                       |
| `migrate` | Controlled Alembic migration execution                  |

---

# 6. Network Layout

Recommended logical networks:

```text
front

data
```

Conceptually:

```text
Internet
    │
    ▼
 Caddy
    │
  front
    │
    ▼
FastAPI
    │
  data
    │
    ▼
 MySQL

Worker
    │
  data
    │
    ▼
 MySQL
```

The API and worker also require outbound connectivity for approved external dependencies.

Examples:

API:

* Google OIDC endpoints
* DNS
* time synchronization through host infrastructure

Worker:

* SMTP server
* SMS provider
* DNS

---

# 7. Public Ports

Externally exposed:

```text
443/tcp
```

Optionally:

```text
80/tcp
```

for:

* HTTP → HTTPS redirect
* ACME certificate validation where required

Do NOT publicly expose:

```text
3306 MySQL

8000 FastAPI

worker ports

Docker API

debug endpoints
```

---

# 8. Firewall

At the VM/cloud firewall level:

Allow:

```text
443/tcp
```

Optionally:

```text
80/tcp
```

Restrict:

```text
22/tcp
```

to approved operator sources where practical.

Block external access to:

```text
3306

8000

other internal service ports
```

Docker configuration alone is not the only security boundary.

Host/cloud firewall rules must also enforce exposure policy.

---

# 9. DNS

Production requires one operator-controlled hostname.

Example:

```text
monitor.example.com
```

DNS:

```text
monitor.example.com
        ↓
Central VM public IP
```

Do not use temporary/example hostnames for production.

The same hostname is used for:

* agent heartbeat URL
* dashboard
* Google OAuth callback
* TLS certificate

---

# 10. Caddy

Caddy is the preferred V1 reverse proxy.

Responsibilities:

```text
TLS certificate issuance

TLS renewal

HTTP → HTTPS redirect

request forwarding

host validation

basic request-size protection
```

Conceptually:

```text
monitor.example.com {
    reverse_proxy api:8000
}
```

The final Caddyfile must also enforce the request/security requirements from `SECURITY.md`.

---

# 11. HTTPS

Production traffic must use:

```text
HTTPS
```

Agents must never automatically fall back to HTTP.

Dashboard authentication must never run over plaintext HTTP.

Caddy certificate storage must persist across container recreation.

---

# 12. MySQL

Database:

```text
MySQL 8.x
```

Storage engine:

```text
InnoDB
```

Character set:

```text
utf8mb4
```

Timezone:

```text
UTC
```

MySQL is the authoritative source for:

* projects
* devices
* credentials
* heartbeats
* latest telemetry
* availability
* GPU health
* incidents
* events
* notification jobs
* sessions
* audit events

---

# 13. MySQL Exposure

MySQL must remain private.

Do NOT publish:

```text
3306:3306
```

to the public host interface.

API and worker connect over the internal Docker network.

Operator database access should use controlled local access or another explicitly approved administrative method.

---

# 14. MySQL Persistence

MySQL requires a persistent Docker volume.

Conceptually:

```text
volumes:
    mysql_data:
```

Container deletion/recreation must not remove database data.

Never use:

```text
docker compose down -v
```

as a normal operational command.

Removing the database volume is destructive.

---

# 15. Database Roles

Use separate MySQL accounts where practical.

Recommended:

```text
skybeat_runtime

skybeat_migration

skybeat_backup
```

`skybeat_runtime` is used by:

```text
api

worker
```

It should have only required application privileges.

`skybeat_migration` is used only for Alembic migrations.

`skybeat_backup` is used only for backups where a dedicated backup account is practical.

Do not run the application using:

```text
root
```

or an unrestricted MySQL administrative account.

---

# 16. Database URL

Runtime configuration:

```text
SKYBEAT_DATABASE_URL
```

Example conceptual format:

```text
mysql+pymysql://skybeat_runtime:<password>@mysql:3306/skybeat
```

The exact SQLAlchemy MySQL driver is selected and pinned during implementation.

Do not place real database credentials in documentation or Git.

---

# 17. MySQL Connection Pool

Initial per-process starting point:

```text
pool size:
5

max overflow:
5
```

This is adequate for the initial fleet.

Pool sizing must remain below MySQL connection capacity across:

```text
API
+
worker
+
migration/admin activity
```

Do not create one database connection per device.

---

# 18. Database Timeouts

Use bounded:

```text
connect timeout

pool acquisition timeout

lock wait timeout
```

Initial conceptual targets:

```text
connect:
3 seconds

pool:
2 seconds

runtime lock wait:
approximately 1–3 seconds
```

Exact MySQL/session settings must be tested.

No request should wait indefinitely for a database connection or row lock.

---

# 19. MySQL UTC Configuration

All application timestamps are treated as UTC.

At startup:

* verify MySQL/session timezone
* configure application sessions consistently
* store `DATETIME(6)` values as UTC
* convert to display timezone only at presentation boundaries

Availability calculations must not depend on local VM timezone.

---

# 20. Alembic

All schema changes use:

```text
Alembic
```

The API and worker must not automatically create/modify schema during normal startup.

Deployment sequence:

```text
MySQL
   ↓
Migration
   ↓
API
   ↓
Worker
   ↓
Caddy
```

Migration failure stops the release.

---

# 21. Migration Workflow

For a release:

```text
1. Back up database

2. Pull/build approved application version

3. Run Alembic migration

4. Verify migration success

5. Start/restart API

6. Start/restart worker

7. Verify readiness

8. Verify heartbeat

9. Verify dashboard
```

Never solve migration failure by deleting tables or resetting the database.

---

# 22. API Process

FastAPI runs inside the application container.

Initial configuration:

```text
1 API process
```

This is sufficient for the expected heartbeat rate.

Increase process count only after measurement demonstrates a need.

The API listens internally on approximately:

```text
0.0.0.0:8000
```

but the host must not publish that port publicly.

---

# 23. Worker Process

Worker runs separately from FastAPI.

Responsibilities:

```text
availability sweep

incident/event creation

notification delivery

retry handling

retention cleanup

worker progress tracking
```

This separation prevents:

```text
SMTP delay
```

from blocking:

```text
heartbeat requests
```

---

# 24. Worker Failure

If worker stops:

```text
heartbeat ingestion continues
```

but:

```text
availability transitions may be delayed

notifications may be delayed

retention cleanup pauses
```

After restart, the worker resumes from persisted MySQL state.

Do not rely on in-memory worker state for correctness.

---

# 25. Worker Sweep

Availability sweep:

```text
every approximately 5 seconds
```

Notification poll:

```text
every approximately 2 seconds
```

Retention cleanup:

```text
approximately hourly
```

These values may be configured.

---

# 26. Health Endpoints

Required:

```text
/livez

/readyz
```

`/livez` answers:

```text
Is the API process alive?
```

`/readyz` answers:

```text
Can the API safely serve application requests?
```

Readiness should include:

* MySQL connectivity
* schema compatibility

Readiness should NOT require:

* SMTP availability
* SMS availability
* Google availability
* every agent being online

External readiness responses must not reveal sensitive topology or credentials.

---

# 27. Worker Health

Worker progress should be persisted or otherwise safely observable.

Useful values:

```text
last_health_sweep_at

last_notification_poll_at

notification backlog
```

Initial stale threshold:

```text
30 seconds
```

A stale worker should be visible to operators.

---

# 28. Environment Configuration

Production configuration is provided through protected environment/secret files.

Do not hard-code production configuration.

Root `.env.example` contains:

```text
variable names

safe placeholders

non-secret defaults
```

Never include actual secrets.

---

# 29. Core Server Variables

Required or commonly used:

```text
SKYBEAT_ENV

SKYBEAT_PUBLIC_BASE_URL

SKYBEAT_DATABASE_URL

SKYBEAT_ALLOWED_HOSTS

SKYBEAT_SUSPECT_AFTER_SECONDS

SKYBEAT_OFFLINE_AFTER_SECONDS

SKYBEAT_HEALTH_SWEEP_SECONDS

SKYBEAT_LOG_LEVEL
```

Recommended defaults:

```text
SKYBEAT_SUSPECT_AFTER_SECONDS=75

SKYBEAT_OFFLINE_AFTER_SECONDS=180

SKYBEAT_HEALTH_SWEEP_SECONDS=5

SKYBEAT_LOG_LEVEL=INFO
```

---

# 30. API Limits

Initial:

```text
SKYBEAT_MAX_BODY_BYTES=131072

SKYBEAT_MAX_GPUS=64

SKYBEAT_MAX_DISKS=64

SKYBEAT_MAX_IPS=16
```

Heartbeat request deadline:

```text
approximately 10 seconds
```

Application/database work should normally complete much faster.

---

# 31. Dashboard Variables

When dashboard is enabled:

```text
SKYBEAT_GOOGLE_CLIENT_ID

SKYBEAT_GOOGLE_CLIENT_SECRET

SKYBEAT_GOOGLE_REDIRECT_URI

SKYBEAT_ADMIN_EMAIL_ALLOWLIST
```

Optional:

```text
SKYBEAT_ADMIN_DOMAIN_ALLOWLIST
```

An empty authorization policy must deny access.

---

# 32. Google Redirect

Conceptual callback:

```text
https://monitor.example.com/auth/google/callback
```

The configured Google callback must exactly match the application configuration.

Do not use:

```text
http://
```

for the production callback.

---

# 33. Dashboard Polling

Initial dashboard refresh:

```text
15 seconds
```

No WebSocket infrastructure is required for V1.

If polling fails, the dashboard must show:

```text
data unavailable/stale
```

rather than silently continuing to present old information as current.

---

# 34. Email Configuration

When enabled:

```text
SKYBEAT_EMAIL_ENABLED=true

SKYBEAT_EMAIL_RECIPIENTS

SKYBEAT_SMTP_HOST

SKYBEAT_SMTP_PORT

SKYBEAT_SMTP_USERNAME

SKYBEAT_SMTP_PASSWORD

SKYBEAT_SMTP_FROM
```

Prefer:

```text
STARTTLS
```

or provider-supported implicit TLS.

Never silently fall back to plaintext SMTP.

---

# 35. SMS Configuration

SMS remains provider-independent.

Conceptually:

```text
SKYBEAT_SMS_ENABLED

SKYBEAT_SMS_PROVIDER

SKYBEAT_SMS_RECIPIENTS
```

Provider-specific credentials are added only after selecting the provider.

Examples may include:

```text
API token

account ID

sender ID

template ID
```

The core incident engine must not depend on one specific SMS vendor.

---

# 36. Notification Defaults

Initial:

```text
poll:
2 seconds

concurrency:
4

attempt timeout:
15 seconds

maximum attempts:
5

retry base:
30 seconds

retry maximum:
900 seconds

expiry:
86400 seconds
```

These align with `ALERTING.md`.

---

# 37. Notification Provider Isolation

SMTP and SMS failures must not affect:

```text
heartbeat ingestion

MySQL telemetry persistence

availability detection

dashboard access
```

Providers are called only by the worker after durable event/delivery creation.

---

# 38. Telemetry Retention

Initial raw heartbeat retention:

```text
7 days
```

At:

```text
100 devices
30-second heartbeat
```

this produces approximately:

```text
288,000 heartbeat samples/day

2,016,000 heartbeat samples/7 days
```

Actual storage must be measured.

The original deployment estimate correctly shows that raw payload storage alone can become significant even though request throughput is low.

---

# 39. Event Retention

Initial:

```text
incidents:
90 days

alert events:
90 days

notification history:
90 days

audit events:
90 days minimum
```

Active incidents and unfinished notification jobs must not be removed by retention cleanup.

---

# 40. Retention Cleanup

Cleanup should run in bounded batches.

Initial:

```text
batch size:
1000 rows
```

Do not execute massive unbounded deletes during normal production operation.

Cleanup should:

1. select old terminal data
2. delete a bounded batch
3. commit
4. continue later

MySQL maintenance should be measured from actual table/index behavior rather than copying PostgreSQL vacuum assumptions.

---

# 41. Docker Logging

Use bounded Docker log rotation.

Suggested:

```text
max-size:
10m

max-file:
5
```

Application logs should use structured output.

Production default:

```text
INFO
```

Do not enable payload-heavy DEBUG logging by default.

---

# 42. Agent Deployment

Agents do NOT require Docker.

Deploy directly using:

```text
Python virtual environment

systemd
```

Recommended:

```text
/opt/skybeat-agent/

/etc/skybeat-agent/agent.env

/etc/systemd/system/skybeat-agent.service
```

---

# 43. Agent Runtime User

Create:

```text
skybeat
```

as a dedicated system account.

The account should:

* have no interactive login where practical
* have no sudo access
* have no Docker socket access
* have only required telemetry/GPU permissions

---

# 44. Agent Configuration

Configuration:

```text
/etc/skybeat-agent/agent.env
```

Required:

```text
SKYBEAT_SERVER_URL

SKYBEAT_DEVICE_ID

SKYBEAT_DEVICE_TOKEN
```

Recommended ownership:

```text
root:root
```

Recommended permissions:

```text
0600
```

---

# 45. Agent systemd Service

Conceptual baseline:

```ini
[Unit]
Description=SkyBeat Device Monitoring Agent
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=skybeat
Group=skybeat
EnvironmentFile=/etc/skybeat-agent/agent.env
ExecStart=/opt/skybeat-agent/venv/bin/python -m skybeat_agent.main
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
UMask=0077

[Install]
WantedBy=multi-user.target
```

Additional hardening is added only after confirming NVIDIA/system telemetry remains accessible.

---

# 46. Agent Installation

Conceptually:

```text
1. Create device on server

2. Obtain UUID + credential

3. Create skybeat user

4. Install Python/agent

5. Create virtual environment

6. Install pinned dependencies

7. Write agent.env

8. Install systemd service

9. daemon-reload

10. enable/start service

11. verify logs

12. verify dashboard heartbeat
```

---

# 47. Agent Upgrade

Use controlled upgrades.

Recommended:

```text
1. Test new version on one device

2. Confirm heartbeat

3. Confirm GPU telemetry

4. Confirm restart

5. Confirm boot startup

6. Roll out to additional devices
```

Do not update all production agents simultaneously without a successful canary.

---

# 48. Agent Rollback

Keep the previous compatible package/version available during rollout.

If a new agent fails:

```text
stop service

restore previous compatible agent

restart service

verify heartbeat
```

Do not change the heartbeat schema incompatibly without server support.

---

# 49. Server Upgrade

Before server upgrade:

```text
backup database

record current application version

record current migration revision

verify backup completed
```

Then:

```text
pull/build release

run migrations

restart API/worker

verify health

verify heartbeat

verify dashboard

verify notification worker
```

---

# 50. Server Rollback

Application rollback is allowed only when the previous application remains compatible with the migrated schema.

Do not automatically downgrade database migrations.

If a migration is destructive or incompatible, deployment requires a specific rollback/recovery plan before release.

---

# 51. MySQL Backup

Use a MySQL-compatible backup mechanism.

For the initial deployment, a logical backup such as:

```text
mysqldump
```

is acceptable.

Backup must include the SkyBeat database schema and data required for recovery.

Backups must be stored outside the live MySQL Docker volume.

---

# 52. Backup Schedule

Initial proposal:

```text
daily backup
```

Retention:

```text
30 days
```

Target:

```text
RPO <= 24 hours
```

Backups should be copied off the central VM.

A backup existing on the same disk as the production database is not sufficient disaster recovery.

---

# 53. Backup Security

Backups contain sensitive operational information.

Protect them with:

* restricted access
* encrypted transport
* encrypted storage where available
* independent credentials

Do not embed storage credentials directly in backup filenames/scripts.

---

# 54. Backup Verification

A backup is not considered proven merely because:

```text
mysqldump exited 0
```

Periodically verify:

* file exists
* file is non-empty
* expected database objects are present
* backup can be restored

Restore testing is mandatory before claiming production recovery readiness.

---

# 55. Restore Procedure

Restore into an isolated environment first.

Conceptually:

```text
1. Prepare replacement MySQL

2. Restore backup

3. Verify schema revision

4. Verify projects/devices

5. Verify incidents/events

6. Start API with notifications disabled

7. Verify dashboard

8. Verify heartbeat ingestion

9. Reconcile credentials/sessions

10. Enable worker

11. Perform controlled outage/recovery test
```

Never automatically overwrite a running production database during recovery.

---

# 56. Security-Sensitive Restore

A restored backup may contain:

```text
old active sessions

old credential state

old authorization state

old notification jobs
```

After restore:

* invalidate dashboard sessions
* reconcile known credential revocations
* review pending notification jobs
* verify administrator allowlist
* verify provider configuration

Do this before reopening public access.

---

# 57. Initial Recovery Targets

Proposed:

```text
RPO:
24 hours

RTO:
4 hours
```

These are initial operational targets.

They must eventually be validated through an actual restore exercise.

---

# 58. Central VM Blind Spot

The monitoring VM cannot reliably detect its own total failure.

If the VM is down:

```text
agents cannot reach it

health worker cannot run

email/SMS cannot be generated
```

Therefore production should use an independent external uptime mechanism.

Examples:

```text
cloud VM monitoring

external HTTPS uptime monitor

independent dead-man check
```

This mechanism is outside SkyBeat V1 itself.

---

# 59. Time Synchronization

Central VM and monitored devices should use normal OS time synchronization.

However:

```text
server receipt time
```

remains authoritative for availability.

Agent clock drift must not directly determine OFFLINE state.

---

# 60. Restart Policy

Recommended:

API:

```text
restart: unless-stopped
```

Worker:

```text
restart: unless-stopped
```

MySQL:

```text
restart: unless-stopped
```

Caddy:

```text
restart: unless-stopped
```

Agent:

```text
Restart=on-failure
```

Restart loops must remain visible rather than being hidden by excessive retry noise.

---

# 61. Graceful Shutdown

API:

```text
stop accepting new work

allow bounded in-flight requests to finish

exit
```

Worker:

```text
stop claiming new jobs

allow bounded current work

persist result where possible

exit
```

Initial server application shutdown budget:

```text
20 seconds
```

Compose stop grace:

```text
approximately 30 seconds
```

Agent shutdown budget:

```text
15 seconds
```

---

# 62. MySQL Failure

If MySQL stops:

```text
API readiness → unhealthy

new heartbeat commits fail

worker state processing pauses
```

The API must not acknowledge a heartbeat before durable commit.

Agents receive bounded temporary failures and retry according to `AGENT_SPEC.md`.

After MySQL returns:

```text
API reconnects

worker resumes

new heartbeats continue
```

---

# 63. API Failure

If FastAPI stops:

```text
agents cannot submit heartbeats

dashboard unavailable
```

Agents:

```text
retry with bounded backoff
```

After API recovery:

```text
fresh telemetry resumes
```

No unbounded agent backlog is replayed.

---

# 64. Worker Failure

If worker stops:

```text
API remains available

heartbeats continue

dashboard may show stale health transitions

notifications pause
```

Worker restart resumes from MySQL.

This separation is intentional.

---

# 65. SMTP Failure

If SMTP fails:

```text
email delivery retries
```

while:

```text
heartbeat processing continues

SMS may continue
```

SMTP availability must not affect API readiness.

---

# 66. SMS Failure

If SMS fails:

```text
SMS delivery retries
```

while:

```text
heartbeat processing continues

email may continue
```

SMS availability must not affect API readiness.

---

# 67. Caddy Failure

If Caddy stops:

```text
external API/dashboard unavailable
```

but internal containers may still be healthy.

Restart policy should restore Caddy automatically.

Certificate/configuration errors must remain visible in logs.

---

# 68. Disk Capacity

Monitor central VM disk usage.

MySQL history and backups can consume significant storage.

Operational thresholds should be configured before disk exhaustion.

Example planning thresholds:

```text
warning:
~70–80%

critical:
~85–90%
```

Exact alerting belongs to infrastructure operations.

Do not wait until MySQL fails writes because the filesystem is full.

---

# 69. Docker Disk Usage

Monitor:

```text
docker volumes

container logs

unused images

build cache
```

Do not perform aggressive automated cleanup that could remove required volumes or active artifacts.

Never automatically prune database volumes.

---

# 70. Production Directory

Recommended server checkout:

```text
/opt/skybeat/
```

Conceptually:

```text
/opt/skybeat/
├── docker-compose.yml
├── .env
├── deployment/
└── server/
```

Secrets should have restrictive permissions.

---

# 71. Repository Deployment Files

Expected:

```text
docker-compose.yml

.env.example

deployment/
├── docker/
│   └── Dockerfile.server
├── caddy/
│   └── Caddyfile
└── systemd/
    ├── skybeat-agent.service
    └── agent.env.example
```

Do not commit:

```text
.env

agent.env

credentials

backup keys
```

---

# 72. Production Startup Sequence

Recommended:

```text
1. Verify DNS

2. Verify firewall

3. Verify secret/config files

4. Start MySQL

5. Verify MySQL health

6. Run migrations

7. Start API

8. Verify /livez

9. Verify /readyz

10. Start worker

11. Verify worker progress

12. Start Caddy

13. Verify HTTPS

14. Verify Google login

15. Verify agent heartbeat

16. Verify dashboard

17. Perform controlled alert test
```

---

# 73. First Device Verification

After enrolling the first real device:

Verify:

```text
agent service active

HTTPS works

device authentication works

heartbeat accepted

CPU displayed

RAM displayed

disk displayed

GPU displayed

last seen updates

device appears under correct project
```

Do not enroll the entire fleet until this path is stable.

---

# 74. First Alert Verification

On a designated test device:

```text
stop skybeat-agent
```

Observe:

```text
ONLINE
  ↓
SUSPECT
  ↓
OFFLINE
```

Expected:

```text
one availability incident

one DEVICE_OFFLINE event

one configured notification
```

Restart agent.

Expected:

```text
OFFLINE
  ↓
ONLINE

incident closes

one DEVICE_RECOVERED event

one configured recovery notification
```

---

# 75. GPU Failure Verification

On a controlled test device, simulate or safely test:

```text
nvidia-smi unavailable

nvidia-smi timeout/failure

expected GPU missing
```

Verify:

```text
system heartbeat continues

GPU health changes

availability remains ONLINE while heartbeats continue

GPU confirmation rules are respected
```

Do not deliberately damage or unload production GPU drivers merely to test monitoring.

---

# 76. Production Acceptance Matrix

Required scenarios:

| Scenario                    | Expected result                         |
| --------------------------- | --------------------------------------- |
| Agent stopped               | OFFLINE after threshold, one incident   |
| Agent restarted             | RECOVERED once                          |
| Device reboot               | Agent returns automatically             |
| Network disconnected        | OFFLINE after threshold                 |
| One heartbeat missed        | No false OFFLINE                        |
| API restart                 | Agent retries, telemetry resumes        |
| Worker restart              | Heartbeats continue, processing resumes |
| MySQL restart               | API fails safely, reconnects afterward  |
| SMTP unavailable            | Email retries, monitoring continues     |
| SMS unavailable             | SMS retries, monitoring continues       |
| `nvidia-smi` timeout        | System telemetry continues              |
| GPU missing                 | GPU degradation, device still reachable |
| Central VM reboot           | Persistent data survives                |
| Invalid device token        | Heartbeat rejected                      |
| Unauthorized dashboard user | Access denied                           |
| Backup restore              | System recoverable                      |

---

# 77. 24-Hour Soak Test

Before wider rollout, run the central server and at least one representative GPU device for:

```text
24 hours
```

Observe:

* API memory
* worker memory
* MySQL memory
* MySQL disk growth
* agent memory
* agent CPU
* heartbeat timing
* GPU collection
* notification queue
* Docker logs
* database connections

There should be no unbounded growth.

---

# 78. Load Validation

Before claiming support for 100 devices, simulate representative heartbeat traffic.

Target:

```text
100 devices

approximately 30-second interval
```

Verify:

* heartbeat success rate
* API latency
* MySQL latency
* connection-pool usage
* CPU
* RAM
* disk writes
* worker sweep timing
* no false OFFLINE transitions

This does not require a complicated load-testing platform.

A controlled test script is sufficient for V1.

---

# 79. Production Monitoring

At minimum operators should be able to inspect:

```text
container status

API readiness

worker progress

MySQL health

disk usage

backup age

TLS certificate status

notification failures
```

Useful commands may include:

```text
docker compose ps

docker compose logs

systemctl status skybeat-agent

journalctl -u skybeat-agent
```

Exact commands belong in the operational runbook.

---

# 80. Deployment Day Priority

Because the initial production target is short, deploy in this order:

```text
1. Ubuntu VM

2. Docker + Compose

3. MySQL

4. FastAPI

5. Alembic migration

6. Caddy + HTTPS

7. First agent

8. Heartbeat verification

9. Availability worker

10. Email alerts

11. Dashboard

12. Google authentication

13. SMS adapter

14. GPU alerts

15. Backup

16. Hardening/testing
```

The first goal is not:

```text
complete every optional operational feature
```

The first goal is:

```text
Device
   ↓
HTTPS
   ↓
FastAPI
   ↓
MySQL
   ↓
Dashboard
```

Then:

```text
Device stops
   ↓
OFFLINE
   ↓
Email
```

Then:

```text
Device returns
   ↓
RECOVERED
   ↓
Email
```

---

# 81. Day-1 Milestone

Target:

```text
Central VM running

MySQL running

FastAPI running

HTTPS working

one device enrolled

agent heartbeat stored

telemetry visible
```

If this path is not working, do not spend time on SMS or advanced UI.

---

# 82. Day-2 Milestone

Target:

```text
health worker running

ONLINE/SUSPECT/OFFLINE working

incidents working

email OFFLINE alert working

recovery working

dashboard functional

Google login functional
```

---

# 83. Day-3 Milestone

Target:

```text
SMS integration/interface

GPU incident confirmation

backup

restore verification

security hardening

failure tests

24-hour soak underway/completed as timing permits

production handoff documentation
```

If SMS provider approval/configuration is not available, leave the provider adapter ready and explicitly document SMS as pending external provider setup.

---

# 84. Production Blockers

Do NOT declare production ready if any of these remain:

```text
HTTP only

shared fleet-wide device credential

public MySQL

heartbeat accepted without durable database commit

no dashboard authorization

secrets committed to Git

unbounded nvidia-smi execution

no OFFLINE deduplication

no recovery behavior

no database backup

no tested agent boot startup
```

---

# 85. Acceptable Post-V1 Improvements

These may be added later without blocking the first production deployment:

```text
advanced infrastructure monitoring

central metrics stack

Prometheus/Grafana

Redis

distributed workers

managed queue

WebSockets

advanced per-project notification routing

point-in-time database recovery

automatic agent upgrades

multi-VM high availability
```

Only add them when there is an operational requirement.

---

# 86. V1 Deployment Success Criteria

Deployment succeeds when:

* one Ubuntu VM runs the central platform
* Caddy terminates valid HTTPS
* FastAPI is not directly public
* MySQL is not public
* MySQL data survives container restart/recreation
* migrations are controlled
* API and worker are separate processes
* edge agents run under systemd
* agents start after reboot
* each device uses an independent credential
* heartbeats persist successfully
* dashboard shows current device state
* Google authorization protects the dashboard
* OFFLINE detection works
* RECOVERED detection works
* email alerts work
* SMS architecture is replaceable/provider-independent
* GPU collection failures do not block system telemetry
* notification failures do not block heartbeat ingestion
* backups exist outside the live database volume
* restore procedure is documented and tested
* critical failure scenarios have been exercised

The production architecture remains:

```text
Linux Agent
     │
     │ HTTPS
     ▼
   Caddy
     │
     ▼
  FastAPI
     │
     ▼
 MySQL 8.x
     ▲
     │
   Worker
     │
     ├── Email
     └── SMS
```

with:

```text
OBSERVATION
+
ALERTING
```

only.

Remote administration, command execution, repair, and self-healing remain outside V1.

---

# 87. Stage 06 Operator Runbook

This runbook implements the approved Compose/systemd architecture. It is an operator procedure, not permission to alter an existing production host, database, firewall, or credentials without the required change approval.

## Central server layout and protected configuration

Place a reviewed release under `/opt/skybeat`. Create `/opt/skybeat/.env` from `deployment/production.env.example`, keep it out of Git, and set owner `root:root` with mode `0600`. It contains the application runtime URL, a distinct migration-account URL, MySQL bootstrap values, Caddy hostname, OIDC settings, session encryption key, and approved notification settings.

Use a real operator-controlled HTTPS hostname for both `SKYBEAT_PUBLIC_BASE_URL` and `SKYBEAT_CADDY_HOST`. Do not use placeholders, localhost, wildcard hosts, MySQL root URLs, or a real SMS recipient with SMS enabled before an approved provider adapter exists. The application rejects placeholder secrets, invalid timing relationships, weak all-identical Fernet keys, and incomplete production notification configuration.

Only Caddy publishes TCP 80 and 443. API, worker, and MySQL publish no host ports. Firewall/security-group policy must independently permit only intended HTTP/HTTPS and restricted operator administration access. Keep Docker socket mounts out of application containers.

On a fresh Compose MySQL volume, `deployment/mysql/01-create-migration-user.sh` creates the separately scoped migration account from the protected `.env` values. The MySQL image intentionally does not run initialization scripts against an existing volume. Before applying this layout to an existing database, have an approved operator provision and verify the migration account; do not reset, reinitialize, or replace retained data to make the script run.

Caddy is the sole public reverse proxy. The API does not enable unconditional forwarded-header trust, so arbitrary clients cannot manufacture client scheme or address metadata by sending proxy headers directly.

## Safe startup and migration sequence

Run the following from `/opt/skybeat` only after an approved database backup has completed:

```sh
python scripts/validate_deployment.py
docker compose --env-file .env config -q
docker compose --env-file .env up -d mysql
docker compose --env-file .env --profile migrate run --rm migrate python -m alembic current
docker compose --env-file .env --profile migrate run --rm migrate
docker compose --env-file .env --profile migrate run --rm migrate python -m alembic heads
docker compose --env-file .env up -d api worker caddy
```

The `migrate` profile is intentionally separate. API and worker startup never runs Alembic, creates a schema, drops a table, resets data, or initializes an existing database. A migration error stops the release: inspect the revision and backup, then follow the approved recovery process. Never solve a migration failure with `docker compose down -v`, a volume removal, a schema reset, or an automatic downgrade.

Verify internal API health after startup without exposing health endpoints publicly through Caddy:

```sh
docker compose --env-file .env exec api python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/livez', timeout=3).read()"
docker compose --env-file .env exec api python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/readyz', timeout=3).read()"
docker compose --env-file .env ps
docker compose --env-file .env logs --tail=100 api worker caddy mysql
```

`/readyz` checks bounded MySQL connectivity and schema compatibility. It does not depend on SMTP, SMS, Google, or individual device availability. Caddy intentionally returns 404 for public `/livez` and `/readyz` requests.

## Backup, restore, and upgrade

Create a daily logical MySQL backup using a dedicated backup account or protected MySQL client configuration; do not put a password on the command line. Store backups outside `mysql_data`, retain at least 30 days, copy them off-host, and use restricted/encrypted storage where available. Initial targets are RPO no worse than 24 hours and RTO no worse than 4 hours.

Test restore into an isolated MySQL environment first. Verify the Alembic revision, projects/devices, incident/event history, and notification jobs. Start the restored API with notification delivery disabled, validate dashboard and one heartbeat, reconcile sessions, credential revocations, and allowlists, then enable the worker and run a controlled outage/recovery test. Never overwrite a running production database automatically. Do not automatically downgrade Alembic revisions during application rollback; only roll back application code that remains schema-compatible.

For an upgrade: record deployed version and current revision, complete a backup, validate `.env`, build/pull the approved image, run the explicit migration sequence above, restart API/worker/Caddy, and run the smoke checks. Docker logs rotate through the Compose `local` driver; inspect them with `docker compose logs` rather than enabling payload-heavy debug logging.

## Agent installation, upgrade, and disable

Agents run directly under systemd. On a supported Linux device, create a non-login `skybeat` system user with no sudo or Docker access. Install the agent under `/opt/skybeat-agent`, create its virtual environment from the pinned agent dependencies, and install `deployment/systemd/skybeat-agent.service` as `/etc/systemd/system/skybeat-agent.service`.

Create `/etc/skybeat-agent/agent.env` from `deployment/systemd/agent.env.example`, replace its UUID and one-time enrollment token through a protected operator channel, and set owner `root:root` plus mode `0600`. Then run:

```sh
systemctl daemon-reload
systemctl enable --now skybeat-agent
systemctl status skybeat-agent
journalctl -u skybeat-agent --since "10 minutes ago"
```

Use a one-device canary before wider upgrades. Verify heartbeat, GPU telemetry, service restart, and boot startup; retain the previous compatible agent package for rollback. To stop monitoring on a device without deleting history, use `systemctl disable --now skybeat-agent` and separately disable monitoring through the approved server operator workflow.

## Production smoke test and pending verification

After deployment, verify from the intended network: valid Caddy TLS certificate, HTTP-to-HTTPS redirect, Google login and allowlist denial, first agent heartbeat, current dashboard telemetry, controlled OFFLINE/RECOVERED flow, GPU confirmation flow, SMTP behavior, and no-network SMS fallback. Do not deliberately damage production GPUs or send unapproved notifications.

The Windows development environment does not establish real Docker/Compose, Caddy/TLS/DNS, Linux systemd, NVIDIA, SMTP, SMS provider, firewall, backup restore, load, or soak evidence. The retained isolated MySQL data directory is unwritable and must not be repaired, reinitialized, reset, or have its ACLs changed merely for verification. Record those checks as environment-pending until exercised safely.
