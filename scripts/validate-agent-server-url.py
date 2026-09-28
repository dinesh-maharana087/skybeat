#!/usr/bin/env python3
"""Validate the constrained agent-facing server origin used by the installer."""

from __future__ import annotations

import argparse
import ipaddress
import sys
from urllib.parse import urlsplit


def valid_origin(value: str, *, allow_insecure_local_server: bool) -> bool:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or (port is not None and not 1 <= port <= 65535)
    ):
        return False
    if parsed.scheme == "https":
        return True
    if not allow_insecure_local_server:
        return False
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        return False
    return not address.is_unspecified and (address.is_private or address.is_loopback)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--server", required=True)
    parser.add_argument("--allow-insecure-local-server", action="store_true")
    arguments = parser.parse_args()
    if valid_origin(
        arguments.server, allow_insecure_local_server=arguments.allow_insecure_local_server
    ):
        return 0
    print("agent server origin is invalid", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
