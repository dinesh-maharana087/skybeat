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

function Get-LocalRuntimeDirectory {
    param([Parameter(Mandatory)][string]$Root)

    return Join-Path $Root ".skybeat-local-runtime"
}

function Get-LocalWorkerStatePath {
    param([Parameter(Mandatory)][string]$Root)

    return Join-Path (Get-LocalRuntimeDirectory -Root $Root) "notification-worker.json"
}

function Get-LocalWorkerStartupGuardName {
    param([Parameter(Mandatory)][string]$Root)

    $bytes = [Text.Encoding]::UTF8.GetBytes($Root.ToLowerInvariant())
    $hash = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = $hash.ComputeHash($bytes)
    }
    finally {
        $hash.Dispose()
    }
    $suffix = ([BitConverter]::ToString($digest)).Replace("-", "").Substring(0, 16)
    return "Local\SkyBeatNotificationWorkerStartup-$suffix"
}

function Invoke-LocalWorkerStartupGuard {
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][scriptblock]$Action
    )

    $mutex = [System.Threading.Mutex]::new($false, (Get-LocalWorkerStartupGuardName -Root $Root))
    $acquired = $false
    try {
        try {
            $acquired = $mutex.WaitOne([TimeSpan]::FromSeconds(10))
        }
        catch [System.Threading.AbandonedMutexException] {
            $acquired = $true
        }
        if (-not $acquired) {
            throw "Another SkyBeat local launcher is starting the notification worker. Wait for it to finish, then rerun the launcher."
        }
        return & $Action
    }
    finally {
        if ($acquired) {
            $mutex.ReleaseMutex()
        }
        $mutex.Dispose()
    }
}

function Test-PathEquals {
    param(
        [Parameter(Mandatory)][string]$Left,
        [Parameter(Mandatory)][string]$Right
    )

    return [String]::Equals($Left, $Right, [StringComparison]::OrdinalIgnoreCase)
}

function Get-ProcessDetails {
    param([Parameter(Mandatory)][int]$ProcessId)

    return Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
}

function Get-ProcessCreationTimeUtc {
    param([Parameter(Mandatory)][object]$Process)

    return ([datetime]$Process.CreationDate).ToUniversalTime().ToString("o")
}

function Test-ExpectedWorkerCommand {
    param([AllowNull()][string]$CommandLine)

    return $null -ne $CommandLine -and $CommandLine -match "(?i)(?:^|\s)-m\s+app\.worker(?:\s|$)"
}

function Read-LocalWorkerState {
    param([Parameter(Mandatory)][string]$StatePath)

    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
        return $null
    }
    try {
        $state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json -ErrorAction Stop
        if (
            $null -eq $state -or
            $null -eq $state.ProcessId -or
            -not $state.CreationTimeUtc -or
            -not $state.RepositoryRoot -or
            -not $state.Python -or
            -not $state.ServerDirectory -or
            -not $state.WorkerCommand
        ) {
            return $null
        }
        return $state
    }
    catch {
        return $null
    }
}

function Write-LocalWorkerState {
    param(
        [Parameter(Mandatory)][string]$StatePath,
        [Parameter(Mandatory)][object]$State
    )

    $stateDirectory = Split-Path -Parent $StatePath
    New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
    $temporaryPath = Join-Path $stateDirectory ("notification-worker.$([guid]::NewGuid().ToString('N')).tmp")
    try {
        [IO.File]::WriteAllText(
            $temporaryPath,
            ($State | ConvertTo-Json -Depth 3),
            [Text.UTF8Encoding]::new($false)
        )
        Move-Item -LiteralPath $temporaryPath -Destination $StatePath -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
}

function Remove-LocalWorkerState {
    param([Parameter(Mandatory)][string]$StatePath)

    if (Test-Path -LiteralPath $StatePath -PathType Leaf) {
        Remove-Item -LiteralPath $StatePath -Force
    }
}

function Test-LocalWorkerState {
    param(
        [AllowNull()][object]$State,
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][string]$Python,
        [Parameter(Mandatory)][string]$ServerDirectory
    )

    if (
        $null -eq $State -or
        -not (Test-PathEquals -Left $State.RepositoryRoot -Right $Root) -or
        -not (Test-PathEquals -Left $State.Python -Right $Python) -or
        -not (Test-PathEquals -Left $State.ServerDirectory -Right $ServerDirectory) -or
        $State.WorkerCommand -ne "-m app.worker"
    ) {
        return $null
    }
    $process = Get-ProcessDetails -ProcessId ([int]$State.ProcessId)
    if (
        $null -eq $process -or
        -not (Test-PathEquals -Left $process.ExecutablePath -Right $Python) -or
        -not (Test-ExpectedWorkerCommand -CommandLine $process.CommandLine) -or
        (Get-ProcessCreationTimeUtc -Process $process) -ne $State.CreationTimeUtc
    ) {
        return $null
    }
    return $process
}

function Get-LocalWorkerRoots {
    try {
        $candidates = @(
            Get-CimInstance -ClassName Win32_Process -Filter "Name = 'python.exe'" -ErrorAction Stop |
                Where-Object { Test-ExpectedWorkerCommand -CommandLine $_.CommandLine }
        )
    }
    catch {
        throw "Unable to inspect local Python processes for SkyBeat worker ownership. Resolve the local process-inspection error before rerunning the launcher."
    }
    $candidateIds = [Collections.Generic.HashSet[int]]::new()
    foreach ($candidate in $candidates) {
        $null = $candidateIds.Add([int]$candidate.ProcessId)
    }
    return @(
        $candidates | Where-Object {
            -not $candidateIds.Contains([int]$_.ParentProcessId)
        }
    )
}

function Find-UntrackedLocalSkyBeatWorkers {
    param([AllowNull()][object]$OwnedWorker)

    return @(
        Get-LocalWorkerRoots | Where-Object {
            $null -eq $OwnedWorker -or [int]$_.ProcessId -ne [int]$OwnedWorker.ProcessId
        }
    )
}

function Get-LocalWorkerProcessTree {
    param([Parameter(Mandatory)][object]$RootWorker)

    $allProcesses = @(Get-CimInstance -ClassName Win32_Process -ErrorAction Stop)
    $processesByParent = @{}
    foreach ($process in $allProcesses) {
        $parentId = [int]$process.ParentProcessId
        if (-not $processesByParent.ContainsKey($parentId)) {
            $processesByParent[$parentId] = @()
        }
        $processesByParent[$parentId] += $process
    }
    $tree = @($RootWorker)
    $pending = [Collections.Generic.Queue[int]]::new()
    $pending.Enqueue([int]$RootWorker.ProcessId)
    while ($pending.Count -gt 0) {
        $parentId = $pending.Dequeue()
        foreach ($child in @($processesByParent[$parentId])) {
            if (Test-ExpectedWorkerCommand -CommandLine $child.CommandLine) {
                $tree += $child
                $pending.Enqueue([int]$child.ProcessId)
            }
        }
    }
    return $tree
}

function Wait-ForLocalWorkerProcessesToExit {
    param([Parameter(Mandatory)][object[]]$Processes)

    foreach ($attempt in 1..12) {
        $stillRunning = @(
            $Processes | Where-Object {
                $null -ne (Get-ProcessDetails -ProcessId ([int]$_.ProcessId))
            }
        )
        if ($stillRunning.Count -eq 0) {
            return $true
        }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

function Stop-LocalOwnedWorker {
    param(
        [Parameter(Mandatory)][object]$OwnedWorker,
        [Parameter(Mandatory)][string]$StatePath,
        [Parameter(Mandatory)][object]$State,
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][string]$Python,
        [Parameter(Mandatory)][string]$ServerDirectory
    )

    if ($null -eq (Test-LocalWorkerState -State $State -Root $Root -Python $Python -ServerDirectory $ServerDirectory)) {
        throw "The recorded SkyBeat notification worker no longer matches its ownership state. It was not stopped; inspect the recorded process manually."
    }
    $processTree = @(Get-LocalWorkerProcessTree -RootWorker $OwnedWorker)
    $children = @($processTree | Where-Object { [int]$_.ProcessId -ne [int]$OwnedWorker.ProcessId })
    foreach ($process in $children) {
        Stop-Process -Id ([int]$process.ProcessId) -ErrorAction SilentlyContinue
    }
    Stop-Process -Id ([int]$OwnedWorker.ProcessId) -ErrorAction SilentlyContinue
    if (-not (Wait-ForLocalWorkerProcessesToExit -Processes $processTree)) {
        foreach ($process in $children) {
            Stop-Process -Id ([int]$process.ProcessId) -Force -ErrorAction SilentlyContinue
        }
        Stop-Process -Id ([int]$OwnedWorker.ProcessId) -Force -ErrorAction SilentlyContinue
        if (-not (Wait-ForLocalWorkerProcessesToExit -Processes $processTree)) {
            throw "Unable to stop the previous launcher-owned notification worker. It was not replaced; inspect its recorded PID before rerunning the launcher."
        }
    }
    Remove-LocalWorkerState -StatePath $StatePath
}

function Format-UntrackedWorkerConflict {
    param([Parameter(Mandatory)][object[]]$Workers)

    $details = @(
        $Workers | ForEach-Object {
            "PID $($_.ProcessId): $($_.CommandLine)"
        }
    ) -join "; "
    return "Untracked SkyBeat notification worker conflict: $details. It was not stopped. Stop or investigate that worker manually before rerunning the launcher."
}

function Start-LocalNotificationWorker {
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][string]$Python,
        [Parameter(Mandatory)][string]$ServerDirectory
    )

    return Invoke-LocalWorkerStartupGuard -Root $Root -Action {
        $statePath = Get-LocalWorkerStatePath -Root $Root
        $state = Read-LocalWorkerState -StatePath $statePath
        $ownedWorker = Test-LocalWorkerState `
            -State $state `
            -Root $Root `
            -Python $Python `
            -ServerDirectory $ServerDirectory
        $untrackedWorkers = @(Find-UntrackedLocalSkyBeatWorkers -OwnedWorker $ownedWorker)
        if ($untrackedWorkers.Count -gt 0) {
            throw (Format-UntrackedWorkerConflict -Workers $untrackedWorkers)
        }
        $restarted = $null -ne $ownedWorker
        if ($restarted) {
            Stop-LocalOwnedWorker `
                -OwnedWorker $ownedWorker `
                -StatePath $statePath `
                -State $state `
                -Root $Root `
                -Python $Python `
                -ServerDirectory $ServerDirectory
        }
        elseif ($null -ne $state) {
            Remove-LocalWorkerState -StatePath $statePath
        }

        try {
            $worker = Start-Process -FilePath $Python `
                -ArgumentList @("-m", "app.worker") `
                -WorkingDirectory $ServerDirectory `
                -WindowStyle Hidden `
                -PassThru
        }
        catch {
            Remove-LocalWorkerState -StatePath $statePath
            throw "Notification worker failed to start. Verify the protected local configuration and review the worker's non-secret logs."
        }

        $startedWorker = $null
        foreach ($attempt in 1..12) {
            $startedWorker = Get-ProcessDetails -ProcessId $worker.Id
            if (
                $null -ne $startedWorker -and
                (Test-PathEquals -Left $startedWorker.ExecutablePath -Right $Python) -and
                (Test-ExpectedWorkerCommand -CommandLine $startedWorker.CommandLine)
            ) {
                Start-Sleep -Milliseconds 750
                $startedWorker = Get-ProcessDetails -ProcessId $worker.Id
                if ($null -ne $startedWorker) {
                    break
                }
            }
            Start-Sleep -Milliseconds 250
        }
        if ($null -eq $startedWorker) {
            Remove-LocalWorkerState -StatePath $statePath
            throw "Notification worker failed to start. Verify the protected local configuration and review the worker's non-secret logs."
        }
        $newState = [PSCustomObject]@{
            ProcessId = [int]$startedWorker.ProcessId
            CreationTimeUtc = Get-ProcessCreationTimeUtc -Process $startedWorker
            RepositoryRoot = $Root
            Python = $Python
            ServerDirectory = $ServerDirectory
            WorkerCommand = "-m app.worker"
        }
        Write-LocalWorkerState -StatePath $statePath -State $newState
        if ($null -eq (Test-LocalWorkerState -State $newState -Root $Root -Python $Python -ServerDirectory $ServerDirectory)) {
            Remove-LocalWorkerState -StatePath $statePath
            throw "Notification worker failed ownership validation after startup. It was not reported as running."
        }
        if ($restarted) {
            return "restarted"
        }
        return "started"
    }
}

function Test-LocalUvicornHealth {
    try {
        $response = Invoke-WebRequest `
            -UseBasicParsing `
            -Uri "http://127.0.0.1:8000/livez" `
            -TimeoutSec 3 `
            -ErrorAction Stop
    }
    catch {
        return $false
    }
    return $response.StatusCode -eq 200
}

function Test-ProcessHasExpectedLauncherAncestor {
    param(
        [Parameter(Mandatory)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory)][string]$ExpectedPython
    )

    $processDetails = Get-ProcessDetails -ProcessId $Process.Id
    foreach ($depth in 1..8) {
        if ($null -eq $processDetails) {
            return $false
        }
        if (
            (Test-PathEquals -Left $processDetails.ExecutablePath -Right $ExpectedPython) -and
            $processDetails.CommandLine -match "(?i)(?:^|\s)-m\s+uvicorn\s+app\.main:create_app\s+--factory\s+--host\s+127\.0\.0\.1\s+--port\s+8000(?:\s|$)"
        ) {
            return $true
        }
        $processDetails = Get-ProcessDetails -ProcessId ([int]$processDetails.ParentProcessId)
    }
    return $false
}

function Test-ExistingLocalSkyBeatUvicorn {
    param(
        [Parameter(Mandatory)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory)][string]$Python
    )

    if ($Process.ProcessName -ne "python") {
        return $false
    }
    $processDetails = Get-ProcessDetails -ProcessId $Process.Id
    if ($null -eq $processDetails) {
        throw "Unable to inspect the local process on TCP port 8000. Do not start another server until the port owner is identified."
    }
    if (
        $processDetails.CommandLine -notmatch "(?i)(?:^|\s)-m\s+uvicorn\s+app\.main:create_app\s+--factory\s+--host\s+127\.0\.0\.1\s+--port\s+8000(?:\s|$)"
    ) {
        return $false
    }
    if (-not (Test-ProcessHasExpectedLauncherAncestor -Process $Process -ExpectedPython $Python)) {
        return $false
    }
    return Test-LocalUvicornHealth
}

function Test-LocalUvicornReuse {
    param([Parameter(Mandatory)][string]$Python)

    $existing = Get-ListeningProcess -Address "127.0.0.1" -Port 8000
    if ($null -eq $existing) {
        return $false
    }
    if (-not (Test-ExistingLocalSkyBeatUvicorn -Process $existing -Python $Python)) {
        throw "TCP port 8000 is already owned by $($existing.ProcessName) (PID $($existing.Id)) and is not a SkyBeat Uvicorn process for this checkout. Stop the conflicting process manually before rerunning the launcher."
    }
    if (-not (Test-LocalUvicornHealth)) {
        throw "Existing SkyBeat Uvicorn on TCP port 8000 failed /livez. Stop the unhealthy local process manually before rerunning the launcher."
    }
    return $true
}

$root = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$envFile = Join-Path $root ".env"
$python = Join-Path $root ".venv\Scripts\python.exe"
$serverDirectory = Join-Path $root "server"
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

Push-Location $serverDirectory
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

$reuseExistingUvicorn = Test-LocalUvicornReuse -Python $python

$workerStatus = Start-LocalNotificationWorker `
    -Root $root `
    -Python $python `
    -ServerDirectory $serverDirectory
Write-Host "Notification worker: $workerStatus"

if ($reuseExistingUvicorn) {
    Write-Host "Uvicorn: running"
    return
}

Set-Location $serverDirectory
Write-Host "Uvicorn: running"
if ($httpsAgentEndpoint) {
    & $python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
}
else {
    & $python -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
}
