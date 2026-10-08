<?php

namespace addons\shop\library\service;

use RuntimeException;
use think\Db;

class SupplierReconciliationService
{
    public static function generate($supplierId, $periodStart, $periodEnd, $adminId = 0, $remark = '')
    {
        $supplierId = (int)$supplierId;
        list($periodStart, $periodEnd, $startTime, $endTime) = self::period($periodStart, $periodEnd);
        if (!Db::name('shop_supplier')->where('id', $supplierId)->find()) {
            throw new RuntimeException('供应商不存在', 404);
        }

        Db::startTrans();
        try {
            $existing = Db::name('shop_supplier_reconciliation')
                ->where('supplier_id', $supplierId)
                ->where('period_start', $periodStart)
                ->where('period_end', $periodEnd)
                ->lock(true)
                ->find();
            if ($existing && $existing['status'] !== 'DRAFT') {
                Db::commit();
                return self::detail((int)$existing['id']);
            }

            $orders = Db::name('shop_order_supplier')
                ->where('supplier_id', $supplierId)
                ->where('status', 'in', ['SHIPPED', 'COMPLETED'])
                ->where("COALESCE(NULLIF(completed_at,0),NULLIF(shipping_at,0),createtime) BETWEEN {$startTime} AND {$endTime}")
                ->field('COUNT(*) AS order_count,COALESCE(SUM(goods_amount),0) AS goods_amount,COALESCE(SUM(supply_amount),0) AS supply_amount')
                ->find();
            $refundAmount = (string)Db::name('shop_refund_transaction')
                ->alias('refund')
                ->join('__SHOP_AFTERSALES_EXT__ aftersales_ext', 'aftersales_ext.aftersales_id=refund.aftersales_id')
                ->where('aftersales_ext.supplier_id', $supplierId)
                ->where('refund.status', 'COMPLETED')
                ->where('refund.completed_at', 'between', [$startTime, $endTime])
                ->sum('refund.amount');
            $supplyAmount = (string)($orders['supply_amount'] ?? '0.00');
            $refundAmount = $refundAmount ?: '0.00';
            $payableAmount = bccomp($supplyAmount, $refundAmount, 2) >= 0
                ? bcsub($supplyAmount, $refundAmount, 2)
                : '0.00';
            $data = [
                'reconciliation_sn' => self::number($supplierId, $periodStart, $periodEnd),
                'supplier_id' => $supplierId,
                'period_start' => $periodStart,
                'period_end' => $periodEnd,
                'order_count' => (int)($orders['order_count'] ?? 0),
                'goods_amount' => (string)($orders['goods_amount'] ?? '0.00'),
                'supply_amount' => $supplyAmount,
                'refund_amount' => $refundAmount,
                'payable_amount' => $payableAmount,
                'admin_id' => (int)$adminId,
                'remark' => trim((string)$remark),
                'updatetime' => time(),
            ];
            if ($existing) {
                Db::name('shop_supplier_reconciliation')->where('id', (int)$existing['id'])->update($data);
                $id = (int)$existing['id'];
            } else {
                $data['status'] = 'DRAFT';
                $data['createtime'] = time();
                $id = (int)Db::name('shop_supplier_reconciliation')->insertGetId($data);
            }
            Db::commit();
            return self::detail($id);
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    public static function confirm($id, $adminId = 0)
    {
        return self::transition($id, ['DRAFT', 'DISPUTED'], 'CONFIRMED', [
            'confirmed_at' => time(), 'admin_id' => (int)$adminId,
        ]);
    }

    public static function dispute($id, $remark, $adminId = 0)
    {
        $remark = trim((string)$remark);
        if ($remark === '') {
            throw new RuntimeException('请填写争议原因');
        }
        return self::transition($id, ['DRAFT', 'CONFIRMED'], 'DISPUTED', [
            'remark' => $remark, 'admin_id' => (int)$adminId,
        ]);
    }

    public static function markPaid($id, $adminId = 0)
    {
        return self::transition($id, ['CONFIRMED'], 'PAID', [
            'paid_at' => time(), 'admin_id' => (int)$adminId,
        ]);
    }

    public static function detail($id)
    {
        $row = Db::name('shop_supplier_reconciliation')->where('id', (int)$id)->find();
        if (!$row) {
            throw new RuntimeException('供应商对账单不存在', 404);
        }
        return $row;
    }

    private static function transition($id, array $allowedStatuses, $targetStatus, array $extra)
    {
        Db::startTrans();
        try {
            $row = Db::name('shop_supplier_reconciliation')->where('id', (int)$id)->lock(true)->find();
            if (!$row) {
                throw new RuntimeException('供应商对账单不存在', 404);
            }
            if ($row['status'] === $targetStatus) {
                Db::commit();
                return $row;
            }
            if (!in_array($row['status'], $allowedStatuses, true)) {
                throw new RuntimeException('当前对账状态不允许执行此操作', 409);
            }
            $data = array_merge($extra, ['status' => $targetStatus, 'updatetime' => time()]);
            Db::name('shop_supplier_reconciliation')->where('id', (int)$id)->update($data);
            Db::commit();
            return self::detail((int)$id);
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    private static function period($start, $end)
    {
        $start = trim((string)$start);
        $end = trim((string)$end);
        $startTime = strtotime($start . ' 00:00:00');
        $endTime = strtotime($end . ' 23:59:59');
        if (!$startTime || !$endTime || $startTime > $endTime) {
            throw new RuntimeException('对账账期不正确');
        }
        return [date('Y-m-d', $startTime), date('Y-m-d', $endTime), $startTime, $endTime];
    }

    private static function number($supplierId, $start, $end)
    {
        return 'SR' . strtoupper(substr(hash('sha256', $supplierId . '|' . $start . '|' . $end), 0, 30));
    }
}
