"""Pickleable helper for the isolated stuck-collector regression."""

import os
import threading
from pathlib import Path
from typing import Any


def collect_forever() -> dict[str, Any]:
    Path(os.environ["SKYBEAT_TEST_STUCK_MARKER"]).touch()
    threading.Event().wait()
    raise AssertionError("unreachable")
