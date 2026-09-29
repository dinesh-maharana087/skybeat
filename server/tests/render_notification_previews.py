"""Write deterministic no-SMTP notification previews for local visual inspection."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from app.notifications.email import SMTPEmailProvider
from app.notifications.types import DeliveryMessage

_SAMPLES = (
    ("device-offline", "DEVICE_OFFLINE"),
    ("device-recovered", "DEVICE_RECOVERED"),
    ("gpu-degraded", "GPU_DEGRADED"),
    ("gpu-recovered", "GPU_RECOVERED"),
)


def _message(event_kind: str) -> DeliveryMessage:
    return DeliveryMessage(
        delivery_uuid="4a4c9d7f-3d7a-4a1f-8d6b-041a7d2ecce0",
        destination="ops@example.test",
        event_kind=event_kind,
        project_name="Training Fleet",
        device_name="GPU host 01",
        incident_uuid="13ee3e3b-3fe4-4b93-97c5-1ea5527bd459",
        occurred_at=datetime(2026, 9, 23, 12, 3, tzinfo=UTC),
        opened_at=datetime(2026, 9, 23, 12, 0, tzinfo=UTC),
        closed_at=datetime(2026, 9, 23, 12, 3, tzinfo=UTC),
    )


def write_previews(output_directory: Path) -> None:
    """Render every supported event without opening an SMTP connection."""
    output_directory.mkdir(parents=True, exist_ok=True)
    provider = SMTPEmailProvider(
        host="smtp.example.test",
        port=587,
        username=None,
        password=None,
        from_address="skybeat@example.test",
        timeout_seconds=15,
    )
    for slug, event_kind in _SAMPLES:
        message = provider._message(_message(event_kind))
        output_directory.joinpath(f"{slug}.html").write_text(
            message.get_body(preferencelist=("html",)).get_content(), encoding="utf-8"
        )
        output_directory.joinpath(f"{slug}.txt").write_text(
            message.get_body(preferencelist=("plain",)).get_content(), encoding="utf-8"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    write_previews(args.output_dir)
    print(f"Wrote notification previews to {args.output_dir}")


if __name__ == "__main__":
    main()
