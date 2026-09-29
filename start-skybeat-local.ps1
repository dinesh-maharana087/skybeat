[CmdletBinding()]
param(
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Stop"

function Import-SkyBeatEnvironment {
    param([Parameter(Mandatory)][string]$Path)

    $loaded = @{}
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
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
        $loaded[$name] = $value
    }
    return $loaded
}

function Test-HttpAgentOriginShape {
    param([Parameter(Mandatory)][string]$Origin)

    try {
        $uri = [Uri]$Origin
    }
    catch {
        throw "SKYBEAT_AGENT_SERVER_URL must be an absolute HTTP or HTTPS origin."
    }
    if (
        -not $uri.IsAbsoluteUri -or
        $uri.Scheme -ne "http" -or
        $uri.UserInfo -or
        $uri.Query -or
        $uri.Fragment -or
        $uri.AbsolutePath -notin "", "/"
    ) {
        throw "SKYBEAT_AGENT_SERVER_URL must be an HTTP origin without credentials, path, query, or fragment."
    }

    $address = $null
    if (-not [System.Net.IPAddress]::TryParse($uri.Host, [ref]$address)) {
        throw "HTTP SKYBEAT_AGENT_SERVER_URL requires a literal private or loopback IP address; hostnames are not allowed."
    }
}

function Get-CommandExitCode {
    param(
        [Parameter(Mandatory)][string]$Command,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Command @Arguments *> $null
        return $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Get-ListeningProcess {
    param(
        [Parameter(Mandatory)][string]$Address,
        [Parameter(Mandatory)][int]$Port
    )

    $listener = Get-NetTCPConnection -State Listen -LocalAddress $Address -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $listener) {
        return $null
    }
    return Get-Process -Id $listener.OwningProcess -ErrorAction Stop
}

function Start-LocalCaddy {
    param(
        [Parameter(Mandatory)][string]$CaddyLauncher,
        [Parameter(Mandatory)][string]$Address,
        [Parameter(Mandatory)][int]$Port
    )

    $existing = Get-ListeningProcess -Address $Address -Port $Port
    if ($null -ne $existing) {
        if ($existing.ProcessName -ne "caddy") {
            throw "TCP port $Port is already owned by $($existing.ProcessName), not Caddy. Stop the conflicting local process; the HTTPS agent endpoint must terminate at Caddy."
        }
        return
    }

    $powershell = Join-Path $PSHOME "powershell.exe"
    $caddyProcess = Start-Process -FilePath $powershell `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $CaddyLauncher) `
        -WindowStyle Hidden -PassThru
    foreach ($attempt in 1..20) {
        Start-Sleep -Milliseconds 250
        $listener = Get-ListeningProcess -Address $Address -Port $Port
        if ($null -ne $listener) {
            if ($listener.ProcessName -ne "caddy") {
                throw "TCP port $Port was claimed by $($listener.ProcessName), not Caddy."
            }
            return
        }
        if ($caddyProcess.HasExited) {
            break
        }
    }
    throw "Caddy did not start an HTTPS listener on TCP port $Port. Run .\\start-caddy-local.ps1 directly for its safe diagnostic output."
}

$root = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$envFile = Join-Path $root ".env"
$python = Join-Path $root ".venv\Scripts\python.exe"
$agentOriginValidator = Join-Path $root "scripts\validate-agent-server-url.py"
$caddyLauncher = Join-Path $root "start-caddy-local.ps1"

if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw "SkyBeat .env file not found at the repository root. Copy .env.example to .env and configure local development values."
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Local Python virtual environment not found at .venv\\Scripts\\python.exe. Recreate the ignored local environment; no application configuration was started."
}
if (-not (Test-Path -LiteralPath $agentOriginValidator -PathType Leaf)) {
    throw "Agent origin validator is missing from the repository. Restore scripts\\validate-agent-server-url.py before starting SkyBeat."
}

$loaded = Import-SkyBeatEnvironment -Path $envFile
if (-not $loaded.ContainsKey("SKYBEAT_ENV") -or $loaded["SKYBEAT_ENV"] -ne "development") {
    throw "start-skybeat-local.ps1 requires SKYBEAT_ENV=development in the repository .env. Do not use this local launcher with production configuration."
}

if ((Get-CommandExitCode -Command $python -Arguments @("--version")) -ne 0) {
    throw "The local .venv Python is unavailable. Recreate the ignored Python 3.12 virtual environment, then rerun this launcher."
}

if ($loaded.ContainsKey("SKYBEAT_AGENT_SERVER_URL") -and $loaded["SKYBEAT_AGENT_SERVER_URL"]) {
    $agentServerUrl = $loaded["SKYBEAT_AGENT_SERVER_URL"]
}
else {
    $agentServerUrl = "http://127.0.0.1:8000"
    [Environment]::SetEnvironmentVariable("SKYBEAT_AGENT_SERVER_URL", $agentServerUrl, "Process")
}

try {
    $agentUri = [Uri]$agentServerUrl
}
catch {
    throw "SKYBEAT_AGENT_SERVER_URL must be an absolute HTTP or HTTPS origin."
}

$insecureLocalAgentHttp = $agentUri.Scheme -eq "http"
$httpsAgentEndpoint = $agentUri.Scheme -eq "https"
if ($insecureLocalAgentHttp) {
    Test-HttpAgentOriginShape -Origin $agentServerUrl
    if ($loaded.ContainsKey("SKYBEAT_ALLOW_INSECURE_LOCAL_AGENT_SERVER")) {
        if ($loaded["SKYBEAT_ALLOW_INSECURE_LOCAL_AGENT_SERVER"].ToLowerInvariant() -ne "true") {
            throw "HTTP SKYBEAT_AGENT_SERVER_URL requires SKYBEAT_ALLOW_INSECURE_LOCAL_AGENT_SERVER=true in the repository .env."
        }
    }
    else {
        [Environment]::SetEnvironmentVariable(
            "SKYBEAT_ALLOW_INSECURE_LOCAL_AGENT_SERVER", "true", "Process"
        )
    }
}

$validatorArguments = @($agentOriginValidator, "--server", $agentServerUrl)
if ($insecureLocalAgentHttp) {
    $validatorArguments += "--allow-insecure-local-server"
}
if ((Get-CommandExitCode -Command $python -Arguments $validatorArguments) -ne 0) {
    throw "SKYBEAT_AGENT_SERVER_URL must be a valid HTTPS origin or an explicitly enabled literal private/loopback HTTP origin."
}

if (-not $httpsAgentEndpoint -and -not $insecureLocalAgentHttp) {
    throw "SKYBEAT_AGENT_SERVER_URL must use HTTPS or an explicitly enabled local HTTP origin."
}

Push-Location (Join-Path $root "server")
try {
    if (
        (Get-CommandExitCode -Command $python -Arguments @(
                "-c", "from app.config import Settings; Settings()"
            )) -ne 0
    ) {
        throw "SkyBeat Settings validation failed. Correct the non-secret local .env configuration and rerun; values are intentionally not displayed."
    }
}
finally {
    Pop-Location
}

if ($httpsAgentEndpoint) {
    if (-not (Test-Path -LiteralPath $caddyLauncher -PathType Leaf)) {
        throw "Local Caddy launcher is missing. Restore start-caddy-local.ps1 before using an HTTPS agent endpoint."
    }
    & $caddyLauncher -PreflightOnly
    $agentPort = $agentUri.Port
    if (-not $PreflightOnly) {
        Start-LocalCaddy -CaddyLauncher $caddyLauncher -Address $agentUri.Host -Port $agentPort
    }

    Write-Host "Environment: development"
    Write-Host "Uvicorn internal: http://127.0.0.1:8000"
    Write-Host "Agent HTTPS endpoint: $agentServerUrl"
    Write-Host "TLS termination: Caddy"
    Write-Host "Local browser/OIDC: http://127.0.0.1:8000"
    Write-Host "Browser HTTPS endpoint: $agentServerUrl"
    Write-Host "Configuration: OK"
}
else {
    Write-Host "Environment: development"
    Write-Host "Uvicorn bind: 0.0.0.0:8000"
    Write-Host "Local browser: http://127.0.0.1:8000"
    Write-Host "Agent endpoint: $agentServerUrl"
    Write-Host "Local insecure agent HTTP: explicitly enabled"
    Write-Host "TLS termination: not used for explicitly enabled local HTTP"
    Write-Host "Configuration: OK"
}

if ($PreflightOnly) {
    return
}

Set-Location (Join-Path $root "server")
if ($httpsAgentEndpoint) {
    & $python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
}
else {
    & $python -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
}
