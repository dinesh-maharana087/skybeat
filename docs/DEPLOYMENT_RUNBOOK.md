# SkyBeat Deployment Runbook

This runbook is an operator procedure. It does not authorize production changes, credential rotation, firewall changes, database resets, or destructive recovery actions without the required approval.

## Development-validation baseline

Stage 06 development validation used a Windows development/server environment, isolated MySQL 8.4.10 on loopback port 3307, FastAPI on port 8000, and Caddy HTTPS on port 443. Those are validation details only; production must use its approved hostname, private database network, and firewall policy rather than depending on those addresses or ports.

Operator-supplied Stage 06 acceptance evidence recorded a successful Ubuntu GPU-agent heartbeat through Caddy, FastAPI, and MySQL. The device used an NVIDIA GeForce RTX 5080 with driver 595.84 and CUDA 13.2 reported by `nvidia-smi`; current device/latest/receipt/sample records showed ONLINE, GPU OK, CPU, memory, hostname, and GPU-summary telemetry. This evidence contains no credentials, tokens, private addresses, or raw telemetry.

## Local dashboard visual acceptance

This procedure is for local development only. It is not a production login
mechanism and it does not replace Google OIDC. In a protected, ignored local
environment file, set both values below, restart the local API, and confirm the
prominent `DEVELOPMENT DASHBOARD AUTH BYPASS ENABLED` startup warning:

```text
SKYBEAT_ENV=development
SKYBEAT_DEV_AUTH_BYPASS=true
```

Open the existing local dashboard origin and verify the sidebar/header/live
freshness indicator, overview cards, projects, filters, inventory table, device
drawer, GPU detail, history ranges, keyboard focus, Escape/close paths, and
responsive presentation at desktop, tablet, and narrow widths. Create a project,
then enroll a device and copy its one-time credential only into the protected
agent environment file. Do not record the credential in screenshots, notes,
shell history, URLs, browser storage, or logs. Close the enrollment dialog and
confirm the credential is no longer displayed. Confirm project reassignment and
enable/disable monitoring only through their explicit confirmation dialogs, then
verify the canonical dashboard refreshes.

Disable this local convenience by setting `SKYBEAT_DEV_AUTH_BYPASS=false` or
removing it, then restarting the API. Production configuration rejects the
bypass flag; when it is off, the existing Google OIDC and opaque-session flow
remains required. Do not change retained MySQL ACLs/data, reset MySQL, or use
this local procedure as a production deployment instruction.

## Local Google OIDC and Owner acceptance

This is the real local authentication path used for the Pre-Stage 11
acceptance prerequisite. It does not enable the development bypass, create an
Owner from Google claims, or change the application's OIDC/session design.
The application intentionally reads process environment variables; it does
not load `.env` automatically.

In the protected, Git-ignored repository-root `.env`, configure the existing
variables below. Use an exact email allowlist or an approved Google Workspace
hosted-domain admission policy. The future Owner must satisfy that admission
policy before it can sign in.

```text
SKYBEAT_ENV=development
SKYBEAT_DATABASE_URL=mysql+pymysql://<scoped-user>:<url-encoded-password>@127.0.0.1:3306/<database>?charset=utf8mb4
SKYBEAT_PUBLIC_BASE_URL=http://localhost:8000
SKYBEAT_ALLOWED_HOSTS=localhost,127.0.0.1
SKYBEAT_AGENT_SERVER_URL=https://<laptop-private-ip>:8000
SKYBEAT_ALLOW_INSECURE_LOCAL_AGENT_SERVER=false
SKYBEAT_ALLOWED_EMAILS=<YOUR_ADMIN_EMAIL>
# Or, only when an approved Workspace domain policy is appropriate:
# SKYBEAT_ALLOWED_DOMAINS=example.com
SKYBEAT_DEV_AUTH_BYPASS=false
SKYBEAT_GOOGLE_CLIENT_ID=<GOOGLE_WEB_CLIENT_ID>
SKYBEAT_GOOGLE_CLIENT_SECRET=<GOOGLE_WEB_CLIENT_SECRET>
SKYBEAT_SESSION_ENCRYPTION_KEY=<FERNET_KEY>
```

Do not put actual values in source, shell history, logs, screenshots, or
documentation. `SKYBEAT_ALLOWED_EMAILS`/`SKYBEAT_ALLOWED_DOMAINS` are an OIDC
admission gate only: they do not assign a SkyBeat role.

For Windows local development, the repository launcher imports the protected
repository-root `.env` into its own child process; it does not change the
application's production environment-loading behavior. It ignores blank lines
and comments, preserves `=` within values, and never prints secret values.
Run its non-secret preflight before starting the server:

```powershell
Set-Location D:\learning\skybeat\skybeat
PowerShell -ExecutionPolicy Bypass -File .\start-skybeat-local.ps1 -PreflightOnly
```

For the preferred HTTPS path, expected output identifies the loopback Uvicorn
listener, the agent HTTPS endpoint, Caddy TLS termination, and `Configuration:
OK`. The launcher validates and starts Caddy before exposing the endpoint; it
never prints Google, SMTP, database, session, enrollment, or other secret
values. It rejects a non-development `.env`, a malformed agent origin, or a
failed Settings/Caddy preflight.

`SKYBEAT_PUBLIC_BASE_URL` remains the browser/OIDC callback origin;
`SKYBEAT_AGENT_SERVER_URL` is the agent-facing origin. They must not be
conflated. For a LAN GPU, set
`SKYBEAT_AGENT_SERVER_URL=https://<laptop-private-ip>:8000` and leave the
insecure HTTP opt-in false. The launcher starts Caddy on that exact private-IP
address and port, with `tls internal`, and proxies only to Uvicorn at
`127.0.0.1:8000`. This allows the existing `http://localhost:8000` Google
callback to remain loopback-only while the GPU reaches the same API through
Caddy HTTPS. Caddy uses the historic repository-sibling `caddy-data` and
`caddy-config` state directories so its existing local CA is preserved; its
root certificate is `../caddy-data/caddy/pki/authorities/local/root.crt`.

The corresponding protected Ubuntu agent configuration keeps the exact HTTPS
URL in `SKYBEAT_SERVER_URL`; do not set
`SKYBEAT_ALLOW_INSECURE_LOCAL_SERVER` for this path. Updating the server's
agent endpoint configuration does not rotate its existing device credential or
re-enroll the device. Ensure Windows allows inbound TCP 8000 on the **Private**
network profile only. Do not create a Public-profile rule or expose this local
development listener to the Internet.

An explicit direct HTTP path remains only for isolated development tests:
`SKYBEAT_AGENT_SERVER_URL=http://<private-or-loopback-ip>:8000` plus
`SKYBEAT_ALLOW_INSECURE_LOCAL_AGENT_SERVER=true`. It binds Uvicorn directly to
`0.0.0.0:8000`, is rejected outside development or for public/hostname/
unspecified addresses, and must never replace the HTTPS path for an installed
agent.

The local Google Cloud Console credential must be a **Web application** OAuth
client with this exact Authorized Redirect URI:

```text
http://localhost:8000/auth/google/callback
```

SkyBeat uses a server-side authorization-code callback and has no browser
Google JavaScript client, so no Authorized JavaScript Origin is required for
this flow. Configure the consent screen with the intended audience and
minimum `openid email` scopes. For an External app in Testing, add the intended
Google account as a Google test user; an Internal app is limited by the
Workspace organization. Google permits a localhost HTTP redirect for local
development, but production must use the approved HTTPS origin.

With the migration already applied to the local development database,
bootstrap the sole Owner before logging in. The command is idempotent for the
same normalized email and rejects an attempt to establish a different Owner:

```powershell
uv run --project server --frozen python -m app.cli --actor local-operator owner-bootstrap --email <YOUR_ADMIN_EMAIL>
```

Start the local API from a fresh PowerShell process; it imports the ignored
repository `.env` for that child process and then starts Uvicorn on its local
development bind:

```powershell
Set-Location D:\learning\skybeat\skybeat
PowerShell -ExecutionPolicy Bypass -File .\start-skybeat-local.ps1
```

Open `http://localhost:8000`, select Google login, and authenticate with the
same Google email used in `owner-bootstrap`. After callback completion,
SkyBeat must resolve the normalized, verified Google email to its active
`application_users` record, bind its Google subject on the first login, and
take the role only from that stored record. Confirm that the Owner dashboard
loads and that the existing Projects, Devices, Users, and authorized device
enrollment workflows are available.

For a negative server-side RBAC check, sign in as an already-provisioned
`USER`, open browser developer tools on the dashboard, and run:

```javascript
fetch("/api/v1/projects", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ name: "unauthorized-rbac-check" })
}).then(async (response) => console.log(response.status, await response.text()))
```

The request must return `403`; no project must be created. Return to the
Owner account afterward and do not use a development-auth bypass as evidence
for this acceptance.

## Server deployment

### Production Google login

SkyBeat uses only the server-side Google authorization-code flow. Users first
visit `/login`, choose **Continue with Google**, and SkyBeat returns them only
to a validated internal path after the callback. Do not send users directly to
the callback endpoint and do not configure a browser Google JavaScript client.

For production, configure a Google **Web application** OAuth client with this
exact redirect URI, replacing the hostname with SkyBeat's configured public
origin:

```text
https://<skybeat-host>/auth/google/callback
```

`SKYBEAT_PUBLIC_BASE_URL` is canonical and must use that HTTPS origin; it is
used to construct the callback URI and is never derived from an incoming Host
header. Production startup rejects `SKYBEAT_DEV_AUTH_BYPASS=true`, non-HTTPS
public URLs, missing Google client settings, missing session encryption key,
and a missing email/domain admission policy. The admission policy only permits
an identity to enter the flow; the current durable `application_users` record
supplies the SkyBeat role. Bootstrap the initial Owner with the documented
`owner-bootstrap` command before its first Google login.

If Google is unavailable, a callback is malformed, or the identity cannot be
admitted/provisioned, SkyBeat returns a safe login-page message without OAuth
codes, tokens, cookie values, secrets, or database details. Login and logout
events are recorded without those sensitive values. Local logout invalidates
the opaque SkyBeat session only; it does not sign the operator out of Google.

After a production configuration change, verify Owner, Admin, User, and an
unauthorized identity in a browser. Confirm that logout in one tab prevents
subsequent protected requests in another tab, and that a disabled or downgraded
durable user loses access on its next request. Real-browser acceptance remains
required; development bypass is never evidence of production login acceptance.

### Prerequisites

Use a supported Linux server with Python 3.12 for direct development operation, MySQL 8.x/InnoDB, Caddy, UTC time synchronization, and a firewall that allows only approved operator access plus Caddy HTTP/HTTPS traffic. Production should use the Stage 06 Docker Compose deployment where available: Caddy is the only public application ingress, while API, worker, and MySQL remain private.

Place the reviewed repository in an operator-controlled directory. Create a protected environment file from `.env.example` for development or `deployment/production.env.example` for Compose production. Keep it outside Git, use non-placeholder values only in production, and do not place secrets in shell history or command lines.

### Database and migrations

Create the database and scoped accounts through an approved MySQL administrator procedure using protected client configuration; do not use MySQL root in application URLs. For a direct development database, the database URL belongs only in the protected environment file.

From `server/`, inspect and apply migrations explicitly:

```sh
python -m alembic current
python -m alembic upgrade head
python -m alembic heads
```

API and worker startup never runs migrations. Before a production migration, complete an approved backup and revision review. Do not resolve a migration failure by resetting a schema, removing a volume, reinitializing MySQL, or automatically downgrading.

### API and Caddy

For direct development startup from `server/`, load protected configuration into the process environment and run the existing application factory:

```sh
python -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
```

Caddy terminates HTTPS and proxies to the private API. Configure the approved hostname in `deployment/caddy/Caddyfile`/protected environment, expose only TCP 80 and 443 as required for redirect/certificate handling, and do not publicly expose MySQL port 3306 or API port 8000. Caddy must remain running; a stopped proxy makes the agent's bounded HTTPS send fail transiently and is not a reason to weaken TLS.

On a direct development API listener, verify process liveness and database/schema readiness from the trusted internal network:

```sh
curl --fail http://127.0.0.1:8000/livez
curl --fail http://127.0.0.1:8000/readyz
```

For the Compose production layout, health endpoints are intentionally checked inside the API container because public Caddy routing returns 404 for them. Do not send public Caddy requests to `/livez` or `/readyz`. A successful `/livez` means the process is running; `/readyz` also verifies bounded MySQL connectivity and schema compatibility without revealing database details.

## Agent deployment

The approved agent installation path is `/opt/skybeat`. The service runs as the least-privilege non-login `skybeat` user; it does not require sudo, Docker access, an inbound listener, or device-project configuration.

1. Use the approved server-side enrollment procedure to create a device and obtain its one-time credential through a protected operator channel. The credential cannot later be recovered as plaintext.
2. Prepare a protected environment file at a secure temporary path using `deployment/systemd/agent.env.example`. Set the server URL, device UUID, and one-time token without printing, echoing, or logging the token.
3. Run the idempotent installer from the reviewed repository as root:

   ```sh
   sudo bash ./scripts/install-agent.sh ./agent /secure/path/agent.env
   ```

4. The installer creates or reuses the `skybeat` system user, creates `/opt/skybeat/venv`, installs the pinned agent package, copies the protected configuration to `/etc/skybeat-agent/agent.env`, installs the committed service unit, reloads systemd, and enables/starts `skybeat-agent.service`.
5. Confirm the final environment file is `root:root` mode `0600`; do not display its contents:

   ```sh
   sudo stat -c '%U:%G %a %n' /etc/skybeat-agent/agent.env
   sudo systemctl status skybeat-agent.service
   sudo journalctl -u skybeat-agent.service --since '10 minutes ago'
   ```

6. Verify a heartbeat through the dashboard/device API or an approved database read procedure. Confirm the device is ONLINE, latest telemetry has a current receipt time, and GPU telemetry is present when GPU monitoring is enabled. Never paste a device credential into a verification command or log.

Log Watch uses the installed `skybeat-agent.service` journal, the system journal, and the journal's kernel view. The agent runs fixed five-minute queries every 120 seconds by default and uploads bounded snapshots independently of heartbeats. It needs the UX.5 database migration (`2f4a6c8d10b2`) before the new agent version is installed. The installer does not change journal group membership or grant sudo; a source the `skybeat` user cannot read is reported as permission unavailable. Review journal visibility on the target Ubuntu host before deciding whether any narrower access is appropriate. Log messages may naturally contain sensitive content; dashboard access and database backups must be protected accordingly.

## TLS and private-CA development

Production agents must validate the certificate chain, hostname, and validity period. Public/system-trusted certificates are preferred for production. Never use `verify=False` or an equivalent TLS bypass.

For a trusted private-CA development/LAN deployment only:

1. Obtain the Caddy development root certificate through the approved server administrator procedure and transfer it over a protected channel.
2. Install it into the Ubuntu system CA store, then refresh the bundle:

   ```sh
   sudo install -m 0644 /secure/path/skybeat-caddy-root.crt /usr/local/share/ca-certificates/skybeat-caddy-root.crt
   sudo update-ca-certificates
   ```

3. If the local Python/OpenSSL trust behavior still requires the explicit bundle, add this non-secret setting to `/etc/skybeat-agent/agent.env` and restart the service:

   ```text
   SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
   ```

This procedure trusts a locally administered CA; it is not a production substitute for publicly/system-trusted HTTPS. A Caddy outage correctly appears as a bounded transient agent transport failure until the proxy is restored.

## Operations

### Backup and restore

Create daily MySQL backups with a dedicated backup account or protected MySQL client configuration. Keep backups outside the active MySQL volume, retain at least 30 days, and copy them off-host using restricted/encrypted storage where available. Never put a database password in a command line.

Restore only into an isolated MySQL environment first. Verify the Alembic revision, devices, incidents, events, notification records, and a dashboard/heartbeat smoke check before any approved production restoration. Do not overwrite a running production database automatically.

### Upgrade, disable, and rollback

For an upgrade, record the deployed version and revision, complete a backup, validate protected configuration, run the explicit migration procedure, update/restart the API/worker/Caddy services, and perform the smoke checks below. Do not automatically downgrade database schema during application rollback; roll back only to application code compatible with the deployed schema.

To disable an agent without deleting configuration or telemetry, use an approved operator change and stop/disable its systemd unit. To re-enable it, restore the approved service state and verify the first accepted heartbeat. Do not remove device records, credentials, or database history as a disable procedure.

### Safe smoke verification

After a controlled deployment, verify Caddy HTTPS, API `/livez` and `/readyz` from the appropriate trusted path, Google-authorized dashboard access, one agent heartbeat, device ONLINE state, CPU/memory/disk/GPU rendering, and a controlled alert flow where separately approved. Treat unavailable SMTP/SMS, Docker, MySQL, Linux systemd, Caddy/TLS, backup restore, load, and soak checks as environment-specific evidence rather than bypassing safety controls.
