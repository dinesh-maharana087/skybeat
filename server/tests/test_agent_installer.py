"""Safety checks for the Linux-only production agent installer."""

import os
import subprocess
from pathlib import Path
from shutil import which

import pytest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "scripts" / "install-agent.sh"
LIBRARY = ROOT / "scripts" / "lib" / "skybeat_agent_install.sh"
UNIT = ROOT / "deployment" / "systemd" / "skybeat-agent.service"


def test_installer_accepts_only_explicit_verified_release_inputs():
    source = INSTALLER.read_text(encoding="utf-8")

    for option in (
        "--server",
        "--package",
        "--sha256",
        "--wheelhouse",
        "--lockfile",
        "--token-file",
    ):
        assert option in source
    assert "agent-source-directory" not in source
    assert "--no-index" in LIBRARY.read_text(encoding="utf-8")
    assert "--require-hashes" in LIBRARY.read_text(encoding="utf-8")
    assert "-m pip install" in LIBRARY.read_text(encoding="utf-8")
    assert "--no-deps" in LIBRARY.read_text(encoding="utf-8")


def test_installer_requires_an_explicit_flag_for_private_development_http_only():
    source = INSTALLER.read_text(encoding="utf-8")
    library = LIBRARY.read_text(encoding="utf-8")

    assert "--allow-insecure-local-server" in source
    assert "validate-agent-server-url.py" in library
    assert "SKYBEAT_ALLOW_INSECURE_LOCAL_SERVER" in library


def test_installer_has_ordered_fail_closed_lifecycle_helpers_and_secret_guards():
    source = LIBRARY.read_text(encoding="utf-8")

    for function in (
        "preflight",
        "verify_package",
        "install_package",
        "configure_agent",
        "enroll_device",
        "install_service",
        "verify_installation",
    ):
        assert f"{function}()" in source
    assert "set -x" not in source
    assert "/etc/skybeat/agent.env" in source
    assert "install -m 0600 -o root -g root" in source
    assert "rollback_switch" in INSTALLER.read_text(encoding="utf-8")
    assert "systemctl disable --now skybeat-agent.service" not in INSTALLER.read_text(
        encoding="utf-8"
    )
    assert "venv.candidate" in source
    assert source.index("verify_local_health()") < source.index("accept_switch()")
    assert "--re-enroll" in INSTALLER.read_text(encoding="utf-8")


def test_installer_polls_the_narrow_receipt_endpoint_after_a_fresh_exchange():
    source = LIBRARY.read_text(encoding="utf-8")

    assert "poll_verification_receipt()" in source
    assert "/api/v1/agent-enrollments/verification" in source
    assert "accepted_heartbeat" in source
    assert "for attempt in {1..12}" in source
    assert "sleep 5" in source


def test_installer_has_distinct_no_change_repair_and_upgrade_outcomes():
    source = LIBRARY.read_text(encoding="utf-8")
    installer = INSTALLER.read_text(encoding="utf-8")

    assert "installation_is_current()" in source
    assert "install_outcome=UPGRADED" in source
    assert "version=%s" in source
    assert "installation_is_current" in installer
    assert "install_outcome=ALREADY_CURRENT" in installer


def test_explicit_reenrollment_binds_exchange_to_the_existing_device():
    source = LIBRARY.read_text(encoding="utf-8")

    assert "X-SkyBeat-Reenroll-Device" in source
    assert "re-enrollment requires an existing device configuration" in source


def test_systemd_unit_runs_unprivileged_with_compatible_hardening():
    unit = UNIT.read_text(encoding="utf-8")

    assert "User=skybeat" in unit
    assert "Group=skybeat" in unit
    assert "EnvironmentFile=/etc/skybeat/agent.env" in unit
    assert "NoNewPrivileges=true" in unit
    assert "PrivateTmp=true" in unit
    assert "PrivateDevices=true" not in unit
    assert "CapabilityBoundingSet=" in unit


@pytest.mark.parametrize("initial_state", ["disabled", "enabled"])
@pytest.mark.skipif(which("bash") is None, reason="Bash is unavailable on this host")
def test_installing_updater_units_preserves_timer_state(initial_state):
    """A fresh install stays disabled; an explicitly enabled timer stays enabled."""
    script = r"""
set -euo pipefail
if command -v cygpath >/dev/null 2>&1; then
    source "$(cygpath -u "$INSTALLER_LIBRARY_PATH")"
else
    source "$INSTALLER_LIBRARY_PATH"
fi
timer_state="$INITIAL_TIMER_STATE"
updater_script=missing
updater_service=missing
updater_timer=missing
reloads=0
systemctl() {
    case "$1" in
        enable|start|disable|stop|restart)
            case " $* " in
                *skybeat-updater.timer*)
                    case "$1" in
                        enable|start) timer_state=enabled ;;
                        disable|stop) timer_state=disabled ;;
                        restart) timer_state=active ;;
                    esac
                    ;;
            esac
            ;;
        daemon-reload) reloads=$((reloads + 1)) ;;
        *) return 1 ;;
    esac
}
install() {
    case "$*" in
        *agent-updater.py*) updater_script=installed ;;
        *skybeat-updater.service*) updater_service=installed ;;
        *skybeat-updater.timer*) updater_timer=installed ;;
    esac
}
install_updater
printf 'timer_state=%s\nupdater_script=%s\nupdater_service=%s\nupdater_timer=%s\nreloads=%s\n' \
    "$timer_state" "$updater_script" "$updater_service" "$updater_timer" "$reloads"
"""
    result = subprocess.run(  # noqa: S603 -- Bash sources only the installer helper; host mutations are stubbed.
        [which("bash"), "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "INSTALLER_LIBRARY_PATH": str(LIBRARY),
            "INITIAL_TIMER_STATE": initial_state,
            "release_dir": str(ROOT),
        },
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        f"timer_state={initial_state}\n"
        "updater_script=installed\n"
        "updater_service=installed\n"
        "updater_timer=installed\n"
        "reloads=1\n"
    )
