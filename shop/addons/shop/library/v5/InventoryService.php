<?php

namespace addons\shop\library\v5;

use think\Db;

class InventoryService
{
    public function adjust($skuId, $delta, $reason, $operatorId, $requestId)
    {
        $delta = (int)$delta;
        $reason = trim((string)$reason);
        if ($delta === 0 || $reason === '') {
            throw new DomainException('库存调整量不能为0且必须填写原因', 40005, 400);
        }
        Db::startTrans();
        try {
            $sku = Db::name('shop_goods_sku')->where('id', (int)$skuId)->lock(true)->find();
            if (!$sku) {
                throw new DomainException('SKU不存在', 40401, 404);
            }
            $stockAfter = (int)$sku['stocks'] + $delta;
            if ($stockAfter < (int)$sku['reserved_stock']) {
                throw new DomainException('调整后库存不能小于已占用库存', 40911, 409, [
                    'stock_after' => $stockAfter, 'reserved_stock' => (int)$sku['reserved_stock'],
                ]);
            }
            $now = time();
            Db::name('shop_goods_sku')->where('id', $sku['id'])->update([
                'stocks' => $stockAfter, 'stock_updated_at' => $now,
                'row_version' => (int)$sku['row_version'] + 1, 'updatetime' => $now,
            ]);
            Db::name('shop_inventory_log')->insert([
                'sku_id' => $sku['id'], 'change_type' => 'manual_adjust', 'quantity_delta' => $delta,
                'stock_before' => (int)$sku['stocks'], 'stock_after' => $stockAfter,
                'reserved_before' => (int)$sku['reserved_stock'], 'reserved_after' => (int)$sku['reserved_stock'],
                'source_type' => 'admin', 'source_ref' => (string)$operatorId,
                'operator_type' => 'admin', 'operator_id' => (int)$operatorId, 'reason' => $reason,
                'request_id' => $requestId, 'createtime' => $now,
            ]);
            Db::commit();
            return ['sku_id' => (string)$sku['id'], 'stock_before' => (int)$sku['stocks'], 'stock_after' => $stockAfter];
        } catch (\Exception $e) {
            Db::rollback();
            throw $e;
        }
    }

    public function reserve($skuId, $quantity, $sourceType, $sourceRef, $sourceItemRef, $requestId, $expiresAt)
    {
        $quantity = (int)$quantity;
        if ($quantity <= 0) {
            throw new DomainException('库存占用数量必须大于0', 40005, 400);
        }
        Db::startTrans();
        try {
            $existing = Db::name('shop_inventory_reservation')->where([
                'source_type' => $sourceType, 'source_ref' => $sourceRef,
                'source_item_ref' => (string)$sourceItemRef, 'sku_id' => (int)$skuId,
            ])->lock(true)->find();
            if ($existing) {
                Db::commit();
                return $existing;
            }
            $sku = Db::name('shop_goods_sku')->where('id', (int)$skuId)->lock(true)->find();
            if (!$sku) {
                throw new DomainException('SKU不存在', 40401, 404);
            }
            $available = (int)$sku['stocks'] - (int)$sku['reserved_stock'] - (int)$sku['safety_stock'];
            if ($available < $quantity) {
                throw new DomainException('库存不足', 40911, 409, ['sku_id' => (string)$skuId, 'available' => max(0, $available)]);
            }
            $reservationSn = Identifiers::make('reserve');
            $now = time();
            $id = Db::name('shop_inventory_reservation')->insertGetId([
                'reservation_sn' => $reservationSn, 'sku_id' => (int)$skuId,
                'source_type' => $sourceType, 'source_ref' => (string)$sourceRef,
                'source_item_ref' => (string)$sourceItemRef, 'quantity' => $quantity,
                'status' => 'active', 'expires_at' => (int)$expiresAt, 'request_id' => $requestId,
                'createtime' => $now, 'updatetime' => $now,
            ]);
            Db::name('shop_goods_sku')->where('id', (int)$skuId)->update([
                'reserved_stock' => (int)$sku['reserved_stock'] + $quantity,
                'stock_updated_at' => $now,
                'row_version' => (int)$sku['row_version'] + 1,
                'updatetime' => $now,
            ]);
            $this->log($sku, $quantity, (int)$sku['stocks'], (int)$sku['stocks'], (int)$sku['reserved_stock'], (int)$sku['reserved_stock'] + $quantity, 'reserve', $sourceType, $sourceRef, $requestId);
            Db::commit();
            return Db::name('shop_inventory_reservation')->where('id', $id)->find();
        } catch (\Exception $e) {
            Db::rollback();
            throw $e;
        }
    }

    public function confirm($reservationSn, $requestId)
    {
        return $this->finish($reservationSn, 'confirmed', 'confirm', $requestId);
    }

    public function release($reservationSn, $reason, $requestId)
    {
        return $this->finish($reservationSn, 'released', $reason, $requestId);
    }

    protected function finish($reservationSn, $targetStatus, $reason, $requestId)
    {
        Db::startTrans();
        try {
            $reservation = Db::name('shop_inventory_reservation')->where('reservation_sn', $reservationSn)->lock(true)->find();
            if (!$reservation) {
                throw new DomainException('库存占用记录不存在', 40406, 404);
            }
            if ($reservation['status'] === $targetStatus) {
                Db::commit();
                return $reservation;
            }
            if ($reservation['status'] !== 'active') {
                throw new DomainException('库存占用状态不可变更', 40912, 409);
            }
            $sku = Db::name('shop_goods_sku')->where('id', $reservation['sku_id'])->lock(true)->find();
            $reservedAfter = max(0, (int)$sku['reserved_stock'] - (int)$reservation['quantity']);
            $stockAfter = $targetStatus === 'confirmed' ? max(0, (int)$sku['stocks'] - (int)$reservation['quantity']) : (int)$sku['stocks'];
            Db::name('shop_goods_sku')->where('id', $sku['id'])->update([
                'stocks' => $stockAfter, 'reserved_stock' => $reservedAfter,
                'stock_updated_at' => time(), 'row_version' => (int)$sku['row_version'] + 1, 'updatetime' => time(),
            ]);
            $update = ['status' => $targetStatus, 'updatetime' => time()];
            if ($targetStatus === 'confirmed') {
                $update['confirmed_at'] = time();
            } else {
                $update['released_at'] = time();
                $update['release_reason'] = $reason;
            }
            Db::name('shop_inventory_reservation')->where('id', $reservation['id'])->update($update);
            $this->log($sku, $targetStatus === 'confirmed' ? -(int)$reservation['quantity'] : 0, (int)$sku['stocks'], $stockAfter, (int)$sku['reserved_stock'], $reservedAfter, $targetStatus, $reservation['source_type'], $reservation['source_ref'], $requestId);
            Db::commit();
            return Db::name('shop_inventory_reservation')->where('id', $reservation['id'])->find();
        } catch (\Exception $e) {
            Db::rollback();
            throw $e;
        }
    }

    protected function log(array $sku, $delta, $stockBefore, $stockAfter, $reservedBefore, $reservedAfter, $type, $sourceType, $sourceRef, $requestId)
    {
        Db::name('shop_inventory_log')->insert([
            'sku_id' => $sku['id'], 'change_type' => $type, 'quantity_delta' => $delta,
            'stock_before' => $stockBefore, 'stock_after' => $stockAfter,
            'reserved_before' => $reservedBefore, 'reserved_after' => $reservedAfter,
            'source_type' => $sourceType, 'source_ref' => (string)$sourceRef,
            'operator_type' => 'system', 'operator_id' => 0, 'reason' => $type,
            'request_id' => $requestId, 'createtime' => time(),
        ]);
    }
}
