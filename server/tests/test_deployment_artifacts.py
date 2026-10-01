"""Deployment artifact validation without a Docker daemon or database."""

import subprocess
import sys
from pathlib import Path
from shutil import which

import pytest

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate_deployment.py"
INSTALLER = ROOT / "scripts" / "install-agent.sh"
INSTALLER_LIBRARY = ROOT / "scripts" / "lib" / "skybeat_agent_install.sh"


def _validate(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- invokes the current interpreter on the committed validator.
        [sys.executable, str(VALIDATOR), "--root", str(root)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_deployment_validator_reports_each_missing_required_artifact():
    result = _validate(ROOT / "missing-deployment-root")

    assert result.returncode == 1
    assert "missing: docker-compose.yml" in result.stderr
    assert "missing: deployment/docker/Dockerfile.server" in result.stderr
    assert "missing: deployment/mysql/01-create-migration-user.sh" in result.stderr
    assert "missing: deployment/production.env.example" in result.stderr
    assert "missing: scripts/install-agent.sh" in result.stderr
    assert "missing: scripts/lib/skybeat_agent_install.sh" in result.stderr


def test_deployment_validator_accepts_the_repository_hardened_artifacts():
    result = _validate(ROOT)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "SkyBeat deployment artifacts are valid.\n"


def test_runbook_requires_backup_before_explicit_migration_and_forbids_volume_deletion():
    deployment = (ROOT / "docs" / "DEPLOYMENT.md").read_text(encoding="utf-8")

    assert "backup" in deployment.lower()
    assert "docker compose --env-file .env --profile migrate run --rm migrate" in deployment
    assert "Never solve a migration failure with `docker compose down -v`" in deployment
    assert "30 days" in deployment


def test_stage07_runbook_documents_safe_private_ca_and_agent_installation():
    runbook = (ROOT / "docs" / "DEPLOYMENT_RUNBOOK.md").read_text(encoding="utf-8")

    assert "/opt/skybeat" in runbook
    assert "/etc/skybeat-agent/agent.env" in runbook
    assert "SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt" in runbook
    assert "Never use `verify=False`" in runbook
    assert "python -m uvicorn app.main:create_app --factory" in runbook
    assert "curl --fail https://monitor.example.com/livez" not in runbook
    assert "curl --fail http://127.0.0.1:8000/livez" in runbook
    assert "sudo bash ./scripts/install-agent.sh ./agent /secure/path/agent.env" in runbook


def test_stage076_runbook_labels_dashboard_bypass_local_only_and_credential_safe():
    runbook = (ROOT / "docs" / "DEPLOYMENT_RUNBOOK.md").read_text(encoding="utf-8")

    assert "SKYBEAT_DEV_AUTH_BYPASS=true" in runbook
    assert "local development only" in runbook.lower()
    assert "production configuration rejects" in runbook.lower()
    assert "do not record the credential" in runbook.lower()


def test_active_agent_unit_uses_standardized_path_and_least_privilege():
    unit = (ROOT / "deployment" / "systemd" / "skybeat-agent.service").read_text(encoding="utf-8")

    assert "/opt/skybeat/venv/bin/skybeat-agent" in unit
    assert "/opt/skybeat-agent" not in unit
    assert "User=skybeat" in unit
    assert "EnvironmentFile=/etc/skybeat/agent.env" in unit


def test_installer_uses_the_current_enrollment_token_and_secret_safe_guards():
    assert INSTALLER.is_file()

    text = INSTALLER.read_text(encoding="utf-8")
    library = INSTALLER_LIBRARY.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text
    assert "--token-file" in text
    assert "--credential" not in text
    assert "warning: use --token-file in production" in text
    assert "/opt/skybeat/venv" in library
    assert "/etc/skybeat/agent.env" in library
    assert "install -m 0600 -o root -g root" in library
    assert "set -x" not in text + library
    assert "[[ ${EUID:-1} -eq 0 ]]" in library
    assert "useradd --system --user-group" in library


@pytest.mark.skipif(which("bash") is None, reason="Bash is unavailable on this host")
def test_installer_rejects_the_legacy_credential_option_before_host_changes():
    result = subprocess.run(  # noqa: S603 -- invokes the committed installer only with rejected input.
        [which("bash"), str(INSTALLER), "--credential", "test-value"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "usage:" in result.stderr
    assert "test-value" not in result.stderr


@pytest.mark.skipif(which("bash") is None, reason="Bash is unavailable on this host")
def test_installer_rejects_missing_source_and_environment_without_host_changes(tmp_path):
    bash = which("bash")
    missing_source = subprocess.run(  # noqa: S603 -- invokes the installer only with invalid paths.
        [bash, str(INSTALLER), str(tmp_path / "missing-agent"), str(tmp_path / "missing.env")],
        check=False,
        capture_output=True,
        text=True,
    )
    missing_environment = subprocess.run(  # noqa: S603 -- invalid environment path stops before root work.
        [bash, str(INSTALLER), str(ROOT / "agent"), str(tmp_path / "missing.env")],
        check=False,
        capture_output=True,
        text=True,
    )

    assert missing_source.returncode != 0
    assert "agent source directory is invalid" in missing_source.stderr
    assert missing_environment.returncode != 0
    assert "protected environment file is missing" in missing_environment.stderr


def test_status_records_operator_supplied_stage06_evidence_without_secrets():
    status = (ROOT / "docs" / "IMPLEMENTATION_STATUS.md").read_text(encoding="utf-8")

    assert "operator-supplied stage 06 acceptance evidence" in status.lower()
    assert "NVIDIA GeForce RTX 5080" in status
    assert "Current stage: Stage 12C - Deployment To Install Workflow" in status
    assert "Implemented Stage 12A Alert Routing UI polish" in status
    assert "Stage 07.1" in status
