# Stage 12J-P: internal Ubuntu pilot runbook

Status on 2026-10-14: **release candidate prepared; NO GO for a canary**. This
is an operator procedure for use after the server and Ubuntu gates are cleared.
It is not authorization to install on a device, issue a token, change a firewall,
or send notifications. Stage 12J and Stage 12JA remain unaccepted.

## Go gates and server preparation

1. The isolated pilot candidate is `skybeat-agent-1.0.5` at
   `release-12jp1/skybeat-agent-1.0.5`; its ZIP SHA-256 is
   `0796c3037908b1114d4773cb923b5e6bc1ffe92355016e9d6446cd048659eb3a`.
   It passed local bundle/archive verification and an isolated WSL package
   command check, not real-device systemd or telemetry acceptance. After
   OWNER/ADMIN review, set this exact line in the
   protected Windows `.env` and restart the API through the existing launcher:

   ```text
   SKYBEAT_AGENT_RELEASE_DIR=D:\learning\skybeat\skybeat\release-12jp1\skybeat-agent-1.0.5
   ```

   The setting selects the **absolute extracted bundle directory**, not its
   parent or ZIP. Do not change the live `.env` or restart processes as part of
   this preparation. The server checks the format-2 manifest, locked
   wheelhouse, every declared file hash, exact file
   set, wheel identity, and matching ZIP before serving it. Confirm that the
   authenticated Deployments page offers **Agent Package** and **Copy
   Instruction** on a `READY` card. `TOKEN EXPIRED` cards remain disabled;
   create a fresh per-device intent. Do not use the old 1.0.0 bundle as the
   server-approved release: the current server rejects its format-1 manifest.
2. The 1.0.5 installer stages the root-owned updater units and reloads systemd,
   but does not enable, start, stop, or disable the timer. A fresh install stays
   inactive; an upgrade preserves the timer's existing state. Check that the
   timer is disabled/inactive **before and after** any pilot install. Explicit
   operator activation remains available only after Stage 12JA acceptance.
   The earlier 1.0.4 archive enables the timer and must not be selected for
   this isolated pilot. A matching 1.0.5 digest alone is not live acceptance.
3. Start the existing local server only under its reviewed launcher after
   checking worker ownership and notification recipients. The launcher
   preflight is `powershell -NoProfile -ExecutionPolicy Bypass -File
   .\start-skybeat-local.ps1 -PreflightOnly`. After operator approval, run the
   same command without `-PreflightOnly`; in a separate PowerShell window,
   `Invoke-WebRequest http://127.0.0.1:8000/readyz -UseBasicParsing` must
   return 200. Confirm the launcher's worker ownership check reports a
   launcher-owned `python -m app.worker` process, then verify that a CA-checked
   request to `<AGENT_HTTPS_ORIGIN>/api/v1/agent-releases/current` returns 401
   without a dashboard session. In an authorized OWNER/ADMIN browser session,
   the same metadata route should return 200 and the `READY` card actions
   should enable. Verify that Google login admits only authorized users, and
   review notification routing and worker delivery state without sending an
   unapproved test notification.
   Do not enable development authentication bypass.
4. Keep the agent origin stable. The current laptop uses Wi-Fi DHCP, so arrange
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
5. Transfer the Caddy local root CA through an approved protected channel.
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
