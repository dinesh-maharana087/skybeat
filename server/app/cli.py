"""Restricted local administration; never exposed as an HTTP management API."""

import argparse
import json
import sys
from datetime import UTC, datetime
from typing import Never
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.db import Database
from app.devices.service import GPUPolicy, IdentityError, IdentityService


class CommandError(ValueError):
    """An invalid command without any potentially sensitive argument text."""


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        # argparse normally repeats rejected values, which may be pasted secrets.
        raise CommandError("Invalid command arguments; run with --help.")


def _identifier(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError:
        raise argparse.ArgumentTypeError("A UUID is required.") from None


def _bounded_text(value: str, maximum: int) -> str:
    if (
        not value.strip()
        or len(value) > maximum
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise argparse.ArgumentTypeError("A bounded printable value is required.")
    return value


def _name(value: str) -> str:
    return _bounded_text(value, 128)


def _description(value: str) -> str:
    if value == "":
        return value
    return _bounded_text(value, 512)


def _gpu_uuid(value: str) -> str:
    return _bounded_text(value, 96)


def _bounded_integer(value: str, maximum: int) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("An integer is required.") from None
    if not 0 <= number <= maximum:
        raise argparse.ArgumentTypeError("Integer is outside the allowed range.")
    return number


def _gpu_count(value: str) -> int:
    return _bounded_integer(value, 64)


def _overlap(value: str) -> int:
    overlap = _bounded_integer(value, 24)
    if overlap < 1:
        raise argparse.ArgumentTypeError("Overlap must be between 1 and 24 hours.")
    return overlap


def _expiry(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError
        return result.astimezone(UTC)
    except ValueError:
        raise argparse.ArgumentTypeError("Use a timezone-qualified ISO 8601 timestamp.") from None


def _add_gpu_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--gpu-monitoring", choices=("on", "off"), default="on")
    parser.add_argument("--expected-gpu-min-count", type=_gpu_count)
    parser.add_argument("--expected-gpu-uuid", type=_gpu_uuid, action="append", default=[])


def _parser() -> SafeParser:
    parser = SafeParser(
        prog="skybeat-admin",
        description="Local SkyBeat administration. Enrollment/rotation output contains a secret.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--actor", type=_name, required=True, help="Accountable local operator label"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("project-create", allow_abbrev=False)
    create.add_argument("--name", type=_name, required=True)
    create.add_argument("--description", type=_description)
    update = commands.add_parser("project-update", allow_abbrev=False)
    update.add_argument("--project", type=_identifier, required=True)
    update.add_argument("--name", type=_name)
    update.add_argument("--description", type=_description)
    update.add_argument("--active", choices=("yes", "no"))
    enroll = commands.add_parser("device-enroll", allow_abbrev=False)
    enroll.add_argument("--project", type=_identifier, required=True)
    enroll.add_argument("--name", type=_name, required=True)
    enroll.add_argument("--expires-at", type=_expiry)
    _add_gpu_arguments(enroll)
    for command in (
        "device-show",
        "device-rename",
        "device-move",
        "device-enable",
        "device-disable",
        "device-gpu-policy",
        "credential-rotate",
        "credential-revoke",
    ):
        child = commands.add_parser(command, allow_abbrev=False)
        child.add_argument("--device", type=_identifier, required=True)
        if command == "device-rename":
            child.add_argument("--name", type=_name, required=True)
        elif command == "device-move":
            child.add_argument("--project", type=_identifier, required=True)
        elif command == "device-gpu-policy":
            _add_gpu_arguments(child)
        elif command == "credential-rotate":
            child.add_argument("--overlap-hours", type=_overlap, default=24)
            child.add_argument("--expires-at", type=_expiry)
        elif command == "credential-revoke":
            child.add_argument("--credential", type=_identifier, required=True)
    return parser


def _gpu_policy(arguments: argparse.Namespace) -> GPUPolicy:
    enabled = arguments.gpu_monitoring == "on"
    count = arguments.expected_gpu_min_count
    if count is None:
        count = 1 if enabled else 0
    uuids = tuple(arguments.expected_gpu_uuid)
    if len(uuids) > 64 or len(set(uuids)) != len(uuids) or (not enabled and (count or uuids)):
        raise CommandError("Invalid command arguments; run with --help.")
    return GPUPolicy(monitoring_enabled=enabled, min_count=count, uuids=uuids)


def _dispatch(service: IdentityService, args: argparse.Namespace) -> dict[str, object]:
    match args.command:
        case "project-create":
            project = service.create_project(args.name, description=args.description)
            return {"project_id": project.public_id, "name": project.name}
        case "project-update":
            project = service.update_project(
                args.project,
                name=args.name,
                description=args.description,
                is_active=None if args.active is None else args.active == "yes",
            )
            return {"project_id": project.public_id, "name": project.name}
        case "device-enroll":
            enrollment = service.enroll(
                args.project,
                args.name,
                policy=args.policy,
                expires_at=args.expires_at,
            )
            return {
                "device_id": enrollment.device.device_uuid,
                "credential_id": enrollment.credential.credential_id,
                "device_token": enrollment.credential.token.get_secret_value(),
            }
        case "device-show":
            device = service.get_device(args.device)
            return {
                "device_id": device.device_uuid,
                "device_name": device.name,
                "monitoring_enabled": device.monitoring_enabled,
                "gpu_monitoring_enabled": device.gpu_monitoring_enabled,
                "expected_gpu_min_count": device.expected_gpu_min_count,
                "expected_gpu_uuids": device.expected_gpu_uuids,
            }
        case "device-rename":
            device = service.rename(args.device, args.name)
        case "device-move":
            device = service.move(args.device, args.project)
        case "device-enable" | "device-disable":
            device = service.set_enabled(args.device, args.command == "device-enable")
        case "device-gpu-policy":
            device = service.set_gpu_policy(args.device, args.policy)
        case "credential-rotate":
            credential = service.rotate(
                args.device,
                overlap_hours=args.overlap_hours,
                expires_at=args.expires_at,
            )
            return {
                "device_id": args.device,
                "credential_id": credential.credential_id,
                "device_token": credential.token.get_secret_value(),
            }
        case "credential-revoke":
            service.revoke(args.device, args.credential)
            return {"device_id": args.device, "credential_id": args.credential, "revoked": True}
        case _:
            raise CommandError("Invalid command arguments; run with --help.")
    return {"device_id": device.device_uuid}


def main(argv: list[str] | None = None) -> int:
    """Return a process exit code and keep exception details out of console output."""
    try:
        arguments = _parser().parse_args(argv)
        if arguments.command in {"device-enroll", "device-gpu-policy"}:
            arguments.policy = _gpu_policy(arguments)
    except (CommandError, IdentityError):
        print("Invalid command arguments; run with --help.", file=sys.stderr)
        return 2
    except SystemExit as exit_status:
        return 0 if exit_status.code == 0 else 2
    try:
        # BaseSettings obtains required values from the protected runtime environment.
        # The pydantic mypy plugin cannot model that source for a required field.
        settings = Settings()  # type: ignore[call-arg]
    except (ValidationError, ValueError):
        print("Invalid SkyBeat configuration; review the protected environment.", file=sys.stderr)
        return 1
    try:
        database = Database(settings)
        try:
            service = IdentityService(database, actor=arguments.actor)
            output = _dispatch(service, arguments)
            print(json.dumps(output, ensure_ascii=True, allow_nan=False))
        finally:
            database.dispose()
    except IdentityError:
        print("Administrative operation rejected; check identifiers and policy.", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print("Administrative database operation failed; inspect database health.", file=sys.stderr)
        return 1
    except Exception as error:
        # This is the process boundary. Exception text can contain SQL parameters or secrets.
        print(
            f"Administrative operation failed unexpectedly ({type(error).__name__}).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
