<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\service\InventoryService;
use think\Db;

function assertSameValue($expected, $actual, $message)
{
    if ($expected !== $actual) {
        throw new RuntimeException($message . ': expected ' . var_export($expected, true) . ', got ' . var_export($actual, true));
    }
}

$stock = Db::name('shop_warehouse_sku')
    ->where('on_hand_qty - locked_qty - unavailable_qty', '>=', 2)
    ->order('id ASC')
    ->find();
if (!$stock) {
    throw new RuntimeException('No inventory row is available for integration testing.');
}

$testRun = 'TEST-' . date('YmdHis') . '-' . bin2hex(random_bytes(3));
$original = InventoryService::getAvailability($stock['id']);

Db::startTrans();
try {
    $reserveKey = $testRun . '-RELEASE';
    InventoryService::reserve($reserveKey, $testRun, [
        ['warehouse_sku_id' => $stock['id'], 'quantity' => 1],
    ], time() + 600);
    $reserved = InventoryService::getAvailability($stock['id']);
    assertSameValue((int)$original['locked_qty'] + 1, (int)$reserved['locked_qty'], 'Reserve must increase locked quantity');
    assertSameValue((int)$original['available_qty'] - 1, (int)$reserved['available_qty'], 'Reserve must reduce available quantity');

    InventoryService::reserve($reserveKey, $testRun, [
        ['warehouse_sku_id' => $stock['id'], 'quantity' => 1],
    ], time() + 600);
    $idempotentReserve = InventoryService::getAvailability($stock['id']);
    assertSameValue((int)$reserved['locked_qty'], (int)$idempotentReserve['locked_qty'], 'Repeated reserve must be idempotent');

    assertSameValue(1, InventoryService::releaseByBizKey($reserveKey), 'Release must change one reservation');
    assertSameValue(0, InventoryService::releaseByBizKey($reserveKey), 'Repeated release must be idempotent');
    $released = InventoryService::getAvailability($stock['id']);
    assertSameValue((int)$original['locked_qty'], (int)$released['locked_qty'], 'Release must restore locked quantity');
    assertSameValue((int)$original['available_qty'], (int)$released['available_qty'], 'Release must restore available quantity');

    $deductKey = $testRun . '-DEDUCT';
    InventoryService::reserve($deductKey, $testRun, [
        ['warehouse_sku_id' => $stock['id'], 'quantity' => 1],
    ], time() + 600);
    assertSameValue(1, InventoryService::deductByBizKey($deductKey), 'Deduct must change one reservation');
    assertSameValue(0, InventoryService::deductByBizKey($deductKey), 'Repeated deduct must be idempotent');
    $deducted = InventoryService::getAvailability($stock['id']);
    assertSameValue((int)$original['on_hand_qty'] - 1, (int)$deducted['on_hand_qty'], 'Deduct must reduce on-hand quantity');
    assertSameValue((int)$original['locked_qty'], (int)$deducted['locked_qty'], 'Deduct must release locked quantity');

    assertSameValue(true, InventoryService::restock($stock['id'], 1, $testRun . '-RESTOCK'), 'Restock must add inventory once');
    assertSameValue(false, InventoryService::restock($stock['id'], 1, $testRun . '-RESTOCK'), 'Repeated restock must be idempotent');
    $restocked = InventoryService::getAvailability($stock['id']);
    assertSameValue((int)$original['on_hand_qty'], (int)$restocked['on_hand_qty'], 'Restock must restore on-hand quantity');
    assertSameValue((int)$original['available_qty'], (int)$restocked['available_qty'], 'Restock must restore available quantity');

    Db::rollback();
} catch (Throwable $e) {
    Db::rollback();
    throw $e;
}

$afterRollback = InventoryService::getAvailability($stock['id']);
assertSameValue((int)$original['on_hand_qty'], (int)$afterRollback['on_hand_qty'], 'Outer rollback must preserve on-hand quantity');
assertSameValue((int)$original['locked_qty'], (int)$afterRollback['locked_qty'], 'Outer rollback must preserve locked quantity');
assertSameValue(0, Db::name('shop_stock_reservation')->where('biz_key', 'like', $testRun . '%')->count(), 'Test reservations must roll back');
assertSameValue(0, Db::name('shop_stock_flow')->where('biz_no', 'like', $testRun . '%')->count(), 'Test flows must roll back');

echo "InventoryService integration test passed.\n";

