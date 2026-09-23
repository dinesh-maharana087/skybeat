# Stage 06 Deployment and Production Hardening Design

Status: approved for implementation on 2026-09-23.

## Scope

Stage 06 makes the accepted SkyBeat server reproducibly deployable on one Ubuntu VM. It does not add monitoring product features, database migrations, a real SMS vendor, remote operations, or automatic database changes.

The central server runs through Docker Compose with `caddy`, `api`, `worker`, and `mysql`. A `migrate` service is invoked explicitly by an operator. Agents remain direct Python/systemd installations.

## Central deployment

`deployment/docker/Dockerfile.server` builds one Python 3.12 application image from the locked server dependencies. The image runs as an unprivileged `skybeat` user. Compose uses it for API, worker, and explicit migration commands, with separate entry points.

`docker-compose.yml` defines two internal networks:

- `edge`: Caddy and API only.
- `data`: API, worker, migration job, and MySQL only.

Only Caddy publishes host ports 80 and 443. API, worker, and MySQL publish no host ports. MySQL data and Caddy certificate/configuration state use named persistent volumes. Application containers have read-only root filesystems and bounded writable temporary filesystems where compatible. Docker logs rotate at 10 MiB with five retained files.

The API and worker do not run Alembic automatically. The production procedure requires backup, configuration validation, revision inspection, the explicit `migrate` profile/service, head verification, service start/restart, health checks, and smoke checks. No artifact initializes, resets, drops, or downgrades an existing database.

## Configuration and runtime behavior

Production validation rejects placeholders, missing protected secrets, unsafe host/origin settings, malformed recipients, and invalid availability timing. Availability thresholds become validated settings with the existing 75-second suspect and 180-second offline defaults; the offline threshold must exceed the suspect threshold. Notification polling becomes a validated setting with a production deployment value of two seconds, without scattering timer constants in worker code.

The API retains its existing `/livez` and bounded `/readyz` endpoints. The response remains minimal and does not reveal database details. Caddy applies the 128 KiB heartbeat-compatible request body limit and HTTPS proxying. Application containers do not trust arbitrary forwarded client headers; Caddy remains the sole public ingress.

The worker receives signal-aware bounded shutdown handling: it stops scheduling new work and disposes database resources cleanly. Durable deliveries remain in MySQL and existing lease/retry logic continues to recover work after restart.

## Agent deployment

The repository provides an agent environment-file example and a systemd unit using `/opt/skybeat-agent`, `/etc/skybeat-agent/agent.env`, and a dedicated non-login `skybeat` user. The unit uses `Restart=on-failure`, a bounded restart delay, a restrictive umask, `NoNewPrivileges`, `PrivateTmp`, `ProtectHome`, and conservative filesystem protection that does not block NVIDIA telemetry. Agent secrets stay in a root-owned 0600 environment file and are never put in command lines or source control.

## Operations documentation

The canonical deployment guide and README will describe prerequisites, protected environment files, Docker network exposure, migration/upgrade procedure, health and smoke checks, agent installation, backup and isolated restore verification, logs, troubleshooting, and a concise checklist separating automatic checks from real-environment validation.

No backup script accepts database passwords on the command line. The documentation provides a safe operator procedure instead of automated destructive restore/rollback behavior.

## Verification

Focused tests cover production configuration, timing validation, worker signal/shutdown behavior, and deployment-artifact invariants. The full server and agent suites, Ruff, formatting, strict mypy, Alembic history/head, diff whitespace, and available Compose/Docker validation run before acceptance.

Real MySQL, Docker daemon/image execution, Linux systemd, Caddy/TLS/DNS, NVIDIA hardware, SMTP, SMS provider, firewall, backup restore, load, and soak tests are recorded as environment-pending unless exercised in a suitable isolated environment. The retained local MySQL data and its ACLs are never changed.
