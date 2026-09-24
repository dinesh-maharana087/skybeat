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

## Server deployment

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
