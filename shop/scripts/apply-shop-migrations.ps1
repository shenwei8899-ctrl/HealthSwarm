param(
    [string]$ComposeFile = "docker-compose.preview.yml",
    [string]$Database = "healthflow",
    [string]$User = "healthflow",
    [string]$Password = "healthflow"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$composePath = Join-Path $projectRoot $ComposeFile
$migrationPath = Join-Path $projectRoot "database\postgresql\migrations"
if (-not (Test-Path -LiteralPath $composePath -PathType Leaf)) { throw "Compose file not found: $composePath" }
if (-not (Test-Path -LiteralPath $migrationPath -PathType Container)) { throw "Migration directory not found: $migrationPath" }

function Invoke-Psql([string]$SqlFile) {
    Get-Content -LiteralPath $SqlFile -Raw -Encoding UTF8 |
        docker compose -f $composePath exec -T -e "PGPASSWORD=$Password" db psql -v ON_ERROR_STOP=1 -U $User -d $Database
    if ($LASTEXITCODE -ne 0) { throw "Migration failed: $SqlFile" }
}

Push-Location $projectRoot
try {
    foreach ($file in (Get-ChildItem -LiteralPath $migrationPath -Filter "*.sql" -File | Sort-Object Name)) {
        $version = [System.IO.Path]::GetFileNameWithoutExtension($file.Name)
        $escaped = $version.Replace("'", "''")
        $applied = docker compose -f $composePath exec -T -e "PGPASSWORD=$Password" db psql -At -U $User -d $Database -c "SELECT COUNT(*) FROM fa_shop_schema_migration WHERE version='$escaped';"
        if ($LASTEXITCODE -eq 0 -and [int]($applied | Select-Object -Last 1) -gt 0) { Write-Host "Skipping $($file.Name) (already applied)."; continue }
        Write-Host "Applying $($file.Name)..."
        Invoke-Psql $file.FullName
        docker compose -f $composePath exec -T -e "PGPASSWORD=$Password" db psql -v ON_ERROR_STOP=1 -U $User -d $Database -c "INSERT INTO fa_shop_schema_migration (version,description,executed_at) VALUES ('$escaped','$($file.Name)',EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::bigint) ON CONFLICT (version) DO UPDATE SET description=EXCLUDED.description, executed_at=EXCLUDED.executed_at;"
    }
}
finally { Pop-Location }
Write-Host "PostgreSQL shop migrations applied successfully."
