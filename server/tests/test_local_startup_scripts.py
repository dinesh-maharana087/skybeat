# ruff: noqa: E501

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _probe_launcher_function(name: str, body: str) -> subprocess.CompletedProcess[str]:
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        pytest.skip("Windows PowerShell is unavailable")
    script = REPOSITORY_ROOT / "start-skybeat-local.ps1"
    command = f"""
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$tree = [System.Management.Automation.Language.Parser]::ParseFile(
    '{script}', [ref]$tokens, [ref]$errors
)
$definition = $tree.FindAll({{
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq '{name}'
}}, $true)[0]
. ([scriptblock]::Create($definition.Extent.Text))
{body}
"""
    return subprocess.run(  # noqa: S603 - fixed PowerShell binary and local test code
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


@pytest.mark.parametrize("script_name", ["start-skybeat-local.ps1", "start-caddy-local.ps1"])
def test_local_launchers_keep_root_endpoint_configuration_over_stale_process_values(
    tmp_path: Path, script_name: str
):
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        pytest.skip("Windows PowerShell is unavailable")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SKYBEAT_ENV=production\n"
        "SKYBEAT_AGENT_SERVER_URL=https://file.example.test\n"
        "SKYBEAT_LOCAL_ENDPOINT_MODE=configured\n"
    )
    script = REPOSITORY_ROOT / script_name
    command = f"""
$tokens = $null
$errors = $null
$tree = [System.Management.Automation.Language.Parser]::ParseFile(
    '{script}', [ref]$tokens, [ref]$errors
)
$definition = $tree.FindAll({{
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Import-SkyBeatEnvironment'
}}, $true)[0]
. ([scriptblock]::Create($definition.Extent.Text))
$loaded = Import-SkyBeatEnvironment -Path '{env_file}'
if ($loaded['SKYBEAT_ENV'] -ne 'development' -or
    $env:SKYBEAT_ENV -ne 'development') {{ throw 'Environment precedence failed' }}
if ($loaded['SKYBEAT_AGENT_SERVER_URL'] -ne 'https://file.example.test') {{
    throw 'Root endpoint precedence failed'
}}
if ($loaded['SKYBEAT_LOCAL_ENDPOINT_MODE'] -ne 'configured') {{
    throw 'Root endpoint mode precedence failed'
}}
'precedence-ok'
"""
    environment = os.environ.copy()
    environment["SKYBEAT_ENV"] = "development"
    environment["SKYBEAT_AGENT_SERVER_URL"] = "https://process.example.test"
    environment["SKYBEAT_LOCAL_ENDPOINT_MODE"] = "auto"
    result = subprocess.run(  # noqa: S603 - fixed PowerShell binary and local test code
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "precedence-ok" in result.stdout


def test_local_launcher_missing_root_configuration_fails_before_starting_services(tmp_path: Path):
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        pytest.skip("Windows PowerShell is unavailable")
    copy = tmp_path / "start-skybeat-local.ps1"
    copy.write_bytes((REPOSITORY_ROOT / "start-skybeat-local.ps1").read_bytes())
    result = subprocess.run(  # noqa: S603 - fixed PowerShell binary and local script
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(copy),
            "-PreflightOnly",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode != 0
    assert "SkyBeat .env file not found" in result.stderr
    assert "Uvicorn: running" not in result.stdout


def test_local_api_launcher_is_path_independent_and_has_a_safe_preflight():
    script = (REPOSITORY_ROOT / "start-skybeat-local.ps1").read_text(encoding="utf-8")

    assert "$PSScriptRoot" in script
    assert "PreflightOnly" in script
    assert "SKYBEAT_AGENT_SERVER_URL" in script
    assert "SKYBEAT_ALLOW_INSECURE_LOCAL_AGENT_SERVER" in script
    assert "Configuration: OK" in script
    assert "GOOGLE_CLIENT_SECRET" not in script
    assert "SMTP_PASSWORD" not in script


def test_local_api_launcher_binds_all_interfaces_without_overwriting_agent_origin():
    script = (REPOSITORY_ROOT / "start-skybeat-local.ps1").read_text(encoding="utf-8")

    assert "--host 0.0.0.0" in script
    assert 'Write-Host "Uvicorn bind: 0.0.0.0:8000"' in script
    assert 'Write-Host "Local browser: http://127.0.0.1:8000"' in script
    assert '$agentServerUrl = $loaded["SKYBEAT_AGENT_SERVER_URL"]' in script


def test_local_api_launcher_uses_durable_checkout_owned_worker_state_without_secrets():
    script = (REPOSITORY_ROOT / "start-skybeat-local.ps1").read_text(encoding="utf-8")
    gitignore = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "function Get-LocalWorkerStatePath" in script
    assert "function Read-LocalWorkerState" in script
    assert "function Write-LocalWorkerState" in script
    assert "function Test-LocalWorkerState" in script
    assert "function Find-UntrackedLocalSkyBeatWorkers" in script
    assert "function Stop-LocalOwnedWorker" in script
    assert "function Start-LocalNotificationWorker" in script
    assert "-m app.worker" in script
    assert "System.Threading.Mutex" in script
    assert "CreationTimeUtc" in script
    assert "RepositoryRoot" in script
    assert "ServerDirectory" in script
    assert "WorkerCommand" in script
    assert "Move-Item -LiteralPath $temporaryPath -Destination $StatePath" in script
    assert "-WorkingDirectory $ServerDirectory" in script
    assert "-WindowStyle Hidden" in script
    assert 'Write-Host "Notification worker: $workerStatus"' in script
    assert 'return "started"' in script
    assert 'return "restarted"' in script
    assert 'Write-Host "Notification worker: running"' not in script
    assert "Notification worker failed to start" in script
    assert "SMTP_PASSWORD" not in script
    assert "GOOGLE_CLIENT_SECRET" not in script
    assert ".skybeat-local-runtime/" in gitignore


def test_local_api_launcher_replaces_only_a_validated_owned_worker_and_rejects_untracked_workers():
    script = (REPOSITORY_ROOT / "start-skybeat-local.ps1").read_text(encoding="utf-8")

    assert "Invoke-LocalWorkerStartupGuard" in script
    assert "Stop-LocalOwnedWorker" in script
    assert "Find-UntrackedLocalSkyBeatWorkers" in script
    assert "Untracked SkyBeat notification worker conflict" in script
    assert '"PID $($_.ProcessId)"' in script
    assert '"PID $($_.ProcessId): $($_.CommandLine)"' not in script
    assert "Stop-Process -Name python" not in script
    assert "Get-Process -Name python" not in script
    assert "-Force" in script


def test_local_api_launcher_starts_the_worker_before_unchanged_foreground_uvicorn():
    script = (REPOSITORY_ROOT / "start-skybeat-local.ps1").read_text(encoding="utf-8")

    worker_start = script.rindex("Start-LocalNotificationWorker")
    uvicorn_start = script.index("& $python -m uvicorn app.main:create_app")
    environment_load = script.index("$loaded = Import-SkyBeatEnvironment")

    assert environment_load < worker_start
    assert worker_start < uvicorn_start
    assert "--host 127.0.0.1 --port 8000" in script
    assert "--host 0.0.0.0 --port 8000" in script


def test_local_launcher_checks_schema_before_starting_services_without_auto_migration():
    script = (REPOSITORY_ROOT / "start-skybeat-local.ps1").read_text(encoding="utf-8")

    guard = script.index("-m app.local_schema_guard")
    assert script.index("$loaded = Import-SkyBeatEnvironment") < guard
    assert guard < script.index("Start-LocalCaddy -CaddyLauncher")
    assert guard < script.rindex("Start-LocalNotificationWorker")
    assert "-m alembic upgrade" not in script


def test_local_launcher_preflight_checks_database_schema_before_process_start():
    script = (REPOSITORY_ROOT / "start-skybeat-local.ps1").read_text(encoding="utf-8")

    guard = script.index("-m app.local_schema_guard")
    preflight_return = script.index("if ($PreflightOnly) {\n    return")
    assert guard < preflight_return
    assert "if (-not $PreflightOnly) {\n    Push-Location $serverDirectory" not in script


def test_local_api_launcher_reuses_only_a_live_skybeat_uvicorn_on_loopback():
    script = (REPOSITORY_ROOT / "start-skybeat-local.ps1").read_text(encoding="utf-8")

    assert "function Test-ExistingLocalSkyBeatUvicorn" in script
    assert "function Test-LocalUvicornHealth" in script
    assert 'Get-ListeningProcess -Address "127.0.0.1" -Port 8000' in script
    assert "Get-CimInstance" in script
    assert "Win32_Process" in script
    assert "Test-ProcessHasExpectedLauncherAncestor" in script
    assert "-ExpectedPython $Python" in script
    assert "app.main:create_app" in script
    assert "/livez" in script
    assert "/readyz" in script
    assert 'Write-Host "Uvicorn: running"' in script
    assert r"(?i)(?:^|\s)-m\s+uvicorn\s+app\.main:create_app" in script


def test_local_api_launcher_rejects_unrelated_loopback_port_owner_without_stopping_it():
    script = (REPOSITORY_ROOT / "start-skybeat-local.ps1").read_text(encoding="utf-8")

    assert "TCP port 8000 is already owned by" in script
    assert "not a SkyBeat Uvicorn process" in script
    uvicorn_reuse = script[script.index("function Test-LocalUvicornReuse") :]
    assert "Stop-Process" not in uvicorn_reuse


def test_local_launcher_has_read_only_running_verification_and_safe_proxy_diagnostics():
    script = (REPOSITORY_ROOT / "start-skybeat-local.ps1").read_text(encoding="utf-8")

    assert "[switch]$VerifyRunning" in script
    assert "function Test-CaddyProxyHealth" in script
    assert "BadGateway" in script
    assert "TrustFailure" in script
    assert "function Test-LocalWorkerRunning" in script
    assert "-m app.local_release_status" in script
    assert "Test-CaddyProxyHealth -Origin $agentServerUrl" in script
    assert "VerifyRunning" in script[script.index("if ($PreflightOnly) {\n    return") :]


def test_running_verification_rejects_stale_worker_ownership_without_starting_one():
    result = _probe_launcher_function(
        "Test-LocalWorkerRunning",
        """
function Get-LocalWorkerStatePath { return 'state.json' }
function Read-LocalWorkerState { return [pscustomobject]@{ ProcessId = 123 } }
function Test-LocalWorkerState { return $null }
function Find-UntrackedLocalSkyBeatWorkers { throw 'Unexpected process scan' }
try {
    Test-LocalWorkerRunning -Root 'root' -Python 'python' -ServerDirectory 'server'
    throw 'Stale state was accepted'
}
catch {
    if ($_.Exception.Message -notmatch 'missing or stale') { throw }
}
'stale-rejected'
""",
    )
    assert result.returncode == 0, result.stderr
    assert "stale-rejected" in result.stdout


def test_worker_startup_rejects_duplicate_before_starting_process():
    result = _probe_launcher_function(
        "Start-LocalNotificationWorker",
        """
function Invoke-LocalWorkerStartupGuard { param($Root, $Action) & $Action }
function Get-LocalWorkerStatePath { return 'state.json' }
function Read-LocalWorkerState { return $null }
function Test-LocalWorkerState { return $null }
function Find-UntrackedLocalSkyBeatWorkers {
    return [pscustomobject]@{ ProcessId = 123; CommandLine = 'secret-canary' }
}
function Format-UntrackedWorkerConflict { return 'Untracked worker PID 123' }
function Start-Process { throw 'Duplicate process started' }
try {
    Start-LocalNotificationWorker -Root 'root' -Python 'python' -ServerDirectory 'server'
    throw 'Duplicate worker was accepted'
}
catch {
    if ($_.Exception.Message -ne 'Untracked worker PID 123') { throw }
}
'duplicate-rejected'
""",
    )
    assert result.returncode == 0, result.stderr
    assert "duplicate-rejected" in result.stdout
    assert "secret-canary" not in result.stdout + result.stderr


def test_untracked_worker_diagnostic_never_echoes_command_line():
    result = _probe_launcher_function(
        "Format-UntrackedWorkerConflict",
        """
$worker = [pscustomobject]@{ ProcessId = 123; CommandLine = 'secret-canary' }
$message = Format-UntrackedWorkerConflict -Workers @($worker)
if ($message -notmatch 'PID 123') { throw 'Missing worker identifier' }
if ($message -match 'secret-canary') { throw 'Command line leaked' }
'worker-redacted'
""",
    )
    assert result.returncode == 0, result.stderr
    assert "worker-redacted" in result.stdout


def test_uvicorn_health_requires_both_liveness_and_readiness():
    result = _probe_launcher_function(
        "Test-LocalUvicornHealth",
        """
function Invoke-WebRequest {
    [CmdletBinding()]
    param([switch]$UseBasicParsing, [string]$Uri, [int]$TimeoutSec)
    if ($Uri.EndsWith('/readyz')) { return [pscustomobject]@{ StatusCode = 503 } }
    return [pscustomobject]@{ StatusCode = 200 }
}
if (Test-LocalUvicornHealth) { throw 'Unready API was accepted' }
'unready-rejected'
""",
    )
    assert result.returncode == 0, result.stderr
    assert "unready-rejected" in result.stdout


@pytest.mark.parametrize(
    "failure,expected", [("BadGateway", "returned 502"), ("TrustFailure", "TLS trust")]
)
def test_proxy_probe_distinguishes_upstream_502_from_tls_trust(failure: str, expected: str):
    if failure == "BadGateway":
        mock_failure = """
$problem = [Exception]::new('proxy request failed')
$response = [pscustomobject]@{ StatusCode = [Net.HttpStatusCode]::BadGateway }
$problem | Add-Member -NotePropertyName Response -NotePropertyValue $response
throw $problem
"""
    else:
        mock_failure = """
throw [Net.WebException]::new('certificate rejected', [Net.WebExceptionStatus]::TrustFailure)
"""
    result = _probe_launcher_function(
        "Test-CaddyProxyHealth",
        f"""
function Invoke-WebRequest {{ {mock_failure} }}
try {{
    Test-CaddyProxyHealth -Origin 'https://127.0.0.1:8443'
    throw 'Proxy failure was accepted'
}}
catch {{
    if ($_.Exception.Message -notmatch '{expected}') {{ throw }}
}}
'proxy-classified'
""",
    )
    assert result.returncode == 0, result.stderr
    assert "proxy-classified" in result.stdout


def test_local_caddy_launcher_is_path_independent_and_has_no_machine_specific_path():
    script = (REPOSITORY_ROOT / "start-caddy-local.ps1").read_text(encoding="utf-8")

    assert "$PSScriptRoot" in script
    assert "D:\\learning\\skybeat" not in script


def test_local_caddyfile_does_not_embed_a_machine_specific_address():
    caddyfile = (REPOSITORY_ROOT / "Caddyfile.test").read_text(encoding="utf-8")

    assert "192.168.1.43" not in caddyfile


def test_local_https_agent_endpoint_keeps_uvicorn_internal_and_caddy_on_tls_port():
    api_launcher = (REPOSITORY_ROOT / "start-skybeat-local.ps1").read_text(encoding="utf-8")
    caddy_launcher = (REPOSITORY_ROOT / "start-caddy-local.ps1").read_text(encoding="utf-8")
    caddyfile = (REPOSITORY_ROOT / "Caddyfile.test").read_text(encoding="utf-8")

    assert "Start-Process" in api_launcher
    assert "--host 127.0.0.1 --port 8000" in api_launcher
    assert 'Write-Host "TLS termination: Caddy"' in api_launcher
    assert "SKYBEAT_LOCAL_TLS_ADDRESS" in caddy_launcher
    assert "SKYBEAT_LOCAL_TLS_BIND_ADDRESS" in caddy_launcher
    assert "Get-TlsListener" in caddy_launcher
    assert "$tlsListener.BindAddress" in caddy_launcher
    assert "https://{$SKYBEAT_LOCAL_TLS_ADDRESS:localhost:8000}" in caddyfile
    assert "bind {$SKYBEAT_LOCAL_TLS_BIND_ADDRESS:127.0.0.1}" in caddyfile
    assert "reverse_proxy 127.0.0.1:8000" in caddyfile
    assert "tls internal" in caddyfile


def _probe_local_endpoint_resolver(body: str) -> subprocess.CompletedProcess[str]:
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        pytest.skip("Windows PowerShell is unavailable")
    resolver = REPOSITORY_ROOT / "scripts" / "local-lan-endpoint.ps1"
    command = f"""
$ErrorActionPreference = 'Stop'
. '{resolver}'
{body}
"""
    return subprocess.run(  # noqa: S603 - fixed PowerShell binary and local test code
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def test_auto_local_endpoint_prefers_active_default_route_over_other_private_adapter():
    result = _probe_local_endpoint_resolver(
        """
function Get-NetAdapter {
    return @(
        [pscustomobject]@{ ifIndex = 12; Status = 'Up'; HardwareInterface = $true; InterfaceAlias = 'Ethernet'; InterfaceDescription = 'Intel Ethernet' },
        [pscustomobject]@{ ifIndex = 18; Status = 'Up'; HardwareInterface = $true; InterfaceAlias = 'Wi-Fi'; InterfaceDescription = 'Intel Wi-Fi' }
    )
}
function Get-NetRoute {
    return @(
        [pscustomobject]@{ ifIndex = 12; RouteMetric = 256; InterfaceMetric = 5 },
        [pscustomobject]@{ ifIndex = 18; RouteMetric = 0; InterfaceMetric = 45 }
    )
}
function Get-NetIPAddress {
    return @(
        [pscustomobject]@{ InterfaceIndex = 12; IPAddress = '192.168.1.88'; AddressState = 'Preferred' },
        [pscustomobject]@{ InterfaceIndex = 18; IPAddress = '192.168.1.38'; AddressState = 'Preferred' }
    )
}
$resolved = Resolve-SkyBeatLocalEndpoint -ConfiguredOrigin 'https://192.168.1.43:8000' -Mode auto
if ($resolved.EffectiveOrigin -ne 'https://192.168.1.38:8000') { throw "Unexpected origin: $($resolved.EffectiveOrigin)" }
if ($resolved.InterfaceAlias -ne 'Wi-Fi') { throw "Unexpected interface: $($resolved.InterfaceAlias)" }
'route-preference-ok'
"""
    )
    assert result.returncode == 0, result.stderr
    assert "route-preference-ok" in result.stdout


def test_configured_stale_private_endpoint_fails_without_explicit_auto_mode():
    result = _probe_local_endpoint_resolver(
        """
function Get-NetAdapter {
    return [pscustomobject]@{ ifIndex = 18; Status = 'Up'; HardwareInterface = $true; InterfaceAlias = 'Wi-Fi'; InterfaceDescription = 'Intel Wi-Fi' }
}
function Get-NetRoute {
    return [pscustomobject]@{ ifIndex = 18; RouteMetric = 0; InterfaceMetric = 45 }
}
function Get-NetIPAddress {
    return [pscustomobject]@{ InterfaceIndex = 18; IPAddress = '192.168.1.38'; AddressState = 'Preferred' }
}
try {
    Resolve-SkyBeatLocalEndpoint -ConfiguredOrigin 'https://192.168.1.43:8000' -Mode configured
    throw 'Stale origin was accepted'
}
catch {
    if ($_.Exception.Message -notmatch 'not assigned to an active trusted LAN interface') { throw }
}
'stale-rejected'
"""
    )
    assert result.returncode == 0, result.stderr
    assert "stale-rejected" in result.stdout


def test_auto_local_endpoint_rejects_vpn_and_reports_no_trusted_interface():
    result = _probe_local_endpoint_resolver(
        """
function Get-NetAdapter {
    return [pscustomobject]@{ ifIndex = 22; Status = 'Up'; HardwareInterface = $true; InterfaceAlias = 'Corp VPN'; InterfaceDescription = 'WireGuard Tunnel Adapter' }
}
function Get-NetRoute {
    return [pscustomobject]@{ ifIndex = 22; RouteMetric = 0; InterfaceMetric = 1 }
}
function Get-NetIPAddress {
    return [pscustomobject]@{ InterfaceIndex = 22; IPAddress = '10.0.0.9'; AddressState = 'Preferred' }
}
try {
    Resolve-SkyBeatLocalEndpoint -ConfiguredOrigin 'https://192.168.1.43:8000' -Mode auto
    throw 'VPN origin was accepted'
}
catch {
    if ($_.Exception.Message -notmatch 'No trusted Windows LAN interface') { throw }
}
'vpn-rejected'
"""
    )
    assert result.returncode == 0, result.stderr
    assert "vpn-rejected" in result.stdout


def test_local_launchers_share_development_endpoint_resolution_without_mutating_env_file():
    api_launcher = (REPOSITORY_ROOT / "start-skybeat-local.ps1").read_text(encoding="utf-8")
    caddy_launcher = (REPOSITORY_ROOT / "start-caddy-local.ps1").read_text(encoding="utf-8")

    for launcher in (api_launcher, caddy_launcher):
        assert '"scripts\\local-lan-endpoint.ps1"' in launcher
        assert "Resolve-SkyBeatLocalEndpoint" in launcher
        assert "SKYBEAT_LOCAL_ENDPOINT_MODE" in launcher
        assert "Set-Content -LiteralPath $envFile" not in launcher
    assert "[string]$AgentServerUrl" in caddy_launcher
    assert "-AgentServerUrl $agentServerUrl" in api_launcher
    assert "requires SKYBEAT_ENV=development" in caddy_launcher


def test_local_listener_detection_treats_wildcard_owner_as_a_port_conflict():
    result = _probe_launcher_function(
        "Get-ListeningProcess",
        """
function Get-NetTCPConnection {
    param($State, $LocalPort, $LocalAddress, $ErrorAction)
    if ($PSBoundParameters.ContainsKey('LocalAddress')) { throw 'Listener query must include wildcard addresses' }
    return [pscustomobject]@{ LocalAddress = '0.0.0.0'; LocalPort = 8000; OwningProcess = 321 }
}
function Get-Process {
    param($Id, $ErrorAction)
    return [pscustomobject]@{ Id = $Id; ProcessName = 'other-process' }
}
$owner = Get-ListeningProcess -Address '192.168.1.38' -Port 8000
if ($owner.ProcessName -ne 'other-process') { throw 'Wildcard listener was not found' }
'wildcard-owner-detected'
""",
    )
    assert result.returncode == 0, result.stderr
    assert "wildcard-owner-detected" in result.stdout


@pytest.mark.parametrize(
    ("startup_output", "expected"),
    [
        (
            "listen tcp 192.168.1.43:8000: bind: The requested address is not valid in its context",
            "invalid bind address",
        ),
        ("tls: failed to obtain certificate", "TLS/certificate startup failure"),
    ],
)
def test_caddy_startup_failure_hint_is_classified_without_echoing_raw_output(
    startup_output: str, expected: str
):
    result = _probe_launcher_function(
        "Get-CaddyStartupFailureHint",
        f"""
function Get-Content {{ return @('{startup_output}') }}
$hint = Get-CaddyStartupFailureHint -DiagnosticPaths @('caddy.out', 'caddy.err')
if ($hint -notmatch '{expected}') {{ throw "Unexpected hint: $hint" }}
if ($hint -match '192\\.168') {{ throw 'Raw Caddy output leaked' }}
'startup-hint-classified'
""",
    )
    assert result.returncode == 0, result.stderr
    assert "startup-hint-classified" in result.stdout
