$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/InventoryServiceTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "Shop core integration tests failed."
    }
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/MockNutritionCatalogTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "MOCK nutrition catalog integration tests failed."
    }
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/ProductCenterAggregationTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "Product Center aggregation integration tests failed."
    }
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/ProductMatchServiceTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "Product matching integration tests failed."
    }
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/ShoppingListServiceTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "Shopping list integration tests failed."
    }
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/ShoppingListAdminWorklistTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "Shopping-list admin worklist integration tests failed."
    }
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/CartProvenanceServiceTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "Cart provenance integration tests failed."
    }
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/OrderServiceTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "Order service integration tests failed."
    }
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/PaymentFulfillmentServiceTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "Payment and fulfillment integration tests failed."
    }
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/OrderSubstitutionServiceTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "Order substitution integration tests failed."
    }
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/SupplierSyncServiceTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "Supplier sync integration tests failed."
    }
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/AfterSalesApplicationServiceTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "After-sales application integration tests failed."
    }
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/AfterSalesServiceTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "After-sales service integration tests failed."
    }
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/RefundServiceTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "Refund transaction integration tests failed."
    }
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/CatalogOrderQueryServiceTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "Catalog and order query integration tests failed."
    }
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/VersionedRouteTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "Versioned route integration tests failed."
    }
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/AdminSupplyChainModulesTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "Supply-chain admin module integration tests failed."
    }
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/AdminSupplierScopeServiceTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "Admin supplier scope integration tests failed."
    }
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/SupplyReportTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "Supply reports integration tests failed."
    }
    docker compose -f docker-compose.preview.yml exec -T app php tests/integration/SupplierReconciliationServiceTest.php
    if ($LASTEXITCODE -ne 0) {
        throw "Supplier reconciliation integration tests failed."
    }
    $httpStatus = curl.exe -sS -o NUL -w "%{http_code}" -X POST "http://127.0.0.1:8080/index.php/api/v1/shop/matching/preview"
    if ($httpStatus -ne "401") {
        throw "Versioned route HTTP test failed with status $httpStatus."
    }
    $catalogStatus = curl.exe -sS -o NUL -w "%{http_code}" "http://127.0.0.1:8080/index.php/api/v1/shop/goods?page_size=1"
    if ($catalogStatus -ne "200") {
        throw "Public catalog HTTP test failed with status $catalogStatus."
    }
    $orderStatus = curl.exe -sS -o NUL -w "%{http_code}" "http://127.0.0.1:8080/index.php/api/v1/shop/orders"
    if ($orderStatus -ne "401") {
        throw "Protected order HTTP test failed with status $orderStatus."
    }
}
finally {
    Pop-Location
}
