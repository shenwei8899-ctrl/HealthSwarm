param(
    [int]$Limit = 50,
    [string]$ComposeFile = "docker-compose.preview.yml"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    docker compose -f $ComposeFile exec -T app php scripts/reconcile-shop-refunds.php $Limit
    if ($LASTEXITCODE -ne 0) {
        throw "Refund reconciliation failed."
    }
}
finally {
    Pop-Location
}
