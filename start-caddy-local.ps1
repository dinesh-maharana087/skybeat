[CmdletBinding()]
param(
    [switch]$PreflightOnly,
    [string]$AgentServerUrl
)

$ErrorActionPreference = "Stop"

function Import-SkyBeatEnvironment {
    param([Parameter(Mandatory)][string]$Path)

    $loaded = @{}
    $rootEndpointSettings = @(
        "SKYBEAT_AGENT_SERVER_URL",
        "SKYBEAT_LOCAL_ENDPOINT_MODE"
    )
    $lineNumber = 0
    foreach ($rawLine in Get-Content -LiteralPath $Path) {
        $lineNumber++
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            continue
        }
        if ($line -notmatch "^(?<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?<value>.*)$") {
            throw "Invalid .env entry at line $lineNumber. Use KEY=VALUE."
        }
        $name = $matches.name
        $value = $matches.value.Trim()
        if ($value.Length -ge 2 -and (
                ($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))
            )) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $explicit = [Environment]::GetEnvironmentVariable($name, "Process")
        if ($name -in $rootEndpointSettings) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
            $loaded[$name] = $value
        }
        else {
            $loaded[$name] = if ($null -ne $explicit) { $explicit } else { $value }
        }
    }
    return $loaded
}

function Get-TlsListener {
    param([Parameter(Mandatory)][string]$AgentServerUrl)

    try {
        $uri = [Uri]$AgentServerUrl
    }
    catch {
        throw "SKYBEAT_AGENT_SERVER_URL must be an absolute HTTPS origin for the local Caddy proxy."
    }
    if (
        -not $uri.IsAbsoluteUri -or
        $uri.Scheme -ne "https" -or
        $uri.UserInfo -or
        $uri.Query -or
        $uri.Fragment -or
        $uri.AbsolutePath -notin "", "/"
    ) {
        throw "SKYBEAT_AGENT_SERVER_URL must be an HTTPS origin without credentials, path, query, or fragment for the local Caddy proxy."
    }

    $caddyHost = $uri.Host
    if ($caddyHost.Contains(":")) {
        $caddyHost = "[$caddyHost]"
    }
    return [PSCustomObject]@{
        ListenAddress = "$caddyHost`:$($uri.Port)"
        BindAddress = $uri.Host
    }
}

$root = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$caddyfile = Join-Path $root "Caddyfile.test"
$envFile = Join-Path $root ".env"
$endpointResolver = Join-Path $root "scripts\local-lan-endpoint.ps1"
# Preserve the historic repository-sibling Caddy state location so a locally
# trusted Caddy internal CA is not silently replaced by a new root.
$stateParent = Split-Path -Parent $root
$caddyDataRoot = Join-Path $stateParent "caddy-data"
$caddyConfigRoot = Join-Path $stateParent "caddy-config"

if (-not (Test-Path -LiteralPath $caddyfile -PathType Leaf)) {
    throw "Local Caddy configuration not found: Caddyfile.test"
}
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw "SkyBeat .env file not found at the repository root."
}
if (-not (Test-Path -LiteralPath $endpointResolver -PathType Leaf)) {
    throw "Local LAN endpoint resolver is missing. Restore scripts\\local-lan-endpoint.ps1 before starting Caddy."
}
if (-not (Get-Command caddy -ErrorAction SilentlyContinue)) {
    throw "Caddy is not available on PATH. Install the approved local Caddy binary before starting the local HTTPS proxy."
}

$loaded = Import-SkyBeatEnvironment -Path $envFile
if (-not $loaded.ContainsKey("SKYBEAT_ENV") -or $loaded["SKYBEAT_ENV"] -ne "development") {
    throw "start-caddy-local.ps1 requires SKYBEAT_ENV=development in the repository .env."
}
if (-not $loaded.ContainsKey("SKYBEAT_AGENT_SERVER_URL") -or -not $loaded["SKYBEAT_AGENT_SERVER_URL"]) {
    throw "SKYBEAT_AGENT_SERVER_URL is required to start the local HTTPS proxy."
}

. $endpointResolver
$endpointMode = if ($loaded.ContainsKey("SKYBEAT_LOCAL_ENDPOINT_MODE")) {
    $loaded["SKYBEAT_LOCAL_ENDPOINT_MODE"].ToLowerInvariant()
}
else {
    "configured"
}
if ($endpointMode -notin @("configured", "auto")) {
    throw "SKYBEAT_LOCAL_ENDPOINT_MODE must be configured or auto for the Windows development launcher."
}
$configuredAgentServerUrl = if ($AgentServerUrl) { $AgentServerUrl } else { $loaded["SKYBEAT_AGENT_SERVER_URL"] }
$resolvedEndpoint = Resolve-SkyBeatLocalEndpoint `
    -ConfiguredOrigin $configuredAgentServerUrl -Mode $endpointMode
$effectiveAgentServerUrl = $resolvedEndpoint.EffectiveOrigin
$tlsListener = Get-TlsListener -AgentServerUrl $effectiveAgentServerUrl
$env:SKYBEAT_LOCAL_TLS_ADDRESS = $tlsListener.ListenAddress
$env:SKYBEAT_LOCAL_TLS_BIND_ADDRESS = $tlsListener.BindAddress
$env:XDG_DATA_HOME = $caddyDataRoot
$env:XDG_CONFIG_HOME = $caddyConfigRoot

Set-Location $root
& caddy validate --config $caddyfile --adapter caddyfile
if ($LASTEXITCODE -ne 0) {
    throw "Local Caddy configuration validation failed."
}
if ($PreflightOnly) {
    Write-Host "LAN endpoint: $effectiveAgentServerUrl ($($resolvedEndpoint.Resolution))"
    return
}

caddy run --config $caddyfile --adapter caddyfile
