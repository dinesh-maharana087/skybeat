# Availability, GPU Health, and Alerting

Status: approved V1 architecture baseline.

This document defines:

* device availability detection
* GPU health evaluation
* incident creation
* OFFLINE and RECOVERED notifications
* GPU degradation/recovery notifications
* email/SMS delivery
* deduplication
* retry behavior
* notification persistence
* recovery behavior

V1 alerts are informational only.

They never:

* reboot a device
* restart an agent
* restart a GPU driver
* execute commands
* repair a device
* trigger self-healing

---

# 1. Core Principle

The server determines whether a device is online.

The agent only sends heartbeats.

```text id="h0b83r"
Agent
  │
  │ heartbeat every ~30 sec
  ▼
Server
  │
  ├── heartbeat recent → ONLINE
  ├── heartbeat aging → SUSPECT
  └── heartbeat missing → OFFLINE
```

The agent must never declare itself offline.

A machine that has:

* lost power
* lost network
* crashed
* stopped its agent

cannot reliably send an offline message.

Therefore availability detection is always central.

---

# 2. What OFFLINE Means

An OFFLINE state means:

```text id="6mt3g2"
The central monitoring server has not received
an accepted heartbeat from the device within
the configured offline threshold.
```

It does NOT prove whether the underlying cause is:

* power failure
* network failure
* operating-system failure
* agent failure
* routing failure
* DNS failure
* firewall failure

The alert wording should therefore avoid claiming a cause that has not been observed.

Prefer:

```text id="z7kjwr"
Device is unreachable by the monitoring system.
```

rather than:

```text id="fhccxu"
Device has powered off.
```

---

# 3. Default Timing

Initial V1 defaults:

| Setting                      |            Default |
| ---------------------------- | -----------------: |
| Heartbeat interval           |         30 seconds |
| Heartbeat jitter             | approximately ±10% |
| SUSPECT threshold            |         75 seconds |
| OFFLINE threshold            |        180 seconds |
| Health sweep                 |          5 seconds |
| GPU failure confirmation     |    2 fresh samples |
| GPU recovery confirmation    |    2 fresh samples |
| GPU maximum confirmation gap |         75 seconds |
| Notification attempts        |            5 total |
| Notification retry base      |         30 seconds |
| Notification retry maximum   |         15 minutes |
| Notification expiry          |           24 hours |

These are configurable.

Required relationship:

```text id="sj91xq"
heartbeat interval
      <
SUSPECT threshold
      <
OFFLINE threshold
```

The initial values intentionally tolerate several missed 30-second heartbeats before declaring a device offline.

---

# 4. Availability States

Persisted V1 availability states:

```text id="nuvbd0"
ONLINE

SUSPECT

OFFLINE
```

Recovery is an event, not a permanent state.

A newly enrolled/re-enabled device may additionally be displayed as:

```text id="ct9j51"
AWAITING_FIRST_HEARTBEAT
```

while its persisted operational state remains compatible with the architecture.

---

# 5. Availability State Machine

Conceptually:

```text id="c1jzkl"
                heartbeat healthy
          ┌─────────────────────────┐
          │                         ▼
       ONLINE ◄────────────────── SUSPECT
          │                         │
          │ heartbeat ages          │ heartbeat ages
          ▼                         ▼
       SUSPECT -----------------> OFFLINE
                                    │
                                    │ new heartbeat
                                    ▼
                                  ONLINE
                                    │
                                    └── DEVICE_RECOVERED
```

---

# 6. ONLINE

A device is ONLINE when:

```text id="o0jjda"
current_time - last_seen_at < 75 seconds
```

for the current monitoring period.

No notification is generated merely because the device remains online.

---

# 7. SUSPECT

A device becomes SUSPECT when:

```text id="bdq03v"
75 seconds <= heartbeat age < 180 seconds
```

No administrator notification is sent at this point in V1.

The dashboard should make SUSPECT visually distinct.

The purpose is to expose temporary heartbeat loss without immediately alarming administrators.

---

# 8. OFFLINE

A device becomes OFFLINE when:

```text id="u1x48v"
heartbeat age >= 180 seconds
```

The server:

1. changes device state to OFFLINE
2. creates an availability incident if one does not already exist
3. creates one `DEVICE_OFFLINE` event
4. creates notification jobs
5. commits the state/event/jobs atomically

The same outage must not create repeated offline events.

---

# 9. RECOVERY

When a new accepted heartbeat arrives after an OFFLINE incident:

```text id="8z07gt"
OFFLINE
   ↓
ONLINE
```

The server:

1. updates `last_seen_at`
2. changes availability to ONLINE
3. closes the open availability incident
4. creates one `DEVICE_RECOVERED` event
5. creates recovery notification jobs

Recovery notification is generated only if an actual OFFLINE incident existed.

---

# 10. No False Recovery During Initial Enrollment

A new device begins monitoring without a current heartbeat.

Conceptually:

```text id="myyn5l"
AWAITING_FIRST_HEARTBEAT
```

If its first heartbeat arrives before OFFLINE occurs:

```text id="gxep3v"
→ ONLINE
```

No recovery alert is generated.

If the device remains unseen until the OFFLINE threshold:

```text id="foc0nv"
→ OFFLINE
```

an incident may be created.

A later first heartbeat then closes that incident and may generate recovery.

---

# 11. Monitoring Baseline

Availability uses the later relevant baseline from:

```text id="7n7kpc"
monitoring_started_at

last_seen_at
```

Pre-existing telemetry from before monitoring was enabled must not make a newly enabled device appear online.

Re-enabling monitoring starts a fresh monitoring period.

---

# 12. Authoritative Time

Availability uses central server/database acceptance time.

Do NOT use:

```text id="vng5js"
agent collected_at

agent wall clock

browser clock
```

to determine availability.

MySQL and application sessions must operate consistently in UTC.

The accepted server timestamp becomes:

```text id="2ouyz5"
last_seen_at
```

for a newly accepted heartbeat.

---

# 13. Health Sweep

A central worker evaluates monitored devices approximately every:

```text id="1bdpu4"
5 seconds
```

The sweep evaluates:

```text id="k2nml6"
current time - monitoring baseline
```

and applies:

```text id="fxij5k"
ONLINE

SUSPECT

OFFLINE
```

transitions.

The worker must not depend on notification-provider availability.

---

# 14. Aging Before Heartbeat

Suppose:

```text id="1enxjp"
last heartbeat:
12:00:00

offline threshold:
180 sec

new heartbeat reaches server:
12:03:10
```

The server must preserve the fact that an outage occurred.

Conceptually:

```text id="x54yye"
12:03:00
OFFLINE

12:03:10
RECOVERED
```

even if the periodic sweep happened to be delayed.

Therefore a new heartbeat transaction must evaluate the previous baseline before replacing it with the new heartbeat timestamp.

---

# 15. Concurrency Rule

Heartbeat processing and health sweeps may evaluate the same device simultaneously.

Both must serialize state changes using the same MySQL/InnoDB device-row lock.

Conceptually:

```sql id="4l10j3"
SELECT ...
FROM devices
WHERE id = ?
FOR UPDATE;
```

This prevents two workers from independently opening duplicate incidents.

Database unique constraints provide final duplicate protection.

---

# 16. Availability Transaction

Conceptually:

```text id="18p8km"
BEGIN

lock device row

read authoritative time

evaluate previous heartbeat age

apply overdue availability transition

insert/close incident if required

insert alert event if required

create notification jobs

apply new heartbeat if present

evaluate recovery if present

COMMIT
```

Provider network calls do NOT occur inside this transaction.

---

# 17. Duplicate Heartbeats

An already accepted:

```text id="1ax8dt"
device_id + heartbeat_id
```

must not:

* update `last_seen_at`
* update telemetry
* change availability
* advance GPU confirmation
* create another event
* create another notification

The original acknowledgement is returned according to `API_SPEC.md`.

---

# 18. One Incident Per Outage

For availability:

```text id="j4e2hp"
OFFLINE
OFFLINE
OFFLINE
OFFLINE
```

must still correspond to:

```text id="qj1b8v"
1 availability incident

1 DEVICE_OFFLINE event
```

No repeated reminder is sent merely because the machine remains offline.

A later recovery closes the incident.

A subsequent independent outage creates a new incident.

---

# 19. Incident Types

V1 incident types:

```text id="xpvglr"
AVAILABILITY

GPU
```

An incident contains approximately:

```text id="dpcezn"
incident_id

device_id

incident_type

opened_at

detected_at

closed_at

close_reason

current_reason

created_at

updated_at
```

Only one open incident of each type may exist for one device.

Because MySQL does not provide PostgreSQL-style partial unique indexes, this invariant must be enforced using a MySQL-compatible schema/transaction strategy.

The exact implementation belongs in the database migration design.

---

# 20. Alert Event Types

Required:

```text id="1j80rc"
DEVICE_OFFLINE

DEVICE_RECOVERED
```

V1 GPU notifications:

```text id="qlg91r"
GPU_DEGRADED

GPU_RECOVERED
```

GPU health must still be detected and displayed even if a deployment temporarily disables GPU notification delivery.

---

# 21. Event vs Delivery

These are different.

An event means:

```text id="s02r38"
Something happened.
```

Example:

```text id="w6tn7b"
DEVICE_OFFLINE
```

A delivery means:

```text id="4ubz3k"
Attempt to communicate that event
to a recipient using a channel.
```

Example:

```text id="dhiy0s"
DEVICE_OFFLINE
        ↓
Email → admin@example.com

DEVICE_OFFLINE
        ↓
SMS → configured recipient
```

One event can therefore have multiple deliveries.

---

# 22. Notification Channels

V1 architecture supports:

```text id="dyp98c"
EMAIL

SMS
```

Email:

```text id="tgr8aj"
SMTP provider
```

SMS:

```text id="ixp0kp"
provider-independent interface
```

A test/no-op adapter may be used until the production SMS provider is configured.

SMS implementation must not be coupled directly to incident logic.

---

# 23. Provider Interface

Conceptually:

```text id="89yvnr"
NotificationProvider
│
├── send(destination, message, delivery_id)
│
└── normalized result
```

Implementations:

```text id="13kvmd"
EmailProvider

SMSProvider
```

Provider result categories:

```text id="2tgnk4"
ACCEPTED

TRANSIENT_FAILURE

PERMANENT_FAILURE

UNCERTAIN
```

The alert engine decides retry policy.

Providers do not decide whether an incident exists.

---

# 24. Notification Jobs

When an alert event is created, the server creates durable notification jobs in MySQL.

Example:

```text id="80b4bp"
DEVICE_OFFLINE
      │
      ├── EMAIL → recipient A
      └── SMS   → recipient A
```

The jobs are committed in the same transaction as the alert event.

This prevents:

```text id="6gny4k"
event committed
        ↓
process crashes
        ↓
notification forgotten
```

No Redis or external broker is required for the initial deployment.

---

# 25. Delivery States

V1 delivery states:

```text id="td3dcm"
PENDING

IN_PROGRESS

RETRY_WAIT

SUCCEEDED

FAILED

CANCELLED
```

Meaning:

| State       | Meaning                     |
| ----------- | --------------------------- |
| PENDING     | Waiting for first attempt   |
| IN_PROGRESS | Currently being sent        |
| RETRY_WAIT  | Waiting for retry           |
| SUCCEEDED   | Provider accepted message   |
| FAILED      | Permanent/exhausted/expired |
| CANCELLED   | Superseded or disabled      |

`SUCCEEDED` means provider acceptance.

It does NOT prove a human actually read or received the message.

---

# 26. Delivery Worker

The worker periodically selects due notification jobs.

With MySQL 8.x/InnoDB, queue claiming may use:

```sql id="8up3x5"
SELECT ...
FROM notification_deliveries
WHERE ...
FOR UPDATE SKIP LOCKED;
```

when the selected MySQL version and transaction behavior have been validated in integration tests.

The worker:

1. claims a bounded batch
2. marks jobs IN_PROGRESS
3. commits the claim
4. releases database locks
5. calls providers
6. records results in a new short transaction

Provider communication never occurs while holding long-lived device locks.

---

# 27. Delivery Concurrency

Initial global notification concurrency:

```text id="u7b6in"
4
```

This is sufficient for the initial fleet.

Do not create:

* one thread per device
* one worker per recipient
* an unbounded task pool

Provider failures must not exhaust server resources.

---

# 28. Provider Timeout

Every provider call must have a bounded total deadline.

Initial:

```text id="msvxg1"
15 seconds
```

This should include as much as practical:

* DNS
* connect
* TLS
* send
* provider response

A broken SMTP/SMS service must not freeze the notification worker.

---

# 29. Retry Policy

Initial maximum:

```text id="upimrn"
5 total attempts
```

Example exponential retry schedule with jitter:

```text id="3flah3"
Attempt 1:
immediate

Attempt 2:
~30 seconds

Attempt 3:
~60 seconds

Attempt 4:
~2 minutes

Attempt 5:
~4 minutes
```

Exact delay should include jitter.

Maximum retry delay:

```text id="c14ywi"
15 minutes
```

Notification expiry:

```text id="91v6na"
24 hours
```

No delivery is retried after expiry.

---

# 30. Retryable Failures

Usually retry:

```text id="wx1lxq"
network timeout

temporary SMTP failure

temporary provider failure

provider throttling

temporary DNS/connectivity problem
```

Usually do NOT retry:

```text id="w6hkw1"
invalid destination

authentication rejected

invalid provider configuration

documented permanent provider rejection
```

Do not determine retryability from arbitrary free-text error messages alone.

---

# 31. Notification Isolation

A notification failure must NOT prevent:

* heartbeat acceptance
* availability evaluation
* GPU health evaluation
* incident persistence
* dashboard updates

Example:

```text id="1a7k5n"
SMTP DOWN

SMS DOWN

        but

heartbeats continue
health sweep continues
incidents continue
dashboard continues
```

This is mandatory.

---

# 32. Recovery Supersession

Suppose:

```text id="6vzz2p"
Device OFFLINE
     ↓
email job waiting

Device RECOVERS
```

A stale offline message should not intentionally be sent afterward if it has not already begun delivery.

Therefore recovery cancels outstanding:

```text id="4n6n3k"
PENDING

RETRY_WAIT
```

offline delivery jobs for the same incident.

Cancellation reason:

```text id="wr6w3h"
superseded_by_recovery
```

History remains stored.

---

# 33. In-Flight Notification During Recovery

If an offline notification is already being sent when recovery occurs, it may be impossible to recall.

The system should:

* record the attempt truthfully
* prevent further retries
* send the recovery event normally
* preserve timestamps and incident identity

External provider ordering cannot be perfectly guaranteed.

Alert wording must therefore include timestamps.

---

# 34. Recovery Notification

Example information:

```text id="tfcz6a"
Project:
StarAgri

Device:
Warehouse-GPU-01

Event:
RECOVERED

Offline since:
21-Sep-2026 14:10 UTC

Recovered:
21-Sep-2026 14:17 UTC

Duration:
7 minutes

Current state:
ONLINE
```

Use server timestamps.

Do not use agent time to calculate outage duration.

---

# 35. Offline Notification

Example:

```text id="2g5wdk"
Project:
StarAgri

Device:
Warehouse-GPU-01

Event:
OFFLINE

Last heartbeat:
21-Sep-2026 14:10 UTC

Offline threshold reached:
21-Sep-2026 14:13 UTC

Current state:
OFFLINE
```

Optionally include:

* hostname
* last known IP
* last known GPU status

but clearly mark last-known telemetry as stale.

---

# 36. Email Subject

Recommended:

```text id="xtbtl6"
[SkyBeat] OFFLINE - StarAgri / Warehouse-GPU-01
```

Recovery:

```text id="q7a1lx"
[SkyBeat] RECOVERED - StarAgri / Warehouse-GPU-01
```

GPU:

```text id="i8qz6u"
[SkyBeat] GPU DEGRADED - StarAgri / Warehouse-GPU-01
```

Keep subjects concise and operational.

---

# 37. SMS Message

SMS must be shorter.

Example:

```text id="aylvka"
SkyBeat ALERT: StarAgri/Warehouse-GPU-01 is OFFLINE. Last seen 14:10 UTC. Incident: 7c515a39.
```

Recovery:

```text id="w81oqs"
SkyBeat RECOVERY: StarAgri/Warehouse-GPU-01 is ONLINE again. Outage: 7 min. Incident: 7c515a39.
```

Do not include secrets or excessive telemetry.

---

# 38. Recipient Configuration

Recipients are server-controlled.

They must NOT be supplied by:

* agents
* heartbeat payloads
* device names
* project names

Initial configuration may support:

```text id="v5p0ma"
global email recipients

global SMS recipients
```

Project-specific recipients may be added if required by the deployment.

For the initial 2–3 day V1, global recipients are sufficient unless project-specific routing is a confirmed requirement.

---

# 39. Recipient Security

Validate recipient addresses/numbers.

Prevent:

* email header injection
* newline injection
* malformed destinations
* agent-controlled recipient routing

Notification templates must safely escape:

* project name
* device name
* hostname
* other telemetry strings

---

# 40. GPU Health

The agent reports:

```text id="rq29sz"
gpu_health.state

gpu_health.reason_code

gpu_health.inventory_reliable

gpus[]
```

The server separately owns expected GPU policy.

Server effective states:

```text id="4afpxg"
OK

GPU_MISSING

NVIDIA_SMI_FAILED

DRIVER_ERROR

UNKNOWN
```

---

# 41. Expected GPU Policy

Server device configuration may include:

```text id="4gdj69"
gpu_monitoring_enabled

expected_gpu_min_count

expected_gpu_uuids
```

Example:

```text id="y3boc8"
expected_gpu_min_count = 2
```

If reliable inventory contains only one GPU:

```text id="dt0msm"
GPU_MISSING
```

If inventory collection itself failed:

```text id="rm34a3"
NVIDIA_SMI_FAILED
```

Do not incorrectly convert unreliable inventory into `GPU_MISSING`.

---

# 42. CPU-Only Devices

For an explicitly configured CPU-only device:

```text id="5lrg99"
gpu_monitoring_enabled = false
```

No GPU incident is generated.

The dashboard displays:

```text id="gqozwi"
GPU monitoring: NOT MONITORED
```

The agent cannot disable this server-side policy by itself.

---

# 43. GPU Confirmation

Do not alert on one isolated bad GPU sample.

Default degradation confirmation:

```text id="mj2e7n"
2 consecutive fresh non-OK samples
```

Default recovery confirmation:

```text id="dmtt0h"
2 consecutive fresh OK samples
```

This reduces alerts from brief `nvidia-smi` glitches.

---

# 44. GPU Failure Example

```text id="tvz33f"
Heartbeat 1
GPU = NVIDIA_SMI_FAILED
failure streak = 1

Heartbeat 2
GPU = NVIDIA_SMI_FAILED
failure streak = 2

→ Open GPU incident
→ GPU_DEGRADED event
```

Continuing failures:

```text id="f8wy0s"
Heartbeat 3
Heartbeat 4
Heartbeat 5
```

do not create repeated GPU alerts.

---

# 45. GPU Recovery Example

```text id="yvm8dh"
GPU incident OPEN

Heartbeat 1
GPU = OK
recovery streak = 1

Heartbeat 2
GPU = OK
recovery streak = 2

→ Close GPU incident
→ GPU_RECOVERED event
```

One successful sample is insufficient.

---

# 46. GPU Sample Gap

GPU confirmation requires fresh consecutive samples.

Maximum gap:

```text id="z1fkib"
75 seconds
```

If the gap is:

```text id="xw2y7e"
>75 seconds
```

reset confirmation streaks.

A gap of exactly 75 seconds remains valid.

Duplicate heartbeat retries do not count as new GPU samples.

---

# 47. Device OFFLINE During GPU Incident

Suppose:

```text id="j0w9cq"
GPU incident OPEN
      ↓
Device becomes OFFLINE
```

The server should:

* keep GPU incident history
* mark GPU telemetry stale
* reset GPU confirmation streaks
* cancel unsent GPU degradation notification jobs where appropriate
* stop making fresh GPU conclusions while device is unreachable

Availability becomes the primary current condition.

---

# 48. Device Returns While GPU Incident Exists

When the device returns:

```text id="m1q66f"
DEVICE_RECOVERED
```

does NOT automatically mean:

```text id="hzq5t1"
GPU_RECOVERED
```

The system requires:

```text id="op7g4u"
2 fresh OK GPU samples
```

before closing the GPU incident.

The device recovery notification may indicate:

```text id="9on4lo"
Device reachable again.
GPU issue still under evaluation.
```

---

# 49. GPU Failure Category Changes

Example:

```text id="d8fsjc"
Sample 1:
NVIDIA_SMI_FAILED

Sample 2:
DRIVER_ERROR
```

These are both non-OK.

They contribute to the same GPU failure confirmation.

Do not create separate incidents simply because the failure category changed.

The latest reason may be recorded for diagnostics.

---

# 50. GPU Policy Changes

Changing:

```text id="sgr61g"
expected GPU count

expected GPU UUIDs

GPU monitoring enabled
```

is an administrative action.

It must:

* be audited
* reset relevant confirmation state
* close/reclassify the previous policy evaluation appropriately
* not manufacture a fake GPU recovery event

---

# 51. Durable Notification Data

Recommended logical tables:

```text id="ik62mo"
device_incidents

alert_events

notification_deliveries

notification_attempts
```

The exact schema is defined by database migrations and `ARCHITECTURE.md`.

---

# 52. Incident Record

Recommended fields:

```text id="2s6td1"
id

device_id

incident_type

opened_at

detected_at

closed_at

close_reason

current_reason

created_at

updated_at
```

---

# 53. Alert Event Record

Recommended fields:

```text id="u53e5b"
id

incident_id

device_id

event_kind

occurred_at

detected_at

project_name_snapshot

device_name_snapshot

reason_snapshot

created_at
```

Snapshots preserve historical meaning if a device/project is renamed later.

---

# 54. Delivery Record

Recommended fields:

```text id="5cnuxr"
id

event_id

channel

recipient_key

destination_snapshot

status

attempt_count

next_attempt_at

expires_at

provider_reference

last_error_code

claimed_at

created_at

updated_at
```

Sensitive destination information should be protected and masked in normal UI/logging.

---

# 55. Attempt Record

Recommended fields:

```text id="g7r5o9"
id

delivery_id

attempt_no

started_at

finished_at

result

error_code

provider_reference
```

Do not store:

* provider secrets
* SMTP password
* raw authorization headers
* full raw SMTP exchange

---

# 56. Notification Claiming

For the initial single-VM deployment, keep claiming simple.

Conceptually:

```text id="sgvqjc"
BEGIN

select due delivery
FOR UPDATE SKIP LOCKED

mark IN_PROGRESS

increment attempt count

insert attempt row

COMMIT

call provider

BEGIN

record result

update delivery

COMMIT
```

Do not hold database locks while waiting for an external provider.

---

# 57. Worker Crash During Delivery

There is an unavoidable ambiguity:

```text id="f79p52"
provider accepted message
        ↓
worker crashes
        ↓
database did not record success
```

A retry may produce a duplicate message.

V1 therefore provides:

```text id="hptu4r"
at-least-once bounded notification attempts
```

not mathematically guaranteed exactly-once delivery.

Where an SMS provider supports an idempotency key, use:

```text id="eb6r6w"
delivery ID
```

as the stable key.

Email may use a stable Message-ID for correlation.

---

# 58. Stuck IN_PROGRESS Jobs

The worker must be able to recover jobs left IN_PROGRESS after a crash.

Initial claim timeout:

```text id="2ymz72"
60 seconds
```

If a job remains IN_PROGRESS beyond this time:

* treat the previous attempt as uncertain
* return it to retry processing if budget remains
* fail/cancel if expired or superseded

Restart must not reset attempt counters.

---

# 59. Notification Deduplication

Required logical uniqueness:

```text id="x4m6bk"
one logical event kind per incident

one delivery per:
event + channel + recipient
```

This ensures:

```text id="c3w2ub"
DEVICE_OFFLINE
```

does not create five identical emails simply because the health sweep ran five times.

---

# 60. Alert History

The dashboard/API may expose:

```text id="1kttm3"
incident

event

channel

delivery status

attempt count

safe error category

timestamps
```

Do not expose unnecessary full recipient information.

Example:

```text id="6dbtef"
Email:
d***@company.com

Status:
SUCCEEDED
```

---

# 61. Notification Logging

Log safe metadata:

```text id="es2nm3"
device_id

incident_id

event_id

delivery_id

channel

attempt

result

duration

safe error code
```

Do not log:

```text id="7nqvrw"
SMTP password

SMS API key

full authorization header

raw provider payload containing secrets
```

---

# 62. Worker Health

The monitoring worker should persist/emit safe health information such as:

```text id="vld5y1"
last_health_sweep_at

last_notification_poll_at

notification backlog
```

The dashboard/internal health check can use this to detect a worker that is running but no longer processing state.

---

# 63. Monitoring Blind Spot

The API, worker, and MySQL initially run on the same central VM deployment.

If that VM completely fails:

```text id="2nyvja"
agents cannot reach server

server cannot evaluate agents

server cannot send its own outage alert
```

Therefore the production VM itself should eventually be monitored externally.

Examples:

* external uptime monitor
* infrastructure monitoring
* cloud VM alerting

This is outside the agent-to-server device availability state machine.

---

# 64. Database Failure

If MySQL becomes unavailable:

* new heartbeat commits may fail
* health evaluation cannot safely progress
* notification jobs cannot safely progress
* readiness becomes unhealthy

The system must NOT invent in-memory device transitions during the outage.

After MySQL returns, evaluation resumes from persisted state.

---

# 65. Provider Failure

If SMTP is unavailable:

```text id="npgclu"
EMAIL retries
```

while:

```text id="d4g0f3"
SMS may continue
```

If SMS is unavailable:

```text id="rghu15"
SMS retries
```

while:

```text id="0o7lcf"
EMAIL may continue
```

Provider channels should fail independently.

---

# 66. Notification Content Safety

Notification content must never include:

* device credentials
* Google OAuth tokens
* database credentials
* SMTP credentials
* SMS provider secrets
* complete configuration files
* arbitrary raw command output

Device-controlled strings must be safely escaped.

---

# 67. Required Availability Tests

Test:

```text id="l6q91n"
74.999 sec → ONLINE

75 sec → SUSPECT

179.999 sec → SUSPECT

180 sec → OFFLINE
```

Also test:

* first heartbeat
* first heartbeat after OFFLINE
* repeated sweeps
* repeated outage
* recovery
* second outage
* worker restart
* API restart
* MySQL restart
* monitoring disable/re-enable
* heartbeat/sweep race
* duplicate heartbeat

---

# 68. Required Alert Tests

Test:

```text id="i1weqj"
one outage
    → one offline event

continuing outage
    → no repeated event

recovery
    → one recovery event

second outage
    → new incident + new offline event
```

Also test:

* queued offline notification cancelled by recovery
* in-flight offline notification during recovery
* notification worker crash
* provider timeout
* provider authentication failure
* retry exhaustion
* notification expiry
* SMTP down while SMS works
* SMS down while email works

---

# 69. Required GPU Tests

Test:

```text id="sjf1nt"
one bad sample
    → no alert

two bad samples
    → GPU_DEGRADED

continued bad samples
    → no repeated degradation

one OK sample
    → incident remains

two OK samples
    → GPU_RECOVERED
```

Also test:

* missing expected GPU
* multiple GPUs
* GPU UUID reorder
* unreliable inventory
* `nvidia-smi` timeout
* driver error
* UNKNOWN state
* CPU-only device
* device OFFLINE during GPU incident
* device recovery while GPU remains unhealthy

---

# 70. Required MySQL Tests

Integration tests must use MySQL 8.x/InnoDB.

Test:

* row locking
* concurrent heartbeat/sweep
* duplicate incident prevention
* duplicate event prevention
* notification queue claiming
* `FOR UPDATE SKIP LOCKED`
* transaction rollback
* worker crash recovery
* MySQL restart
* lock timeout behavior

SQLite is not an acceptable substitute for concurrency/integration tests.

---

# 71. Required Production Failure Drills

Before production approval:

```text id="r8rt0m"
stop agent

kill agent

reboot monitored machine

disconnect monitored network

stop API

stop worker

restart central VM

stop MySQL

restore MySQL

break SMTP

break SMS provider

hang nvidia-smi

make NVIDIA driver unavailable

remove expected GPU in controlled test
```

Observe:

```text id="ih1w9v"
detection time

incident creation

email/SMS behavior

recovery behavior

dashboard state
```

---

# 72. Initial V1 Notification Scope

For the initial production deployment, prioritize:

```text id="f0sbyx"
DEVICE_OFFLINE

DEVICE_RECOVERED
```

These directly satisfy the primary operational requirement.

GPU health detection remains mandatory.

If implementation time permits within the V1 window, enable:

```text id="09d6ri"
GPU_DEGRADED

GPU_RECOVERED
```

using the same alert infrastructure.

If time becomes constrained, GPU notifications may be enabled immediately after the core offline/recovery path without redesigning the architecture.

---

# 73. Implementation Priority

Because the deployment target is 2–3 days, implement in this order:

```text id="uubklv"
1. Heartbeat availability state machine

2. Availability incidents

3. DEVICE_OFFLINE event

4. Email notification

5. DEVICE_RECOVERED event

6. Recovery email

7. Durable notification jobs

8. Retry + deduplication

9. SMS provider interface

10. GPU incident detection

11. GPU notifications

12. Advanced delivery hardening
```

Do not begin with a sophisticated notification framework.

First prove:

```text id="m4vzxx"
stop device
    ↓
server detects OFFLINE
    ↓
incident created
    ↓
email received
```

Then prove:

```text id="bzzsnh"
device returns
    ↓
server detects ONLINE
    ↓
incident closes
    ↓
recovery email received
```

Only then add additional provider/retry hardening.

---

# 74. Day-2 Functional Milestone

The project should be considered functionally useful when this works:

```text id="4ifn8b"
Ubuntu GPU Device
      │
      │ heartbeat
      ▼
FastAPI
      ▼
MySQL
      ▼
Health Worker
      ▼
Device OFFLINE
      ▼
Incident
      ▼
Email Alert
```

and:

```text id="3qhvpm"
Device reconnects
      ▼
Heartbeat accepted
      ▼
Incident closes
      ▼
RECOVERED
      ▼
Recovery Email
```

SMS and GPU alert delivery then reuse the same infrastructure.

---

# 75. V1 Success Criteria

The alerting system succeeds when:

* a stopped/unreachable agent becomes OFFLINE centrally
* one outage creates one offline incident
* no repeated offline alerts are generated for the same outage
* recovery closes the correct incident
* one recovery event is generated
* email works
* SMS can be plugged into the same interface
* provider failure does not break monitoring
* GPU health is evaluated independently
* GPU glitches require confirmation
* MySQL persists incidents and delivery jobs
* dashboard can show incident/delivery status
* monitoring continues correctly across service restarts
* no alert causes a remote device action

The architecture remains:

```text id="5nnc8o"
OBSERVE
   ↓
DETECT
   ↓
RECORD
   ↓
NOTIFY
```

not:

```text id="6o42hn"
OBSERVE
   ↓
REPAIR
```

Remote operations and self-healing remain outside V1.
