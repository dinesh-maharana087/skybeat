# Stage 12J-P: internal Ubuntu pilot runbook

Status on 2026-10-14: **release management implemented locally; NO GO for a canary**. This
is an operator procedure for use after the server and Ubuntu gates are cleared.
It is not authorization to install on a device, issue a token, change a firewall,
or send notifications. Stage 12J and Stage 12JA remain unaccepted.

## Go gates and server preparation

1. Build → Verify → Register → Approve/Activate → Distribute. The isolated
   candidate is `release-12jp1/skybeat-agent-1.0.5` with its sibling ZIP;
   ZIP SHA-256 is
   `0796c3037908b1114d4773cb923b5e6bc1ffe92355016e9d6446cd048659eb3a`.
   It passed local format-2 verification, not real-device acceptance. Build
   future versions with `scripts/build-agent-release.sh` and verify with
   `scripts/verify-agent-release.py`; never alter an approved artifact in place.
   During an approved maintenance window, configure the protected `.env` **once**
   with an absolute `SKYBEAT_AGENT_RELEASE_STORE` directory. On this Windows
   checkout, a suitable reviewed value is
   `D:\learning\skybeat\skybeat\release-store`; create its `incoming` directory
   with access limited to the SkyBeat operator and API account. For Compose,
   configure `RELEASE_STORE_HOST_DIR` as a protected host directory mounted at
   `/var/lib/skybeat/agent-releases`, and set `SKYBEAT_AGENT_RELEASE_STORE` to
   that container path. Preserve this store across restarts and backups.
   The old `SKYBEAT_AGENT_RELEASE_DIR` is no longer the selection control.
2. Confirm `alembic current` and `alembic heads` both report `93f20b4c17d6`
   for the intended database. Read-only inspection on 2026-10-14 found that
   revision in local development, with both release tables, zero registered
   releases, and no active selection. Recheck before starting services. The
   launcher never migrates; its `-PreflightOnly` checks settings, database,
   schema, release status, and Caddy configuration without starting services.

### Local development migration recovery after MySQL error 3818

The first attempted upgrade created `agent_releases` before MySQL rejected the
`agent_release_selection` CHECK on an auto-increment key. The operator cleared
the empty partial table and subsequently applied the corrected migration.
The latest read-only inspection found local schema `skybeat` at
`93f20b4c17d6` with both release tables. **Do not rerun the local upgrade.**
The following checks and guarded retry apply only to a separately lagging
database after its own state and backup have been reviewed.

In a MySQL client already connected to the intended local development schema,
check the database name, revision, tables, and any rows:

```sql
SELECT DATABASE(), VERSION();
SELECT version_num FROM alembic_version;
SELECT table_name FROM information_schema.tables
  WHERE table_schema = DATABASE()
    AND table_name IN ('agent_releases', 'agent_release_selection');
SELECT table_name, column_name, referenced_table_name
  FROM information_schema.key_column_usage
  WHERE table_schema = DATABASE()
    AND referenced_table_name IN ('agent_releases', 'agent_release_selection');
```

If either release table exists while the revision is still `4ab92d1e7c30`,
inspect its rows and DDL and stop for a reviewed recovery decision. Preserve
a verified backup. Do not drop any table, downgrade, stamp, or disable CHECK
enforcement. Only when a separately approved target remains at
`4ab92d1e7c30` and both release tables are absent may its operator run the
migration. From `server/`, Alembic reads the dedicated
`SKYBEAT_MIGRATION_DATABASE_URL` from the root `.env` automatically:

```powershell
& ..\.venv\Scripts\python.exe -m alembic current
& ..\.venv\Scripts\python.exe -m alembic heads
# Only after the identity, state, backup, and migration are approved:
& ..\.venv\Scripts\python.exe -m alembic upgrade 93f20b4c17d6
& ..\.venv\Scripts\python.exe -m alembic current
```

The final command must report `93f20b4c17d6`. In the same MySQL client, verify
the seeded row, non-autoincrement key, and enforced CHECK before starting the API:

```sql
SELECT COUNT(*) AS rows_found, MIN(id) AS minimum_id, MAX(id) AS maximum_id
  FROM agent_release_selection;
SELECT extra FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'agent_release_selection'
    AND column_name = 'id';
SELECT enforced FROM information_schema.table_constraints
  WHERE table_schema = DATABASE() AND table_name = 'agent_release_selection'
    AND constraint_name = 'ck_agent_release_selection_singleton';
```

Expect `1, 1, 1`, an empty `extra`, and `YES`. We can confirm only the
configured local database; independently check every shared environment before
deploying this edited revision. If this revision has completed in a shared
environment, prepare a reviewed forward corrective migration for it.

### Windows operator validation after the approved local migration

In a first PowerShell window, from the repository root, run the supported
launcher. It reads the root `.env`, checks the runtime schema, reports release
store and registry status, and starts or reuses only an owned worker and API:

```powershell
Set-Location D:\learning\skybeat\skybeat
$env:SKYBEAT_AGENT_RELEASE_STORE = Join-Path $env:LOCALAPPDATA 'SkyBeat\agent-releases'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start-skybeat-local.ps1 -PreflightOnly
# After the protected release store and candidate are staged as described below:
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start-skybeat-local.ps1
```

Keep that window open. In a second PowerShell window, run read-only service
checks. The launcher prints the actual local dashboard and agent HTTPS URLs;
use those rather than assuming a fixed LAN address:

```powershell
Set-Location D:\learning\skybeat\skybeat
$env:SKYBEAT_AGENT_RELEASE_STORE = Join-Path $env:LOCALAPPDATA 'SkyBeat\agent-releases'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start-skybeat-local.ps1 -VerifyRunning
Invoke-WebRequest -UseBasicParsing -Uri http://127.0.0.1:8000/readyz
```

`-VerifyRunning` checks both API health endpoints, validates the worker PID and
ownership state, and probes the Caddy HTTPS `/livez` endpoint with normal TLS
validation. A Caddy 502 points to API upstream readiness; a TLS trust failure
requires certificate/CA review. Then use the printed local dashboard URL to
complete Google OIDC login and inspect `/dashboard/releases`. Confirm that the
active installation release is unchanged; startup never activates one. The
protected local `.env` currently names a Linux container path, so this
process override must be set in every PowerShell window that launches or
checks SkyBeat until an operator corrects the protected configuration. An
explicit value always wins over the per-user development default. No Ubuntu
agent action is part of this validation.

Run these commands in the first PowerShell window before the normal launcher.
Confirm the ACL grants write access only to the operator and API account. The
commands refuse to overwrite existing staged bytes:

```powershell
Set-Location D:\learning\skybeat\skybeat
$store = Join-Path $env:LOCALAPPDATA 'SkyBeat\agent-releases'
$env:SKYBEAT_AGENT_RELEASE_STORE = $store
$data = Split-Path $store -Parent
$incoming = Join-Path $store 'incoming'
$bundle = Resolve-Path .\release-12jp1\skybeat-agent-1.0.5
$zip = Resolve-Path .\release-12jp1\skybeat-agent-1.0.5-linux.zip
& .\.venv\Scripts\python.exe scripts\verify-agent-release.py --bundle $bundle
foreach ($directory in @($data, $store, $incoming)) {
  if (Test-Path -LiteralPath $directory) {
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) { throw 'A storage path is not a directory.' }
  } else { New-Item -ItemType Directory -Path $directory | Out-Null }
}
Get-Acl -LiteralPath $store | Select-Object -ExpandProperty Access |
  Select-Object IdentityReference, FileSystemRights, AccessControlType
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start-skybeat-local.ps1 -PreflightOnly
$stagedBundle = Join-Path $incoming 'skybeat-agent-1.0.5'
$stagedZip = Join-Path $incoming 'skybeat-agent-1.0.5-linux.zip'
if ((Test-Path -LiteralPath $stagedBundle) -or (Test-Path -LiteralPath $stagedZip)) { throw 'Staging already exists; inspect it before copying.' }
Copy-Item -LiteralPath $bundle -Destination $stagedBundle -Recurse
Copy-Item -LiteralPath $zip -Destination $stagedZip
$actual = (Get-FileHash -LiteralPath $stagedZip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne '0796c3037908b1114d4773cb923b5e6bc1ffe92355016e9d6446cd048659eb3a') { throw 'Staged ZIP SHA-256 mismatch.' }
$actual
```

The final digest must equal
`0796c3037908b1114d4773cb923b5e6bc1ffe92355016e9d6446cd048659eb3a`.
After the server starts, authenticate as OWNER/ADMIN, open
`/dashboard/releases`, register `skybeat-agent-1.0.5`, review verification and
digests, and explicitly activate it. Refresh `/dashboard/deployments`; one
eligible READY card should show `Agent version: v1.0.5` with both actions
enabled. Download Agent Package in the browser and compare its ZIP SHA-256
against the approved archive digest shown in Release Management. A `TOKEN
EXPIRED` card remains disabled. Registration and activation never install or
upgrade an enrolled device.
3. On a valid `READY` enrollment, confirm **Agent Package** and **Copy
   Instruction** are enabled. Download through the authenticated existing
   route and compare its SHA-256 with the registered ZIP digest. `TOKEN EXPIRED`
   cards remain disabled regardless of release state; any new intent requires
   separate authorization. Do not use the old format-1 1.0.0 bundle.
4. If a later active release is defective, verify that a previously approved
   artifact is still available, then explicitly activate that digest for
   **future installations**. This does not downgrade or upgrade running agents,
   alter device credentials, or issue a lifecycle operation. Treat any device
   rollback as a separate Stage 12J authorization.
5. The 1.0.5 installer stages the root-owned updater units and reloads systemd,
   but does not enable, start, stop, or disable the timer. A fresh install stays
   inactive; an upgrade preserves the timer's existing state. Check that the
   timer is disabled/inactive **before and after** any pilot install. Explicit
   operator activation remains available only after Stage 12JA acceptance.
   The earlier 1.0.4 archive enables the timer and must not be selected for
   this isolated pilot. A matching 1.0.5 digest alone is not live acceptance.
6. Keep the agent origin stable. The current laptop uses Wi-Fi DHCP, so arrange
   a LAN reservation or a reviewed stable hostname, then verify that the
   configured HTTPS origin, Caddy listener, certificate SAN, and Ubuntu route
   all name the same endpoint. The intended inbound rule, if needed after a
   failed canary network probe, is **TCP 8000, Private profile, Caddy only,
   remote address limited to the trusted pilot LAN/subnet**. Obtain operator
   approval before adding a rule; do not expose the API or port to the public
   internet. Caddy proxies to `127.0.0.1:8000`. After the CA transfer below,
   test from Ubuntu with
   `curl --cacert /path/to/verified-root.crt
   <AGENT_HTTPS_ORIGIN>/api/v1/agent-releases/current`; a 401 response confirms
   the protected endpoint is reachable through verified TLS.
7. Transfer the Caddy local root CA through an approved protected channel.
   Its Windows source is `..\caddy-data\caddy\pki\authorities\local\root.crt`.
   Verify the root fingerprint through a separate trusted channel, then install
   it in the Ubuntu system trust store under the operator's device change
   approval. Confirm that the served leaf SAN matches `<AGENT_HTTPS_ORIGIN>`
   and that the intermediate chain validates. Do not use `curl -k`,
   `verify=False`, or direct HTTP.

## One authorized canary

Use **Ubuntu 24.04 LTS amd64/x86_64 with systemd, Python 3.12, curl,
sha256sum, and unzip**. The current installer rejects other versions and
architectures. Check `nvidia-smi` availability separately; missing NVIDIA
hardware is an observed GPU state, not an installation failure.

1. An OWNER/ADMIN creates one `NEW` enrollment for the intended project and
   device name and saves the one-time token file immediately. The token is
   disclosed only on creation, expires after 24 hours, and is consumed on
   exchange. Transfer it and the dashboard-downloaded approved ZIP to the
   intended machine through separate protected paths. Never put the token in
   shell history, a URL, a ticket, or a unit. For an existing operational
   device, use a reviewed token-free install with its **unchanged** server URL;
   never create a `NEW` enrollment or pass `--re-enroll` for an upgrade.
2. On Windows, record `Get-FileHash -Algorithm SHA256 <approved-ZIP>` and
   communicate the digest through a trusted channel. On Ubuntu, compare
   `sha256sum <approved-ZIP>` to that value. Then run:

   ```sh
   unzip <approved-ZIP>
   cd <archive-root-from-dashboard>
   python3.12 ./verify-agent-release.py --bundle .
   sha256sum -c wheel.sha256
   sudo install -d -m 0700 -o root -g root /root/skybeat
   sudo install -m 0600 -o root -g root /secure-transfer/enrollment.token /root/skybeat/enrollment.token
   ```

   Stop if the ZIP, bundle, wheel, or chain fails validation. Do not alter the
   extracted installer or fetch missing wheels from a package index.
3. Copy the exact **Copy Instruction** text for this release, replace only its
   `--token-file ./enrollment.token` argument with
   `--token-file /root/skybeat/enrollment.token`, and execute it with `sudo`
   from the extracted bundle. The supported form is:

   ```sh
   sudo ./install-agent.sh --server <AGENT_HTTPS_ORIGIN> \
     --package ./<manifest-wheel-filename> --sha256 <manifest-wheel-sha256> \
     --wheelhouse ./wheelhouse --lockfile ./requirements.lock \
     --token-file /root/skybeat/enrollment.token
   ```

   If the exchange result is uncertain, inspect the enrollment state first;
   never replay the same token blindly. After a confirmed exchange, securely
   remove the token file with `sudo shred -u /root/skybeat/enrollment.token`.
   A healthy repeat install uses the same exact bundle
   and command **without any token option** and reports `ALREADY_CURRENT`.
4. Confirm the active unit runs as `skybeat`, loads root-owned mode-0600
   `/etc/skybeat/agent.env`, and invokes
   `/opt/skybeat/venv/bin/skybeat-agent`:

   ```sh
   sudo systemctl is-enabled skybeat-agent.service
   sudo systemctl is-active skybeat-agent.service
   sudo systemctl show -p User -p Group -p ExecStart -p MainPID skybeat-agent.service
   sudo stat -c '%U:%G %a %n' /etc/skybeat/agent.env
   sudo journalctl -u skybeat-agent.service --since '10 minutes ago' --no-pager
   sudo systemctl is-enabled skybeat-updater.timer
   sudo systemctl is-active skybeat-updater.timer
   ```

   The updater timer must be disabled and inactive for this pilot. Do not issue
   a lifecycle operation. Do not display `agent.env` or raw authorization
   headers. Use the dashboard and server events to corroborate the first
   accepted heartbeat before considering the install complete.

## Canary acceptance record

Record timestamps, the device UUID, safe status outputs, dashboard screenshots,
and incident/delivery IDs. Do not record tokens, credentials, or raw private
logs. Keep the normal availability thresholds: `ONLINE` below 75 seconds,
`SUSPECT` from 75 to under 180 seconds, `OFFLINE` at 180 seconds or more;
the health sweep is approximately every 5 seconds.

| Check | Execute and expected result | Evidence | Safe recovery |
|---|---|---|---|
| Enrollment | Exchange one fresh `NEW` intent; one durable UUID appears. | Enrollment state and Device Detail UUID; no second device. | Inspect state; issue a new intent only after an uncertain/expired exchange is resolved. |
| Service and restart | Check `systemctl is-active`, run `sudo systemctl restart skybeat-agent.service`, then check again; after approved reboot, confirm it starts at boot under `skybeat`. | Unit properties, PID, bounded journal after restart/boot. | Inspect journal and unit; use verified token-free installer repair or its local rollback path. |
| Heartbeats | Wait for at least two fresh periods; Last Seen advances. | Device Detail timestamps and server accepted-heartbeat records. | Verify DNS/route, TLS, token validity, and service logs without printing secrets. |
| Dashboard identity | Confirm one device under the intended project and name. | Device Detail UUID and project/name screenshot. | Stop; reconcile enrollment and server-controlled metadata before another intent. |
| OS, CPU, memory | Confirm Ubuntu version/hostname plus fresh CPU and memory telemetry. | Device Detail system/telemetry fields. | Inspect collector status and heartbeat rejection category. |
| GPU | If NVIDIA hardware is present, confirm GPU UUID/state and metrics; otherwise show an honest missing/not-monitored state. | Device Detail GPU fields and safe local `nvidia-smi` status. | Inspect fixed-command collector errors; do not change drivers for this pilot. |
| Diagnostics | Check permitted agent, systemd, and kernel sources reach Log Watch. | Log Watch source status and bounded records. | Inspect collection/upload state and rate limits; do not expose raw sensitive logs. |
| Offline and recovery | With operator approval, stop communication long enough for normal thresholds, then restore it. Expect one outage and one recovery. | State timestamps, incident/event IDs, then fresh heartbeat. | Restore service/network; investigate duplicate or missing incidents before proceeding. |
| Notifications | Confirm intended recipients and applicable delivery states for the approved test event. | Durable delivery/attempt state and recipient mailbox confirmation. | Fix worker/SMTP routing; do not repeat an alert blindly. |
| Security | Inspect redacted logs/dashboard and config permissions; no plaintext credential appears. | Mode/owner output and bounded redacted samples. | Secure the exposure and rotate only through a separately approved response. |
| Resources | Observe agent CPU, memory, and journal volume over the canary window; behavior stays bounded. | `systemctl status`, `ps`/`top`, journal size and cadence. | Stop rollout, inspect collector timeouts/batching, and disable the service if needed. |
| Isolation | Timer remains disabled/inactive; no lifecycle intent, upgrade, or re-enrollment appears. | `systemctl` timer state and server lifecycle/audit view. | Stop the timer and pause pilot; preserve identity and investigate before resuming. |

## Expansion, rollback, and troubleshooting

After the first canary passes and an operator approves expansion, repeat the
same release verification and **one new enrollment per machine**. Transfer each
machine's token only to that machine. Check project/name/UUID, service, fresh
telemetry, diagnostics, and timer state before preparing the next device.

For connectivity failures, test the configured host and port from Ubuntu,
then `curl --cacert /path/to/verified-root.crt
<AGENT_HTTPS_ORIGIN>/api/v1/agent-releases/current`. A `401` proves the
protected HTTPS route is reachable without a dashboard session; `502` means
Caddy cannot reach the local API. A certificate error requires checking SAN,
clock, root trust, and intermediate chain. An enrollment `401` may mean an
expired/consumed token; inspect its state rather than retrying an uncertain
exchange. Use `journalctl -u skybeat-agent.service` and server-side safe error
categories for agent failures.

To pause monitoring on an authorized device, use
`sudo systemctl disable --now skybeat-agent.service` and confirm the resulting
availability/notification consequences with the operator. Leave the protected
identity and credential file intact. For a failed release change, use the
verified previous bundle with the same server origin and **no enrollment
options**; the installer also has local rollback for a failed switch. Do not
delete `/etc/skybeat/agent.env`, remove old environments, rotate credentials,
or attempt managed rollback during this pilot. Record the rollback result and
pause further devices for review.
