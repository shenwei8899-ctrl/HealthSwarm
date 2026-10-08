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
$requiredTables = @(
    "fa_shop_goods_ext", "fa_shop_sku_ext", "fa_shop_ingredient", "fa_shop_ingredient_product_map",
    "fa_shop_supplier", "fa_shop_supplier_sku", "fa_shop_supplier_reconciliation", "fa_shop_supplier_sync_job",
    "fa_shop_admin_supplier_scope", "fa_shop_warehouse", "fa_shop_warehouse_sku", "fa_shop_stock_reservation",
    "fa_shop_stock_reservation_adjustment", "fa_shop_stock_flow", "fa_shop_shopping_list", "fa_shop_shopping_list_item",
    "fa_shop_cart_ext", "fa_shop_order_ext", "fa_shop_order_supplier", "fa_shop_order_goods_ext", "fa_shop_order_snapshot",
    "fa_shop_order_status_log", "fa_shop_order_shipment", "fa_shop_payment_transaction", "fa_shop_refund_transaction",
    "fa_shop_aftersales_inspection"
)
$quoted = ($requiredTables | ForEach-Object { "'$_'" }) -join ","
$query = "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public' AND tablename IN ($quoted) ORDER BY tablename;"
Push-Location $projectRoot
try {
    $actual = docker compose -f $composePath exec -T -e "PGPASSWORD=$Password" db psql -At -U $User -d $Database -c $query
    if ($LASTEXITCODE -ne 0) { throw "Unable to inspect PostgreSQL schema." }
}
finally { Pop-Location }
$missing = $requiredTables | Where-Object { $_ -notin $actual }
if ($missing) { throw "Missing required tables: $($missing -join ', ')" }
Write-Host "Verified $($requiredTables.Count) required shop tables in PostgreSQL."
