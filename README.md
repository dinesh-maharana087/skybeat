# SkyBeat V1

SkyBeat is a standalone Linux/GPU monitoring and alerting platform for an initial fleet of up to 100 devices on one Ubuntu VM. The approved design uses FastAPI, a separate worker, MySQL 8.x/InnoDB, lightweight Python agents, and a same-origin Jinja2 dashboard behind Caddy. SkyBeat observes device health; it does not execute remote commands or repair devices.

Implementation is in progress. Stage 01 provides the server foundation, database migrations, and a restricted local device-management CLI. Heartbeats, the agent, alerts, dashboard authentication, and deployment hardening belong to subsequent stages. See [implementation status](docs/IMPLEMENTATION_STATUS.md) for verified progress and limitations, and [the approved plan](docs/IMPLEMENTATION_PLAN.md) for stage acceptance criteria. This development setup is not a production rollout.

## Local development

Use Python 3.12 and an isolated MySQL 8.x instance with InnoDB and `utf8mb4`. Provision a dedicated development database and scoped account before running migrations. The application refuses root database credentials. Keep database access private. SQLite does not establish MySQL transaction or locking correctness.

From the repository root, the following example uses a POSIX shell:

```sh
uv venv --python 3.12
. .venv/bin/activate
uv pip sync --require-hashes server/requirements.lock
cp .env.example .env
chmod 600 .env
```

Edit the protected `.env` with the development account's connection URL. URL-encode special characters in the password. Do not put a password or device token in a command-line argument. The application reads environment variables; it does not automatically load `.env`. Load a trusted file locally:

```sh
set -a
. ./.env
set +a
cd server
python -m alembic upgrade head
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

On Windows, use `.venv\Scripts\python.exe` and load the corresponding environment variables using a protected local configuration mechanism. Do not paste real secrets into a recorded terminal or shared shell history.

Migrations are explicit and are not run during API startup. Use a schema-scoped migration account for migrations and a separate runtime account with only the required data permissions for deployment. Never reset a database to fix a migration. Upgrading an existing production database requires the separate operational approval and backup procedure described in [AGENTS.md](AGENTS.md) and [deployment documentation](docs/DEPLOYMENT.md).

The loopback API exposes:

- `/livez`: process liveness, without a database dependency.
- `/readyz`: bounded MySQL connectivity and schema readiness; returns 503 when unavailable or incompatible.

Keep these endpoints internal. API documentation is disabled by default. There is no public enrollment endpoint and Stage 01 does not expose a heartbeat endpoint.

## Local administrative commands

Run from `server/` with the protected database environment already loaded. Restrict operating-system and database access to authorized operators. `--actor` records an accountable operator label in the audit trail; it does not authenticate or authorize the person running the command. Use public UUIDs returned by the CLI, not internal database IDs.

```sh
python -m app.cli --help
python -m app.cli --actor operator-name project-create --name "Training fleet"
python -m app.cli --actor operator-name device-enroll --project PROJECT_UUID --name "GPU server 01"
```

Successful commands print JSON. **Enrollment and rotation print the new device token once to stdout.** Use a private terminal with recording disabled, or redirect to a newly created protected file in a restricted directory. Do not send this output to CI logs, tickets, screenshots, or source control. Transfer the device UUID and token securely to the intended device. The server stores only the credential digest; it cannot display a token again.

Enrollment defaults to GPU monitoring with a minimum expected count of one. CPU-only enrollment must explicitly use `--gpu-monitoring off`. Expected inventory is controlled by the operator:

```sh
python -m app.cli --actor operator-name device-enroll --project PROJECT_UUID --name "CPU server" --gpu-monitoring off
python -m app.cli --actor operator-name device-gpu-policy --device DEVICE_UUID --expected-gpu-min-count 2 --expected-gpu-uuid GPU_UUID_1 --expected-gpu-uuid GPU_UUID_2
python -m app.cli --actor operator-name device-show --device DEVICE_UUID
python -m app.cli --actor operator-name device-rename --device DEVICE_UUID --name "New name"
python -m app.cli --actor operator-name device-move --device DEVICE_UUID --project PROJECT_UUID
python -m app.cli --actor operator-name device-disable --device DEVICE_UUID
python -m app.cli --actor operator-name device-enable --device DEVICE_UUID
python -m app.cli --actor operator-name project-update --project PROJECT_UUID --name "New project name"
```

Renaming and moving devices preserve UUIDs and credentials. Disabling monitoring does not erase historical records. GPU policy changes replace the complete expected policy; supply the full intended inventory each time.

For planned credential rotation:

```sh
python -m app.cli --actor operator-name credential-rotate --device DEVICE_UUID --overlap-hours 24
```

Securely install the replacement on that device, verify its authenticated heartbeat once Stage 02 is available, then revoke the old credential using its non-secret identifier:

```sh
python -m app.cli --actor operator-name credential-revoke --device DEVICE_UUID --credential OLD_CREDENTIAL_UUID
```

Rotation allows at most two active credentials and at most 24 hours of overlap. `--expires-at` on enrollment or rotation accepts a timezone-qualified ISO 8601 timestamp, such as `2030-01-01T00:00:00Z`. Revocation is also available for an emergency; it is not a deletion of device history. Live credential operations require explicit production authorization.

Exit codes are `0` for success, `2` for invalid arguments, and `1` for configuration or operation failure. Error output omits raw SQL, credentials, and exception messages. When an operation is interrupted after submission, inspect state before retrying: a database commit and terminal output are separate operations.

## Verification

From the repository root with the environment activated:

```sh
python -m pytest -c server/pyproject.toml server/tests
python -m ruff check server
python -m ruff format --check server
cd server
python -m mypy app
```

Real MySQL tests require `SKYBEAT_TEST_DATABASE_URL` supplied through a protected environment. Point it only at an isolated loopback MySQL 8.x test database, with a name ending in `_test` and an account scoped to that database. Tests may apply migrations and create test records. They must never target production. Without the test URL, MySQL-specific tests are skipped; a unit-only pass does not complete Stage 01 acceptance. Keep test credentials and data outside version control.

The hash-locked dependency file is generated from `server/pyproject.toml`. Intentional dependency updates require regenerating the lock, reviewing changes, and rerunning affected checks. See [security requirements](docs/SECURITY.md) for secret handling, credential lifecycle, audit, and least-privilege requirements.
