$ErrorActionPreference = "Stop"

$Root = "D:\learning\skybeat\skybeat"
$EnvFile = Join-Path $Root ".env"

if (-not (Test-Path $EnvFile)) {
    throw "SkyBeat .env file not found: $EnvFile"
}

Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()

    if (
        $line -and
        -not $line.StartsWith("#") -and
        $line.Contains("=")
    ) {
        $name, $value = $line -split "=", 2

        $name = $name.Trim()
        $value = $value.Trim()

        [Environment]::SetEnvironmentVariable(
            $name,
            $value,
            "Process"
        )
    }
}

Set-Location "$Root\server"

Write-Host "Starting SkyBeat..."
Write-Host "Uvicorn: http://127.0.0.1:8000"
Write-Host "External HTTPS is provided by Caddy."

& "$Root\.venv\Scripts\python.exe" `
    -m uvicorn app.main:create_app `
    --factory `
    --host 127.0.0.1 `
    --port 8000