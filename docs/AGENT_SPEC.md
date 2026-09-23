# V1 Linux Monitoring Agent

Status: approved V1 agent architecture baseline.

The SkyBeat agent is a lightweight Linux service installed on monitored edge/GPU devices.

Its responsibilities are:

* identify itself securely to the central server
* collect system telemetry
* collect NVIDIA GPU telemetry
* classify local GPU observation failures
* send periodic HTTPS heartbeats
* retry safely during temporary network/server failures
* produce useful bounded local logs

The agent does NOT:

* determine central ONLINE/OFFLINE state
* send administrator alerts directly
* receive commands
* reboot devices
* restart GPU drivers
* repair devices
* change operating-system configuration
* open remote shells
* execute server-provided commands
* update itself remotely

The server remains authoritative for:

* project assignment
* device name
* availability
* expected GPU inventory
* incidents
* alerts
* notification delivery

This project has no dependency on Canopus.

---

# 1. V1 Platform

Initial supported environment:

* Ubuntu Linux
* Python 3.12 where available
* physical NVIDIA GPU hosts
* systemd
* outbound HTTPS connectivity

Primary tested Ubuntu targets:

* Ubuntu 22.04 LTS
* Ubuntu 24.04 LTS

Other Linux distributions may work but are not considered supported until tested.

V1 does not promise complete support for:

* Windows
* macOS
* Jetson-specific telemetry
* MIG-specific telemetry
* vGPU
* container-only deployments
* Kubernetes nodes

Those may be validated separately later.

---

# 2. Agent Design Principle

The agent should remain intentionally small.

Conceptually:

```text
skybeat-agent
│
├── Configuration
│
├── Runtime / Scheduler
│
├── System Collector
│
├── GPU Collector
│
├── Telemetry Builder
│
├── HTTPS Transport
│
└── Logging
```

No:

* local database
* message broker
* remote command listener
* HTTP server
* metrics daemon
* NVIDIA SDK
* persistent telemetry queue

is required for V1.

---

# 3. Proposed Package Structure

```text
agent/
│
├── pyproject.toml
├── requirements.lock
│
├── src/
│   └── skybeat_agent/
│       │
│       ├── __init__.py
│       ├── main.py
│       ├── config.py
│       ├── contracts.py
│       ├── runtime.py
│       ├── telemetry.py
│       ├── transport.py
│       ├── logging.py
│       │
│       └── collectors/
│           ├── __init__.py
│           ├── system.py
│           └── gpu.py
│
└── tests/
```

Responsibilities:

| Module                 | Responsibility                   |
| ---------------------- | -------------------------------- |
| `main.py`              | Agent startup/shutdown           |
| `config.py`            | Typed configuration              |
| `contracts.py`         | Heartbeat schema serialization   |
| `runtime.py`           | Scheduling and lifecycle         |
| `telemetry.py`         | Snapshot assembly                |
| `transport.py`         | Authenticated HTTPS              |
| `logging.py`           | Structured/redacted logging      |
| `collectors/system.py` | CPU/RAM/disk/host collection     |
| `collectors/gpu.py`    | NVIDIA collection/classification |

Avoid unnecessary abstraction layers until implementation requires them.

---

# 4. Dependencies

Prefer a small dependency set.

Expected:

* Python standard library
* `psutil`
* one maintained HTTP client

Possible HTTP client:

```text
httpx
```

or another explicitly selected maintained library.

Exact versions are pinned during implementation.

Do not add:

* SQL database client
* Redis
* Celery
* Docker SDK
* NVIDIA Python SDK

unless a later requirement justifies them.

---

# 5. Device Identity

Each agent receives a server-generated immutable:

```text
DEVICE UUID
```

Example:

```text
8cf5c647-70a0-4559-a4da-1a39dd66c119
```

The UUID is NOT derived from:

* hostname
* IP
* MAC address
* GPU UUID
* machine-id

The server remains authoritative for device identity.

---

# 6. Device Credential

Each device receives an independent credential.

Conceptual format:

```text
sb1.<credential_id>.<secret>
```

The secret must contain strong cryptographically secure random entropy.

The agent retains the raw credential because it must authenticate.

The server stores only the appropriate secure representation/hash.

Never place the credential in:

* command-line arguments
* logs
* heartbeat payload
* exception messages
* shell history
* Git
* process diagnostics where avoidable

---

# 7. Project Assignment

The agent does NOT know or control its project assignment.

The agent sends:

```text
device UUID
```

The server determines:

```text
UUID
  ↓
Device
  ↓
Project
```

The heartbeat must not contain:

```text
project_id

project_name

device_name
```

Moving a device between projects therefore requires no agent reconfiguration.

Renaming a device also requires no agent reconfiguration.

---

# 8. Local Configuration

Preferred configuration location:

```text
/etc/skybeat-agent/agent.env
```

Application:

```text
/opt/skybeat
```

Service:

```text
/etc/systemd/system/skybeat-agent.service
```

Configuration should be:

* root owned
* mode `0600`
* excluded from Git

---

# 9. Configuration Variables

Required:

```text
SKYBEAT_SERVER_URL

SKYBEAT_DEVICE_ID

SKYBEAT_DEVICE_TOKEN
```

Example:

```text
SKYBEAT_SERVER_URL=https://monitor.example.com

SKYBEAT_DEVICE_ID=8cf5c647-70a0-4559-a4da-1a39dd66c119

SKYBEAT_DEVICE_TOKEN=<secret>
```

Optional settings:

| Variable                             |               Default |
| ------------------------------------ | --------------------: |
| `SKYBEAT_HEARTBEAT_INTERVAL_SECONDS` |                    30 |
| `SKYBEAT_REQUEST_TIMEOUT_SECONDS`    |                    10 |
| `SKYBEAT_CONNECT_TIMEOUT_SECONDS`    |                     3 |
| `SKYBEAT_MAX_SEND_ATTEMPTS`          |                     3 |
| `SKYBEAT_GPU_COLLECTION_ENABLED`     |                  true |
| `SKYBEAT_NVIDIA_SMI_PATH`            | `/usr/bin/nvidia-smi` |
| `SKYBEAT_NVIDIA_SMI_TIMEOUT_SECONDS` |                     5 |
| `SKYBEAT_DISK_MOUNTPOINTS`           |                   `/` |
| `SKYBEAT_LOG_LEVEL`                  |                `INFO` |

Implementation may add bounded retry/jitter configuration where useful.

Avoid exposing dozens of configuration knobs unnecessarily.

---

# 10. Configuration Validation

Configuration is validated before normal operation.

Fatal configuration errors include:

* missing server URL
* non-HTTPS production URL
* malformed device UUID
* missing credential
* invalid heartbeat interval
* invalid timeout
* invalid GPU executable path
* excessive disk mount list

Invalid configuration should:

1. log a safe error
2. exit non-zero
3. allow systemd restart policy/start limits to expose persistent failure

Never silently substitute unsafe defaults.

---

# 11. HTTPS Requirement

Production server URLs must use:

```text
https://
```

TLS certificate validation is mandatory.

Never implement:

```text
verify=False
```

as an automatic fallback.

Never fall back from HTTPS to HTTP after a certificate failure.

Unexpected redirects should be rejected so bearer credentials are not forwarded to another origin.

---

# 12. Runtime Model

Use one main agent runtime.

Conceptually:

```text
Runtime
│
├── schedule collection
│
├── collect system telemetry
│
├── collect GPU telemetry
│
├── build heartbeat
└── send heartbeat
```

Collection failures are isolated.

For example:

```text
CPU        OK
Memory     OK
Disk       OK
GPU        NVIDIA_SMI_FAILED
```

must still produce a heartbeat.

---

# 13. Heartbeat Schedule

Default interval:

```text
30 seconds
```

Use monotonic time for scheduling.

Do not depend on wall-clock time for interval calculation.

A small random startup delay/jitter may be used to prevent many devices from contacting the server simultaneously.

Recommended initial startup jitter:

```text
0–3 seconds
```

Normal interval jitter may remain small.

For example:

```text
approximately 27–33 seconds
```

for a nominal 30-second profile.

---

# 14. First Heartbeat

After service startup:

1. validate configuration
2. initialize collectors
3. collect current telemetry
4. send the first heartbeat

Target:

```text
within one normal heartbeat interval
```

under healthy conditions.

The first heartbeat is NOT a recovery notification.

The server determines first-contact semantics.

---

# 15. Snapshot Identity

Each newly collected snapshot receives a unique:

```text
heartbeat_id
```

UUID.

The same `heartbeat_id` must be reused when retrying the same immutable snapshot.

Never mutate telemetry after assigning the heartbeat ID.

A newly collected snapshot receives a new heartbeat ID.

---

# 16. Snapshot Fields

The heartbeat follows `API_SPEC.md`.

At minimum it includes:

```text
schema_version

heartbeat_id

device_id

agent_version

collected_at

hostname

ip_addresses

os

uptime_seconds

cpu

memory

disks

gpu_health

gpus
```

Project information is not included.

---

# 17. Latest-Only Buffer

The agent does not maintain a persistent telemetry backlog.

Conceptually:

```text
Latest Snapshot
      │
      ▼
Sender
```

If network communication fails and newer telemetry becomes available, the agent may replace old unsent telemetry with the newest snapshot.

This prevents:

* unlimited disk growth
* large replay queues
* stale telemetry floods after reconnection

A process restart may lose an unsent snapshot.

This is acceptable for V1 because the system monitors current health rather than providing guaranteed telemetry archival from disconnected devices.

---

# 18. No Offline Message From Agent

The agent must never attempt:

```text
POST /offline
```

during shutdown.

That would be unreliable because a genuinely failed machine cannot send such a message.

Instead:

```text
Agent heartbeat stops
        ↓
Server observes missing heartbeat
        ↓
Server changes availability
        ↓
Server creates incident
```

This is a core architectural rule.

---

# 19. System Telemetry

Use:

```text
psutil
```

and standard Python/Linux interfaces.

Do not use shell commands for normal CPU/RAM/storage collection.

Do not inspect:

* user files
* process command lines
* browser data
* application contents
* login sessions

unless a future approved requirement explicitly requires it.

---

# 20. Hostname

Collect the local hostname.

Treat it only as telemetry.

It must not become device identity.

Maximum wire length is defined by `API_SPEC.md`.

---

# 21. IP Addresses

Collect active IPv4/IPv6 addresses.

Exclude where practical:

* loopback
* unspecified
* multicast
* duplicates

Link-local addresses may be excluded unless needed for a supported environment.

Maximum:

```text
16 addresses
```

Ordering should be deterministic where practical.

---

# 22. Operating System

Collect:

```text
distribution name

distribution version

kernel version

architecture
```

Missing values become:

```text
null
```

rather than fabricated strings.

---

# 23. Uptime

Prefer:

```text
psutil.boot_time()
```

or a tested Linux monotonic source.

Convert to:

```text
uptime_seconds
```

Do not use agent uptime as central device availability.

---

# 24. CPU

Collect aggregate CPU utilization.

Range:

```text
0–100%
```

Be aware that the first nonblocking CPU utilization call may not represent a valid interval measurement.

Prime CPU sampling appropriately.

If unavailable:

```text
null
```

---

# 25. Memory

Collect:

```text
total

used

available

utilization percent
```

Do not confuse:

```text
available memory
```

with:

```text
free memory
```

Use the semantics provided by the tested `psutil` version.

---

# 26. Storage

Default monitored mount:

```text
/
```

Additional mounts are explicitly configured.

Do not automatically enumerate every mounted filesystem.

This avoids unexpectedly touching:

* NFS
* CIFS
* autofs
* removable devices
* procfs
* sysfs
* container pseudo-filesystems

For each configured mount collect:

```text
device

mountpoint

filesystem

total

used

free

utilization
```

Maximum configured mounts:

```text
64
```

---

# 27. Collector Failure

If one configured filesystem cannot be measured:

```text
Disk /
    OK

Disk /data
    unavailable
```

other telemetry must still be sent.

Unavailable values become null.

Never replace failed readings with zero.

---

# 28. Collection Deadline

Telemetry collection must remain bounded.

Initial target:

```text
System collection <= 3 seconds

GPU collection <= 5 seconds

Snapshot assembly <= 6 seconds
```

These are engineering targets and should be validated on actual systems.

A slow collector must not indefinitely block heartbeat progress.

---

# 29. NVIDIA Collection

V1 uses:

```text
nvidia-smi
```

for NVIDIA GPU telemetry.

Default executable:

```text
/usr/bin/nvidia-smi
```

The executable path must be locally configured and trusted.

The server cannot supply executable paths or arguments.

---

# 30. Approved NVIDIA Query

Conceptual command:

```text
/usr/bin/nvidia-smi \
  --query-gpu=index,uuid,name,utilization.gpu,temperature.gpu,memory.total,memory.used,driver_version \
  --format=csv,noheader,nounits
```

Implementation must use an argument array.

Use:

```text
shell=False
```

Never construct a shell command using untrusted strings.

---

# 31. GPU Command Environment

Use a controlled subprocess environment.

Set:

```text
LC_ALL=C
```

where appropriate for predictable parsing.

Do not pass the device bearer token to `nvidia-smi`.

Do not pass unrelated application secrets to collector subprocesses.

Standard input should be closed.

---

# 32. NVIDIA Command Restrictions

The agent may use only approved read-only NVIDIA telemetry queries.

It must NOT execute GPU mutation commands for:

* reset
* persistence changes
* clock changes
* power changes
* compute mode
* MIG configuration
* driver changes

V1 is observation-only.

---

# 33. NVIDIA Output Parsing

Use a real CSV parser.

Do not parse by naive:

```text
split(",")
```

because GPU model strings or future output variations may contain unexpected formatting.

Validate:

* column count
* GPU index
* UUID
* numeric fields
* duplicate identity
* row count

Malformed output invalidates the inventory for that cycle rather than silently hiding a GPU.

---

# 34. GPU Memory Units

`nvidia-smi` memory values from this query are interpreted as MiB.

Convert using:

```text
1 MiB = 1,048,576 bytes
```

Do not interpret MiB as decimal MB.

---

# 35. Unsupported NVIDIA Values

Values such as:

```text
N/A
```

may occur.

Where a metric is legitimately unavailable, represent it as:

```text
null
```

Do not convert unavailable metrics to zero.

---

# 36. GPU Output Limits

GPU command output must be bounded.

Initial limits:

```text
64 GPU rows

64 KiB combined captured output
```

If limits are exceeded:

```text
gpu_health = NVIDIA_SMI_FAILED

reason_code = output_limit
```

Do not parse a truncated inventory as healthy.

---

# 37. GPU Timeout

Default GPU collection deadline:

```text
5 seconds
```

A hanging `nvidia-smi` must not indefinitely block the agent.

When timeout occurs:

```text
gpu_health = NVIDIA_SMI_FAILED

reason_code = timeout

inventory_reliable = false
```

The heartbeat still sends system telemetry.

---

# 38. GPU Process Cleanup

After timeout:

1. terminate the collector process/group
2. allow a short bounded grace period
3. force termination if possible
4. continue the monitoring loop

If the process remains stuck in uninterruptible kernel/driver I/O, the agent must NOT continuously spawn replacement processes.

Instead:

```text
gpu_health = NVIDIA_SMI_FAILED

reason_code = collector_stuck
```

until the previous helper exits or an operator resolves the host condition.

The guarantee is:

```text
agent waiting is bounded
```

not:

```text
Linux can always kill a driver-stuck process
```

---

# 39. GPU Health Vocabulary

Schema V1 reason/state mapping:

| Observation                  | State               | Reason               | Inventory Reliable |
| ---------------------------- | ------------------- | -------------------- | ------------------ |
| Valid non-empty inventory    | `OK`                | null                 | true               |
| Valid empty inventory        | `GPU_MISSING`       | `no_gpu`             | true               |
| Command missing              | `NVIDIA_SMI_FAILED` | `command_missing`    | false              |
| Permission failure           | `NVIDIA_SMI_FAILED` | `permission_denied`  | false              |
| Timeout                      | `NVIDIA_SMI_FAILED` | `timeout`            | false              |
| Stuck collector              | `NVIDIA_SMI_FAILED` | `collector_stuck`    | false              |
| Known driver failure         | `DRIVER_ERROR`      | `driver_unavailable` | false              |
| Other nonzero exit           | `NVIDIA_SMI_FAILED` | `nonzero_exit`       | false              |
| Invalid output               | `NVIDIA_SMI_FAILED` | `malformed_output`   | false              |
| Output limit                 | `NVIDIA_SMI_FAILED` | `output_limit`       | false              |
| Unsupported required metric  | `UNKNOWN`           | `unsupported_metric` | true               |
| Unexpected collector failure | `UNKNOWN`           | `collector_error`    | false              |
| Locally disabled collector   | `UNKNOWN`           | `disabled`           | false              |

This vocabulary must remain consistent with `API_SPEC.md`.

---

# 40. Driver Failure Classification

Known tested driver failures may map to:

```text
DRIVER_ERROR
```

Do not classify arbitrary stderr text as a driver failure.

Unknown command failures should safely fall back to:

```text
NVIDIA_SMI_FAILED
```

Classification should be based on tested:

* exit codes
* narrowly recognized diagnostics

not broad substring guessing.

---

# 41. Multiple GPUs

The agent supports:

```text
0..64 GPUs
```

GPU UUID is preferred for stable identity.

Example:

Before reboot:

```text
index 0 → GPU-A
index 1 → GPU-B
```

After reboot:

```text
index 0 → GPU-B
index 1 → GPU-A
```

This is not a missing-GPU event.

The server compares expected inventory using GPU UUID/count policy.

---

# 42. Expected GPU Inventory

The agent does not determine expected GPU count.

Server configuration may contain:

```text
expected_gpu_min_count

expected_gpu_uuids
```

The agent reports only current observation.

It must never change its behavior to redefine expected inventory based on what it currently sees.

---

# 43. Reliable Empty Inventory

If `nvidia-smi` successfully and reliably determines that no GPUs exist:

```text
gpus = []

inventory_reliable = true

gpu_health = GPU_MISSING
```

If the command failed:

```text
gpus = []

inventory_reliable = false
```

The server must be able to distinguish:

```text
No GPU observed
```

from:

```text
Could not determine GPU inventory
```

---

# 44. Partial GPU Failure

Do not reuse GPU values from the previous cycle and present them as current.

If current GPU inventory cannot be reliably collected:

```text
gpus = []
```

or only the contract-approved current observation is sent.

Previous telemetry remains available server-side as stale historical information.

---

# 45. HTTPS Sender

Heartbeat endpoint:

```text
POST /api/v1/heartbeats
```

Headers:

```text
Content-Type: application/json

Authorization: Bearer <device-token>
```

The device credential must not be placed in the URL.

---

# 46. Request Timeout

Initial total request deadline:

```text
10 seconds
```

Suggested connection timeout:

```text
3 seconds
```

The implementation must bound:

* DNS resolution where practical
* connection
* TLS negotiation
* write
* response wait

No network operation should block indefinitely.

---

# 47. Successful Send

A heartbeat is considered acknowledged only when:

```text
HTTP 200
```

is received with a valid acknowledgement matching:

```text
heartbeat_id

device_id
```

If the response is malformed or mismatched, treat acceptance as uncertain and retry the same immutable heartbeat ID within retry policy.

---

# 48. Retry Policy

Maximum transmissions for one snapshot:

```text
3
```

including the first attempt.

Use bounded exponential backoff with jitter.

Example:

```text
Attempt 1
    immediate

Attempt 2
    approximately 0–1 sec

Attempt 3
    approximately 0–2 sec
```

A newer snapshot may supersede retries for an older snapshot.

Do not allow retries to create an ever-growing backlog.

---

# 49. Extended Outage

If the server/network remains unavailable:

* continue local collection
* retain only the newest useful snapshot
* progressively reduce send frequency
* cap outage backoff

Initial maximum outage pacing:

```text
60 seconds
```

After successful acknowledgement:

```text
reset outage backoff
```

This protects both the device and server during prolonged outages.

---

# 50. HTTP Response Handling

| Response | Agent behavior                                    |
| -------- | ------------------------------------------------- |
| `200`    | Validate acknowledgement and complete             |
| `400`    | Drop sample; contract/request problem             |
| `401`    | Stop fast retry; credential problem               |
| `403`    | Stop fast retry; identity/policy problem          |
| `404`    | Configuration/endpoint problem                    |
| `408`    | Bounded retry                                     |
| `409`    | Drop sample; heartbeat conflict/programming issue |
| `413`    | Drop sample; payload too large                    |
| `415`    | Drop sample                                       |
| `422`    | Drop incompatible sample                          |
| `429`    | Respect bounded Retry-After                       |
| `500`    | Bounded retry                                     |
| `502`    | Bounded retry                                     |
| `503`    | Bounded retry                                     |
| `504`    | Bounded retry                                     |

The agent should primarily branch on:

```text
HTTP status
+
machine-readable error code
```

not human-readable error text.

---

# 51. Credential Failure

On:

```text
401
403
```

do not send every 30 seconds indefinitely.

Enter slow probe mode.

Suggested:

```text
maximum one authentication probe every 5 minutes
```

Continue collecting locally but do not persist a backlog.

Log a clear operator-visible category.

---

# 52. TLS Failure

TLS verification failure enters slow failure mode.

Never:

* disable certificate verification
* accept arbitrary certificates
* fall back to HTTP

The error must be visible to operators through local logs/service status.

---

# 53. Retry-After

For HTTP:

```text
429
```

support a bounded integer-seconds:

```text
Retry-After
```

Maximum honored value:

```text
300 seconds
```

Do not retain an obsolete snapshot for the entire wait.

The newest snapshot should be used when sending resumes.

---

# 54. Logging

Logs should be useful but bounded.

Include where appropriate:

```text
timestamp

level

component

device UUID

heartbeat ID

event category

duration

attempt number

safe reason code
```

Do not routinely log complete telemetry payloads.

---

# 55. Secret Redaction

Never log:

```text
device token

Authorization header

agent.env contents

SMTP credentials

SMS credentials

Google credentials

raw nvidia-smi output containing unexpected data
```

Unexpected exceptions must pass through safe logging/redaction.

---

# 56. Repeated Failures

Avoid one log line every few seconds for the same continuing failure.

Recommended behavior:

```text
first failure
    log

failure category changes
    log

periodic summary
    log

recovery
    log
```

This keeps journald useful during long outages.

---

# 57. systemd Service

Service:

```text
skybeat-agent.service
```

Suggested:

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
ExecStart=/opt/skybeat/venv/bin/skybeat-agent
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
UMask=0077

[Install]
WantedBy=multi-user.target
```

This is conceptual baseline configuration.

The final deployment unit may add tested hardening options.

---

# 58. Runtime User

Preferred runtime user:

```text
skybeat
```

The service should not run as root where practical.

The account requires only enough access to:

* collect normal system metrics
* execute `nvidia-smi`
* access required NVIDIA device interfaces through normal driver permissions
* establish outbound HTTPS connections

It does not require:

* sudo
* SSH keys
* Docker socket
* arbitrary filesystem write access
* host configuration write access

---

# 59. systemd Hardening

Potential settings include:

```text
NoNewPrivileges=true

ProtectSystem=strict

ProtectHome=true

PrivateTmp=true
```

but they must be tested.

Do NOT blindly enable settings such as device isolation that prevent legitimate NVIDIA access.

Security hardening must not silently break telemetry.

---

# 60. Shutdown

On:

```text
SIGTERM
```

the agent should:

1. stop scheduling new collections
2. cancel retry timers
3. stop/cancel network activity where possible
4. request bounded collector cleanup
5. exit cleanly

Target application shutdown budget:

```text
<=15 seconds
```

No final offline heartbeat is required.

---

# 61. Agent Crash

systemd handles unexpected process failure.

Initial policy:

```text
Restart=on-failure

RestartSec=5
```

Start limits should prevent endless rapid crash loops.

A repeated startup failure must become visible through:

```text
systemctl status skybeat-agent

journalctl -u skybeat-agent
```

---

# 62. Monitoring During Boot

The service starts after:

```text
network-online.target
```

but must still tolerate:

* network unavailable
* DNS unavailable
* server unavailable

It should remain running and retry according to bounded policy.

---

# 63. CPU-Only Device

For approved CPU-only systems:

```text
SKYBEAT_GPU_COLLECTION_ENABLED=false
```

The agent reports:

```text
gpu_health = UNKNOWN

reason_code = disabled

inventory_reliable = false
```

However, the server must also have:

```text
gpu_monitoring_enabled = false
```

The agent cannot disable server-side GPU monitoring policy by itself.

---

# 64. Resource Targets

The agent is intended to be lightweight.

Initial acceptance targets:

```text
RSS <= approximately 100 MiB

Idle CPU <= approximately 1% of one CPU core
```

These must be measured.

The term:

```text
lightweight
```

is not sufficient without testing.

---

# 65. Network Usage

Heartbeat payloads should remain compact.

At approximately:

```text
30-second interval
```

there are:

```text
2 heartbeats/minute/device
```

or:

```text
2880 heartbeats/day/device
```

The agent should not transmit:

* logs
* command output
* historical backlog
* screenshots
* large files

as part of routine heartbeats.

---

# 66. Schema Version

Wire schema:

```text
schema_version = 1
```

Agent release version:

```text
agent_version
```

These are independent.

Example:

```text
agent_version = 1.3.0

schema_version = 1
```

Several agent versions may implement the same heartbeat schema.

---

# 67. Compatibility Strategy

For backward-compatible changes:

```text
Server support first
        ↓
Agent rollout second
```

Do not deploy an agent schema before the server supports it.

Breaking heartbeat changes require a new schema version.

---

# 68. Credential Rotation

A device may temporarily have:

```text
old credential

new credential
```

active during controlled rotation.

Recommended maximum overlap:

```text
24 hours
```

Procedure:

1. create new credential server-side
2. update `/etc/skybeat-agent/agent.env`
3. restart agent
4. verify successful heartbeat using new credential
5. revoke old credential

Do not automatically revoke the old credential before successful validation.

---

# 69. Installation Layout

Recommended:

```text
/opt/skybeat/
    venv/
    app/

/etc/skybeat-agent/
    agent.env

/etc/systemd/system/
    skybeat-agent.service
```

Runtime-generated state should be minimal.

Logs go to:

```text
journald
```

rather than an unbounded application log file by default.

---

# 70. Installation Workflow

Conceptually:

```text
Create server-side project
        ↓
Enroll device
        ↓
Generate UUID + credential
        ↓
Install agent package
        ↓
Create /etc/skybeat-agent/agent.env
        ↓
Install systemd unit
        ↓
systemctl daemon-reload
        ↓
systemctl enable --now skybeat-agent
        ↓
Verify heartbeat
        ↓
Verify dashboard
```

Detailed commands belong in `DEPLOYMENT.md`.

---

# 71. Required Unit Tests

Test:

* configuration validation
* HTTPS-only validation
* device UUID parsing
* heartbeat ID generation
* snapshot immutability
* null versus zero
* CPU priming
* memory collection
* disk collection
* failed mount
* IP filtering
* OS collection
* uptime
* serialization
* payload bounds

---

# 72. Required GPU Tests

Test:

* nvidia-smi exists
* nvidia-smi missing
* permission denied
* timeout
* process stuck
* output flood
* non-zero exit
* known driver failure
* malformed CSV
* missing columns
* invalid numeric field
* duplicate index
* duplicate UUID
* zero GPUs
* one GPU
* multiple GPUs
* GPU reorder
* N/A values
* MiB → bytes conversion
* GPU collection disabled

Use stored fixture outputs for automated parser tests.

---

# 73. Required Transport Tests

Test:

* successful heartbeat
* server unavailable
* DNS failure
* connect timeout
* TLS failure
* read timeout
* lost acknowledgement
* malformed acknowledgement
* mismatched heartbeat ID
* HTTP 401
* HTTP 403
* HTTP 409
* HTTP 413
* HTTP 422
* HTTP 429
* HTTP 500
* HTTP 503
* unexpected redirect
* retry exhaustion
* outage backoff
* recovery after outage

---

# 74. Required Runtime Tests

Test:

* normal 30-second scheduling
* startup jitter
* wall-clock changes
* latest-only snapshot replacement
* retry cancellation
* clean SIGTERM
* process crash/restart
* network missing at boot
* no telemetry backlog
* no unbounded threads/processes
* no memory growth during prolonged outage

---

# 75. MySQL Integration Drills

The agent itself does not connect to MySQL.

However, end-to-end tests must validate agent behavior while the central server experiences:

* MySQL unavailable
* MySQL restart
* heartbeat transaction failure
* API readiness failure caused by MySQL
* API recovery after MySQL returns

The agent should observe these only as bounded HTTP failures/retries.

It must never attempt direct database connectivity.

---

# 76. Required Manual Failure Drills

Before production deployment, test a real Linux GPU device with:

```text
agent stopped

agent killed

device reboot

network disconnected

DNS failure

central API stopped

central API restarted

MySQL stopped

MySQL restarted

nvidia-smi unavailable

NVIDIA driver unavailable

GPU missing

nvidia-smi hanging

credential revoked

credential rotated
```

Verify the complete path:

```text
Agent
  ↓
Server
  ↓
MySQL
  ↓
Availability/GPU decision
  ↓
Incident
  ↓
Email/SMS
  ↓
Dashboard
```

---

# 77. 24-Hour Soak Test

Run the agent for at least:

```text
24 hours
```

under normal conditions and selected induced failures.

Verify:

* memory remains bounded
* process count remains bounded
* no zombie accumulation
* CPU remains acceptable
* network traffic remains acceptable
* logs remain bounded
* heartbeat timing remains stable
* recovery works after connectivity loss

---

# 78. Agent Production Release Gate

The agent is ready for V1 production deployment only when:

* installation succeeds on supported Ubuntu target
* service starts on boot
* service runs unprivileged
* heartbeat reaches production-like server
* CPU/RAM/disk telemetry is correct
* NVIDIA telemetry is correct
* multiple GPU parsing works
* `nvidia-smi` timeout does not block heartbeats
* network outage does not cause resource growth
* TLS verification is enforced
* credential revocation works
* credential rotation works
* systemd restart works
* SIGTERM is clean
* no secret appears in logs
* 24-hour soak test passes
* real end-to-end offline/recovery alert test passes

---

# 79. Known V1 Limitations

The agent cannot guarantee recovery from:

* kernel-level uninterruptible I/O
* severely broken NVIDIA driver state
* compromised root account
* compromised device credential
* complete central monitoring VM failure
* unsupported GPU/driver combinations

These require operational intervention.

V1 does not hide those limitations through automatic repair.

---

# 80. Implementation Priority

Because V1 has a short delivery timeline, implementation should occur in this order:

```text
1. Configuration + identity

2. Basic system collector

3. Basic NVIDIA collector

4. Heartbeat contract

5. HTTPS sender

6. systemd deployment

7. Timeout/retry handling

8. GPU failure classification

9. Security hardening

10. Failure/soak testing
```

Do not implement sophisticated edge-case machinery before the basic end-to-end heartbeat path works.

The first milestone is:

```text
Linux GPU machine
      ↓
Agent
      ↓
HTTPS
      ↓
FastAPI
      ↓
MySQL
      ↓
Dashboard
```

The second milestone is:

```text
Stop/disconnect device
      ↓
Server detects outage
      ↓
Incident created
      ↓
Notification sent
```

Then harden the implementation against the failure cases defined in this specification.

---

# 81. V1 Agent Success Criteria

The agent succeeds when it reliably answers:

```text
Who am I?

Can I contact the monitoring server?

What is my current CPU usage?

What is my current memory usage?

What storage is being monitored?

Which NVIDIA GPUs can I currently observe?

What are their current metrics?

Did nvidia-smi fail?

Can I keep reporting system telemetry when GPU telemetry fails?
```

Everything beyond those responsibilities belongs either to the central server or to a future product stage.
