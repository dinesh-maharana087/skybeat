"""SkyBeat's outbound-only Linux monitoring agent."""

from importlib import metadata


def agent_version() -> str:
    """Read the running wheel version; source-only test runs have no installed wheel."""
    try:
        return metadata.version("skybeat-agent")
    except metadata.PackageNotFoundError:
        return "unknown"
