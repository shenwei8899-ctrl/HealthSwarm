<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'tests' . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\service\SupplierSyncService;

$limit = isset($argv[1]) ? max(1, (int)$argv[1]) : 50;
$jobs = SupplierSyncService::retryDue($limit);
echo json_encode(['processed' => count($jobs), 'jobs' => $jobs], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) . PHP_EOL;
