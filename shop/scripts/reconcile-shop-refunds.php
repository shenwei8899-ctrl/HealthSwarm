<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'tests' . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\service\RefundService;

$limit = isset($argv[1]) ? (int)$argv[1] : 50;
$completed = RefundService::reconcileLocalCompletions($limit);
echo sprintf("Reconciled %d externally successful refund transaction(s).\n", $completed);
