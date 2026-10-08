param([int]$Limit = 50)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    docker compose -f docker-compose.preview.yml exec -T app php scripts/retry-shop-supplier-sync.php $Limit
    if ($LASTEXITCODE -ne 0) {
        throw "Supplier sync retry failed."
    }
}
finally {
    Pop-Location
}
