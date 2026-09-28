cd D:\learning\skybeat\skybeat

$env:XDG_DATA_HOME = "D:\learning\skybeat\caddy-data"
$env:XDG_CONFIG_HOME = "D:\learning\skybeat\caddy-config"

caddy run --config .\Caddyfile.test --adapter caddyfile