"""Static safety checks for the Linux-only production agent installer."""

from pathlib import Path

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
