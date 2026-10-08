<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'bootstrap.php';

foreach (['product_sales', 'orders', 'supplier_fulfillment', 'inventory', 'refunds', 'expiry'] as $type) {
    $rows = \addons\shop\library\service\SupplyReportService::rows($type);
    if (!is_array($rows)) {
        throw new RuntimeException('Supply report did not return rows: ' . $type);
    }
    foreach ($rows as $row) {
        foreach (['dimension', 'metric1', 'metric2', 'metric3', 'unit_label'] as $field) {
            if (!array_key_exists($field, $row)) {
                throw new RuntimeException('Supply report is missing field ' . $field . ': ' . $type);
            }
        }
    }
}

echo "Supply reports integration test passed.\n";
