"""Deployment artifact validation without a Docker daemon or database."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate_deployment.py"


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
