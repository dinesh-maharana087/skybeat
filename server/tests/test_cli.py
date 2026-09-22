"""Local operator input, output, and failure boundaries."""

import importlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy.exc import OperationalError


@pytest.fixture
def cli(monkeypatch):
    module = importlib.import_module("app.cli")
    database = MagicMock()
    service = MagicMock()
    monkeypatch.setattr(module, "Settings", MagicMock())
    monkeypatch.setattr(module, "Database", MagicMock(return_value=database))
    monkeypatch.setattr(module, "IdentityService", MagicMock(return_value=service))
    return SimpleNamespace(module=module, database=database, service=service)


def run(cli, *arguments):
    return cli.module.main(["--actor", "local-operator", *arguments])


def test_enroll_exposes_new_token_only_in_deliberate_output(cli, capsys):
    device_id, project_id, credential_id = (str(uuid4()) for _ in range(3))
    token = "test-only-secret-output"
    cli.service.enroll.return_value = SimpleNamespace(
        device=SimpleNamespace(device_uuid=device_id),
        credential=SimpleNamespace(credential_id=credential_id, token=SecretStr(token)),
    )
    result = run(cli, "device-enroll", "--project", project_id, "--name", "GPU server")
    output = capsys.readouterr()
    assert result == 0
    assert json.loads(output.out) == {
        "device_id": device_id,
        "credential_id": credential_id,
        "device_token": token,
    }
    assert token not in output.err
    cli.database.dispose.assert_called_once()
    assert cli.service.enroll.call_args.args == (project_id, "GPU server")
    assert cli.service.enroll.call_args.kwargs["policy"].min_count == 1


def test_cpu_only_enrollment_has_explicit_disabled_policy(cli, capsys):
    cli.service.enroll.return_value = SimpleNamespace(
        device=SimpleNamespace(device_uuid=str(uuid4())),
        credential=SimpleNamespace(credential_id=str(uuid4()), token=SecretStr("test-only")),
    )
    assert (
        run(
            cli,
            "device-enroll",
            "--project",
            str(uuid4()),
            "--name",
            "CPU server",
            "--gpu-monitoring",
            "off",
        )
        == 0
    )
    policy = cli.service.enroll.call_args.kwargs["policy"]
    assert not policy.monitoring_enabled
    assert policy.min_count == 0
    assert policy.uuids == ()
    capsys.readouterr()


def test_expiration_is_timezone_qualified_and_converted_to_utc(cli, capsys):
    credential_id = str(uuid4())
    cli.service.rotate.return_value = SimpleNamespace(
        credential_id=credential_id, token=SecretStr("test-only")
    )
    device_id = str(uuid4())
    assert (
        run(
            cli,
            "credential-rotate",
            "--device",
            device_id,
            "--overlap-hours",
            "6",
            "--expires-at",
            "2030-01-01T05:30:00+05:30",
        )
        == 0
    )
    cli.service.rotate.assert_called_once_with(
        device_id, overlap_hours=6, expires_at=datetime(2030, 1, 1, tzinfo=UTC)
    )
    assert json.loads(capsys.readouterr().out)["credential_id"] == credential_id


@pytest.mark.parametrize(
    "arguments",
    [
        ["device-show", "--device", "secret-invalid-uuid"],
        ["credential-rotate", "--device", str(uuid4()), "--overlap-hours", "25"],
        ["credential-rotate", "--device", str(uuid4()), "--overlap-hours", "0"],
        ["credential-rotate", "--device", str(uuid4()), "--expires-at", "2030-01-01"],
        ["device-enroll", "--project", str(uuid4()), "--name", "\nsecret-invalid-name"],
        [
            "device-enroll",
            "--project",
            str(uuid4()),
            "--name",
            "example",
            "--gpu-monitoring",
            "off",
            "--expected-gpu-min-count",
            "1",
        ],
        ["secret-invalid-command"],
        ["device-show", "--device", str(uuid4()), "--token", "secret-invalid-option"],
    ],
)
def test_invalid_input_never_reaches_database_or_echoes_arguments(cli, capsys, arguments):
    assert run(cli, *arguments) == 2
    output = capsys.readouterr()
    assert not output.out
    assert "secret-invalid" not in output.err
    assert "Invalid command arguments" in output.err
    cli.module.Database.assert_not_called()


def test_actor_required_before_mutations(cli, capsys):
    assert cli.module.main(["project-create", "--name", "example"]) == 2
    cli.module.Database.assert_not_called()
    assert "Invalid command arguments" in capsys.readouterr().err


def test_help_does_not_initialize_database(cli, capsys):
    assert cli.module.main(["--help"]) == 0
    cli.module.Database.assert_not_called()
    assert "credential-rotate" in capsys.readouterr().out


def test_configuration_failure_does_not_print_secret(cli, capsys):
    cli.module.Settings.side_effect = ValueError("mysql://test:private-password@localhost/test")
    assert run(cli, "project-create", "--name", "example") == 1
    output = capsys.readouterr()
    assert not output.out
    assert "private-password" not in output.err
    assert "configuration" in output.err
    cli.module.Database.assert_not_called()


def test_database_failure_does_not_print_parameters_or_exception(cli, capsys):
    cli.service.create_project.side_effect = OperationalError(
        "INSERT secret SQL", {"password": "private-password"}, RuntimeError("private-password")
    )
    assert run(cli, "project-create", "--name", "example") == 1
    output = capsys.readouterr()
    assert not output.out
    assert "private-password" not in output.err
    assert "database" in output.err
    cli.database.dispose.assert_called_once()


def test_project_creation_records_actor_and_returns_public_identity(cli, capsys):
    project_id = str(uuid4())
    cli.service.create_project.return_value = SimpleNamespace(public_id=project_id, name="example")
    assert run(cli, "project-create", "--name", "example", "--description", "test fleet") == 0
    cli.module.IdentityService.assert_called_once_with(cli.database, actor="local-operator")
    cli.service.create_project.assert_called_once_with("example", description="test fleet")
    assert json.loads(capsys.readouterr().out) == {"project_id": project_id, "name": "example"}


def test_device_move_keeps_output_free_of_credential_data(cli, capsys):
    device_id, project_id = str(uuid4()), str(uuid4())
    cli.service.move.return_value = SimpleNamespace(device_uuid=device_id, token="private-password")
    assert run(cli, "device-move", "--device", device_id, "--project", project_id) == 0
    cli.service.move.assert_called_once_with(device_id, project_id)
    assert json.loads(capsys.readouterr().out) == {"device_id": device_id}


def test_revoke_requires_bound_device_and_credential_identifiers(cli, capsys):
    device_id, credential_id = str(uuid4()), str(uuid4())
    assert run(cli, "credential-revoke", "--device", device_id, "--credential", credential_id) == 0
    cli.service.revoke.assert_called_once_with(device_id, credential_id)
    assert json.loads(capsys.readouterr().out) == {
        "device_id": device_id,
        "credential_id": credential_id,
        "revoked": True,
    }


def test_show_selects_only_public_noncredential_fields(cli, capsys):
    device_id = str(uuid4())
    cli.service.get_device.return_value = SimpleNamespace(
        id=42,
        device_uuid=device_id,
        name="example",
        monitoring_enabled=True,
        gpu_monitoring_enabled=False,
        expected_gpu_min_count=0,
        expected_gpu_uuids=[],
        token="private-password",
    )
    assert run(cli, "device-show", "--device", device_id) == 0
    output = capsys.readouterr()
    assert "private-password" not in output.out
    assert "id" not in json.loads(output.out)
    assert json.loads(output.out)["device_name"] == "example"


@pytest.mark.parametrize("enabled", [True, False])
def test_enable_and_disable_call_explicit_monitoring_state(cli, capsys, enabled):
    device_id = str(uuid4())
    cli.service.set_enabled.return_value = SimpleNamespace(device_uuid=device_id)
    command = "device-enable" if enabled else "device-disable"
    assert run(cli, command, "--device", device_id) == 0
    cli.service.set_enabled.assert_called_once_with(device_id, enabled)
    assert json.loads(capsys.readouterr().out)["device_id"] == device_id


def test_project_update_preserves_unspecified_values(cli, capsys):
    project_id = str(uuid4())
    cli.service.update_project.return_value = SimpleNamespace(public_id=project_id, name="example")
    assert run(cli, "project-update", "--project", project_id, "--active", "no") == 0
    cli.service.update_project.assert_called_once_with(
        project_id,
        name=None,
        description=None,
        is_active=False,
    )
    capsys.readouterr()


def test_policy_rejection_does_not_print_exception_text(cli, capsys):
    cli.service.create_project.side_effect = cli.module.IdentityError("private-password")
    assert run(cli, "project-create", "--name", "example") == 1
    output = capsys.readouterr()
    assert not output.out
    assert "private-password" not in output.err
    assert "rejected" in output.err


def test_unexpected_error_has_safe_category_without_traceback(cli, capsys):
    cli.service.create_project.side_effect = RuntimeError("private-password")
    assert run(cli, "project-create", "--name", "example") == 1
    output = capsys.readouterr()
    assert not output.out
    assert "private-password" not in output.err
    assert "RuntimeError" in output.err
    assert "Traceback" not in output.err
