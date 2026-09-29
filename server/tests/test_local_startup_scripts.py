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
