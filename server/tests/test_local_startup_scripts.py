from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


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
    assert '"PID $($_.ProcessId): $($_.CommandLine)"' in script
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
    assert 'Write-Host "Uvicorn: running"' in script
    assert r"(?i)(?:^|\s)-m\s+uvicorn\s+app\.main:create_app" in script


def test_local_api_launcher_rejects_unrelated_loopback_port_owner_without_stopping_it():
    script = (REPOSITORY_ROOT / "start-skybeat-local.ps1").read_text(encoding="utf-8")

    assert "TCP port 8000 is already owned by" in script
    assert "not a SkyBeat Uvicorn process" in script
    uvicorn_reuse = script[script.index("function Test-LocalUvicornReuse") :]
    assert "Stop-Process" not in uvicorn_reuse


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
