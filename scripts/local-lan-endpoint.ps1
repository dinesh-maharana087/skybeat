function Test-SkyBeatPrivateIPv4Address {
    param([Parameter(Mandatory)][string]$Address)

    $parsed = $null
    if (-not [System.Net.IPAddress]::TryParse($Address, [ref]$parsed)) {
        return $false
    }
    $bytes = $parsed.GetAddressBytes()
    if ($bytes.Length -ne 4) {
        return $false
    }
    return (
        $bytes[0] -eq 10 -or
        ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or
        ($bytes[0] -eq 192 -and $bytes[1] -eq 168)
    )
}

function Test-SkyBeatTrustedLanAdapter {
    param([Parameter(Mandatory)]$Adapter)

    if ($Adapter.Status -ne "Up" -or $Adapter.HardwareInterface -ne $true) {
        return $false
    }
    $identity = "$($Adapter.InterfaceAlias) $($Adapter.InterfaceDescription)"
    return $identity -notmatch "(?i)vpn|tunnel|tap|tun|wireguard|wintun|tailscale|zerotier|virtual|hyper-v|vmware|virtualbox|loopback|bluetooth"
}

function Get-SkyBeatTrustedLanCandidate {
    $adapters = @{}
    foreach ($adapter in @(Get-NetAdapter -IncludeHidden -ErrorAction Stop)) {
        $adapters[[int]$adapter.ifIndex] = $adapter
    }

    $addressesByInterface = @{}
    foreach ($address in @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop)) {
        if ($address.AddressState -ne "Preferred" -or -not (Test-SkyBeatPrivateIPv4Address -Address $address.IPAddress)) {
            continue
        }
        $index = [int]$address.InterfaceIndex
        if (-not $addressesByInterface.ContainsKey($index)) {
            $addressesByInterface[$index] = @()
        }
        $addressesByInterface[$index] += $address
    }

    $candidates = @()
    $routes = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix "0.0.0.0/0" -ErrorAction Stop) |
        Sort-Object RouteMetric, InterfaceMetric, ifIndex
    foreach ($route in $routes) {
        $index = [int]$route.ifIndex
        if (-not $adapters.ContainsKey($index)) {
            continue
        }
        $adapter = $adapters[$index]
        if (-not (Test-SkyBeatTrustedLanAdapter -Adapter $adapter) -or -not $addressesByInterface.ContainsKey($index)) {
            continue
        }
        foreach ($address in @($addressesByInterface[$index] | Sort-Object IPAddress)) {
            $candidates += [PSCustomObject]@{
                InterfaceIndex = $index
                InterfaceAlias = [string]$adapter.InterfaceAlias
                IPAddress = [string]$address.IPAddress
                RouteMetric = [int]$route.RouteMetric
                InterfaceMetric = [int]$route.InterfaceMetric
            }
        }
    }
    return $candidates
}

function Resolve-SkyBeatLocalEndpoint {
    param(
        [Parameter(Mandatory)][string]$ConfiguredOrigin,
        [Parameter(Mandatory)][ValidateSet("configured", "auto")][string]$Mode
    )

    try {
        $configuredUri = [Uri]$ConfiguredOrigin
    }
    catch {
        throw "SKYBEAT_AGENT_SERVER_URL must be an absolute HTTPS origin before local LAN endpoint resolution."
    }
    if (
        -not $configuredUri.IsAbsoluteUri -or
        $configuredUri.Scheme -ne "https" -or
        $configuredUri.UserInfo -or
        $configuredUri.Query -or
        $configuredUri.Fragment -or
        $configuredUri.AbsolutePath -notin "", "/"
    ) {
        throw "SKYBEAT_AGENT_SERVER_URL must be an HTTPS origin without credentials, path, query, or fragment before local LAN endpoint resolution."
    }

    $configuredAddress = $null
    if (-not [System.Net.IPAddress]::TryParse($configuredUri.Host, [ref]$configuredAddress)) {
        return [PSCustomObject]@{
            EffectiveOrigin = $configuredUri.GetLeftPart([System.UriPartial]::Authority)
            InterfaceAlias = $null
            Resolution = "configured-hostname"
        }
    }
    if (-not (Test-SkyBeatPrivateIPv4Address -Address $configuredUri.Host)) {
        throw "SKYBEAT_AGENT_SERVER_URL must use a private IPv4 address for local LAN Caddy, or a deliberate static hostname."
    }

    $candidates = @(Get-SkyBeatTrustedLanCandidate)
    $configuredCandidate = @($candidates | Where-Object { $_.IPAddress -eq $configuredUri.Host } | Select-Object -First 1)
    if ($configuredCandidate.Count -eq 1) {
        return [PSCustomObject]@{
            EffectiveOrigin = $configuredUri.GetLeftPart([System.UriPartial]::Authority)
            InterfaceAlias = $configuredCandidate[0].InterfaceAlias
            Resolution = "configured-local-ip"
        }
    }
    if ($Mode -eq "configured") {
        throw "Configured HTTPS endpoint host '$($configuredUri.Host)' is not assigned to an active trusted LAN interface. Update the endpoint, or set SKYBEAT_LOCAL_ENDPOINT_MODE=auto for Windows development discovery."
    }
    if ($candidates.Count -eq 0) {
        throw "No trusted Windows LAN interface with an active private IPv4 default route was found. Check Wi-Fi/Ethernet connectivity, or configure a deliberate static endpoint."
    }

    $selected = $candidates[0]
    $builder = [System.UriBuilder]::new($configuredUri)
    $builder.Host = $selected.IPAddress
    return [PSCustomObject]@{
        EffectiveOrigin = $builder.Uri.GetLeftPart([System.UriPartial]::Authority)
        InterfaceAlias = $selected.InterfaceAlias
        Resolution = "auto-default-route"
    }
}
