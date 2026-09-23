"""Validate committed deployment artifacts without starting infrastructure."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REQUIRED = (
    "docker-compose.yml",
    "deployment/docker/Dockerfile.server",
    "deployment/caddy/Caddyfile",
    "deployment/mysql/01-create-migration-user.sh",
    "deployment/systemd/skybeat-agent.service",
    "deployment/systemd/agent.env.example",
    "deployment/production.env.example",
)


def validate(root: Path) -> list[str]:
    errors = [f"missing: {path}" for path in REQUIRED if not (root / path).is_file()]
    if errors:
        return errors
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    caddy = (root / "deployment/caddy/Caddyfile").read_text(encoding="utf-8")
    dockerfile = (root / "deployment/docker/Dockerfile.server").read_text(encoding="utf-8")
    unit = (root / "deployment/systemd/skybeat-agent.service").read_text(encoding="utf-8")
    required_compose = ("mysql:", "migrate:", "api:", "worker:", "caddy:", "profiles:")
    errors.extend(f"compose missing: {item}" for item in required_compose if item not in compose)
    if "3306:3306" in compose or "8000:8000" in compose:
        errors.append("compose publishes an internal service port")
    if "80:80" not in compose or "443:443" not in compose:
        errors.append("compose does not publish Caddy HTTP and HTTPS ports")
    if "mysql_data:/var/lib/mysql" not in compose:
        errors.append("compose lacks persistent MySQL storage")
    if "USER skybeat" not in dockerfile:
        errors.append("server image does not use the skybeat runtime user")
    if "max_size 128KiB" not in caddy or "/livez" not in caddy or "/readyz" not in caddy:
        errors.append("Caddy lacks request-size or internal-health protection")
    required_unit = ("User=skybeat", "Restart=on-failure", "NoNewPrivileges=true")
    errors.extend(f"agent unit missing: {item}" for item in required_unit if item not in unit)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    root = parser.parse_args().root.resolve()
    errors = validate(root)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("SkyBeat deployment artifacts are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
