<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\service\SupplierReconciliationService;
use think\Db;

function reconciliationAssertSame($expected, $actual, $message)
{
    if ($expected !== $actual) {
        throw new RuntimeException($message . ': expected ' . var_export($expected, true) . ', got ' . var_export($actual, true));
    }
}

$now = time();
$key = strtoupper(bin2hex(random_bytes(4)));
Db::startTrans();
try {
    $supplierId = Db::name('shop_supplier')->insertGetId([
        'code' => 'RECON-' . $key,
        'name' => '对账测试供应商',
        'company_name' => '对账测试供应商有限公司',
        'contact_name' => '',
        'contact_mobile' => '',
        'fulfillment_mode' => 'SUPPLIER_DIRECT',
        'settlement_mode' => 'MONTHLY',
        'api_type' => 'MANUAL',
        'priority' => 0,
        'status' => 'normal',
        'createtime' => $now,
        'updatetime' => $now,
    ]);
    Db::name('shop_order_supplier')->insert([
        'supplier_order_sn' => 'RECON-ORDER-' . $key,
        'order_id' => 900000,
        'order_sn' => 'RECON-MAIN-' . $key,
        'supplier_id' => $supplierId,
        'warehouse_id' => 0,
        'fulfillment_mode' => 'SUPPLIER_DIRECT',
        'goods_amount' => '150.00',
        'shipping_fee' => '0.00',
        'supply_amount' => '100.00',
        'status' => 'COMPLETED',
        'completed_at' => $now,
        'createtime' => $now,
        'updatetime' => $now,
    ]);
    $aftersalesId = 900000 + random_int(1, 99999);
    Db::name('shop_aftersales_ext')->insert([
        'aftersales_id' => $aftersalesId,
        'supplier_order_id' => 0,
        'supplier_id' => $supplierId,
        'warehouse_id' => 0,
        'return_status' => 'NONE',
        'restock_quantity' => 0,
        'idempotency_key' => 'RECON-' . $key,
        'createtime' => $now,
        'updatetime' => $now,
    ]);
    Db::name('shop_refund_transaction')->insert([
        'refund_sn' => 'RECON-REFUND-' . $key,
        'aftersales_id' => $aftersalesId,
        'order_id' => 900000,
        'order_sn' => 'RECON-MAIN-' . $key,
        'channel' => 'manual',
        'amount' => '20.00',
        'local_action' => 'REFUND_ONLY',
        'external_required' => 0,
        'status' => 'COMPLETED',
        'gateway_refund_id' => '',
        'attempt_count' => 1,
        'error_message' => '',
        'completed_at' => $now,
        'createtime' => $now,
        'updatetime' => $now,
    ]);

    $today = date('Y-m-d', $now);
    $row = SupplierReconciliationService::generate($supplierId, $today, $today, 1, '测试账期');
    reconciliationAssertSame(1, (int)$row['order_count'], 'Reconciliation must count completed supplier orders');
    reconciliationAssertSame('100.00', number_format((float)$row['supply_amount'], 2, '.', ''), 'Reconciliation must sum supply amounts');
    reconciliationAssertSame('20.00', number_format((float)$row['refund_amount'], 2, '.', ''), 'Reconciliation must deduct completed refunds');
    reconciliationAssertSame('80.00', number_format((float)$row['payable_amount'], 2, '.', ''), 'Reconciliation must calculate payable amount');

    $repeated = SupplierReconciliationService::generate($supplierId, $today, $today, 1);
    reconciliationAssertSame((int)$row['id'], (int)$repeated['id'], 'Generating the same period must be idempotent');
    reconciliationAssertSame(1, Db::name('shop_supplier_reconciliation')->where('supplier_id', $supplierId)->count(), 'Idempotent generation must not duplicate rows');

    $disputed = SupplierReconciliationService::dispute($row['id'], '金额待核对', 1);
    reconciliationAssertSame('DISPUTED', $disputed['status'], 'Draft reconciliation must support disputes');
    $confirmed = SupplierReconciliationService::confirm($row['id'], 1);
    reconciliationAssertSame('CONFIRMED', $confirmed['status'], 'Disputed reconciliation must be confirmable');
    $paid = SupplierReconciliationService::markPaid($row['id'], 1);
    reconciliationAssertSame('PAID', $paid['status'], 'Confirmed reconciliation must support payment confirmation');
    $repeatedPaid = SupplierReconciliationService::markPaid($row['id'], 1);
    reconciliationAssertSame('PAID', $repeatedPaid['status'], 'Payment confirmation must be idempotent');

    Db::rollback();
} catch (Throwable $e) {
    Db::rollback();
    throw $e;
}

echo "Supplier reconciliation integration test passed.\n";
