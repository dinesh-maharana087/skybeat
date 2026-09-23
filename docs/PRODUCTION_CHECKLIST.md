# SkyBeat V1 Production Checklist

Use this checklist for an operator-controlled deployment. It does not authorize production changes by itself.

## Automatically verified in the repository

- Server and agent tests, static checks, migration graph, and whitespace checks recorded in `IMPLEMENTATION_STATUS.md`.
- `python scripts/validate_deployment.py` confirms required Compose, Caddy, Dockerfile, and systemd artifacts without starting infrastructure.
- Production configuration rejects unsafe timing, placeholder secrets, weak all-identical Fernet keys, and SMS enabled without an approved provider adapter.
- Compose exposes only Caddy ports 80/443; MySQL, API, and worker have no host port mapping.
- API and worker do not run migrations automatically; `migrate` is a profile-gated explicit service.

## Required before a production release

- [ ] Ubuntu 24.04 host is patched, time-synchronised, and has Docker Engine/Compose installed.
- [ ] DNS points the approved hostname at the host; firewall allows only intended 80/443 and restricted operator SSH.
- [ ] `/opt/skybeat/.env` is copied from `deployment/production.env.example`, root-owned mode 0600, absent from Git, and contains non-placeholder runtime, migration, MySQL, OIDC, SMTP, and Caddy values.
- [ ] Separate scoped MySQL runtime, migration, and backup accounts are provisioned; no application URL uses MySQL root.
- [ ] A current encrypted/off-host database backup exists and its restore procedure has been reviewed.
- [ ] `docker compose --env-file .env config -q` succeeds before services are started.
- [ ] Current Alembic revision is inspected, migration is explicitly run, and `a58c71d904ef` is confirmed as the only head.
- [ ] `/livez` and `/readyz` pass from the API container; public Caddy routing does not expose those endpoints.
- [ ] TLS, HTTP-to-HTTPS redirect, Google login, allowed-user policy, agent heartbeat, and dashboard access are verified from the intended network.
- [ ] A controlled OFFLINE/RECOVERED drill, GPU confirmation drill, SMTP drill, and no-network SMS behavior are verified.
- [ ] At least one agent service starts after reboot and a canary upgrade/rollback procedure has been exercised.
- [ ] Backup restore, 24-hour soak, and representative 100-device load validation are recorded before broad rollout.

## Environment-dependent checks not established by local tests

- Real MySQL 8.x/InnoDB migration, locking, reconnect, and worker restart behavior.
- Docker image build/run, Compose rendering, network isolation, log rotation, and persistent-volume behavior.
- Linux systemd sandbox compatibility with host telemetry and NVIDIA access.
- Caddy certificate issuance, TLS, DNS, reverse proxy, and firewall behavior.
- Real NVIDIA, SMTP, selected SMS provider, backup restore, load, and soak behavior.
