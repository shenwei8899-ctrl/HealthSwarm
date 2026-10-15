<?php

namespace addons\shop\library\v5;

use think\Db;

class CartService
{
    public function listItems($userId)
    {
        $rows = Db::name('shop_carts')->alias('c')
            ->join('shop_goods_sku s', 's.id=c.goods_sku_id')
            ->join('shop_goods g', 'g.id=c.goods_id')
            ->where('c.user_id', (int)$userId)->where('c.sceneval', 1)
            ->field('c.*,g.title,g.image,g.status as goods_status,g.catalog_status,g.agent_visible,s.image as sku_image,s.sku_code,s.sku_id as sku_name,s.price,s.stocks,s.reserved_stock,s.safety_stock,s.net_content_value,s.net_content_unit')
            ->order('c.id', 'desc')->select();
        $items = [];
        $total = 0;
        foreach ($rows as $row) {
            $available = max(0, (int)$row['stocks'] - (int)$row['reserved_stock'] - (int)$row['safety_stock']);
            $valid = $row['goods_status'] === 'normal' && $row['catalog_status'] === 'published' && (int)$row['agent_visible'] === 1 && $available >= (int)$row['nums'];
            $line = (int)round((float)$row['price'] * 100) * (int)$row['nums'];
            if ($valid && (int)$row['is_selected'] === 1) {
                $total += $line;
            }
            $items[] = [
                'cart_item_id' => (string)$row['id'], 'product_id' => (string)$row['goods_id'],
                'sku_id' => (string)$row['goods_sku_id'], 'product_name' => $row['title'],
                'sku_name' => $row['sku_name'], 'sku_code' => $row['sku_code'], 'image_url' => MediaUrl::absolute($row['sku_image'] ?: $row['image']),
                'selected' => (bool)$row['is_selected'], 'net_content' => ['value' => (float)$row['net_content_value'], 'unit' => $row['net_content_unit']],
                'quantity' => (int)$row['nums'], 'unit_price_cent' => (int)round((float)$row['price'] * 100),
                'line_amount_cent' => $line, 'available_quantity' => $available, 'valid' => $valid,
                'invalid_reason' => $valid ? null : ($row['goods_status'] !== 'normal' ? 'off_shelf' : 'out_of_stock'),
                'source_type' => $row['source_type'], 'source_ref' => $row['source_ref'],
                'source_version' => (int)$row['source_version'], 'purchase_item_id' => (string)$row['purchase_item_id'],
                'version' => (int)$row['row_version'],
            ];
        }
        return ['items' => $items, 'valid_total_amount_cent' => $total, 'invalid_count' => count(array_filter($items, function ($item) { return !$item['valid']; }))];
    }

    public function add($userId, $skuId, $quantity, array $source = [])
    {
        Db::startTrans();
        try {
            Db::name('user')->where('id', (int)$userId)->lock(true)->find();
            $result = $this->addItem($userId, $skuId, $quantity, $source);
            Db::commit();
            return $result;
        } catch (\Exception $e) { Db::rollback(); throw $e; }
    }

    private function addItem($userId, $skuId, $quantity, array $source)
    {
        (new CatalogService())->getSku($skuId, false);
        if (filter_var($quantity, FILTER_VALIDATE_INT) === false || (int)$quantity <= 0 || (int)$quantity > 32767) {
            throw new DomainException('购买数量必须大于0', 40005, 400);
        }
        $quantity = (int)$quantity;
        $sku = Db::name('shop_goods_sku')->alias('s')->join('shop_goods g', 'g.id=s.goods_id')
            ->where('s.id', (int)$skuId)->field('s.*,g.status as goods_status')->find();
        if (!$sku || $sku['goods_status'] !== 'normal') {
            throw new DomainException('商品不存在或已下架', 40904, 409);
        }
        $available = (int)$sku['stocks'] - (int)$sku['reserved_stock'] - (int)$sku['safety_stock'];
        if ($available < $quantity) {
            throw new DomainException('库存不足', 40904, 409, ['available_quantity' => max(0, $available)]);
        }
        $where = ['user_id'=>(int)$userId,'goods_sku_id'=>(int)$skuId,'sceneval'=>1,
            'source_type'=>isset($source['source_type'])?$source['source_type']:'',
            'source_ref'=>isset($source['source_ref'])?$source['source_ref']:''];
        $row = Db::name('shop_carts')->where($where)->find();
        $now = time();
        if ($row) {
            $newQuantity = (int)$row['nums'] + $quantity;
            if ($newQuantity > $available) {
                throw new DomainException('库存不足', 40904, 409, ['available_quantity' => max(0, $available)]);
            }
            $changed = Db::name('shop_carts')->where('id', $row['id'])->where('row_version', $row['row_version'])->update(['nums'=>$newQuantity,'is_selected'=>1,'row_version'=>(int)$row['row_version']+1,'updatetime'=>$now]);
            if (!$changed) throw new DomainException('购物车已更新，请重试', 40906, 409);
            $id = $row['id'];
        } else {
            $id = Db::name('shop_carts')->insertGetId($where + [
                'goods_id'=>(int)$sku['goods_id'],'nums'=>$quantity,
                'source_version'=>(int)(isset($source['source_version'])?$source['source_version']:0),
                'purchase_item_id'=>(int)(isset($source['purchase_item_id'])?$source['purchase_item_id']:0),
                'row_version'=>1,'createtime'=>$now,'updatetime'=>$now,
            ]);
        }
        return ['cart_item_id'=>(string)$id] + $this->listItems($userId);
    }

    public function update($userId, $itemId, $quantity, $baseVersion)
    {
        if (filter_var($quantity, FILTER_VALIDATE_INT) === false || (int)$quantity < 0 || (int)$quantity > 32767) throw new DomainException('购买数量无效', 40005, 400);
        $row = Db::name('shop_carts')->where('id', (int)$itemId)->where('user_id', (int)$userId)->find();
        if (!$row) throw new DomainException('购物车项不存在', 40412, 404);
        if ((int)$row['row_version'] !== (int)$baseVersion) throw new DomainException('购物车版本冲突', 40906, 409, ['current_version'=>(int)$row['row_version']]);
        if ((int)$quantity <= 0) return $this->remove($userId, $itemId, $baseVersion);
        $sku = (new CatalogService())->getSku($row['goods_sku_id'], false);
        if ((int)$quantity > (int)$sku['available_quantity']) throw new DomainException('库存不足', 40904, 409);
        $changed = Db::name('shop_carts')->where('id', $row['id'])->where('row_version', $baseVersion)->update(['nums'=>(int)$quantity,'row_version'=>(int)$baseVersion+1,'updatetime'=>time()]);
        if (!$changed) throw new DomainException('购物车已更新，请重试', 40906, 409);
        return $this->listItems($userId);
    }

    public function select($userId, $itemId, $selected, $version)
    {
        if (!is_bool($selected)) throw new DomainException('勾选状态无效', 40001, 400);
        $changed = Db::name('shop_carts')->where('id', (int)$itemId)->where('user_id', (int)$userId)->where('row_version', (int)$version)
            ->update(['is_selected' => (int)$selected, 'row_version' => (int)$version + 1, 'updatetime' => time()]);
        if (!$changed) throw new DomainException('购物车不存在或版本已变化', 40906, 409);
        return $this->listItems($userId);
    }

    public function checkoutItems($userId, array $references, $lock = false)
    {
        if (!$references) throw new DomainException('请选择购物车商品', 40012, 400);
        $items = []; $seen = [];
        foreach ($references as $ref) {
            if (empty($ref['cart_item_id']) || !isset($ref['version']) || isset($seen[$ref['cart_item_id']])) throw new DomainException('购物车引用无效', 40001, 400);
            $seen[$ref['cart_item_id']] = true;
            $q = Db::name('shop_carts')->where('id', (int)$ref['cart_item_id'])->where('user_id', (int)$userId)->where('sceneval', 1);
            if ($lock) $q->lock(true);
            $row = $q->find();
            if (!$row || !(int)$row['is_selected'] || (int)$row['row_version'] !== (int)$ref['version']) throw new DomainException('购物车已变化，请重新结算', 40906, 409);
            $items[] = ['cart_item_id' => (string)$row['id'], 'version' => (int)$row['row_version'], 'sku_id' => (string)$row['goods_sku_id'], 'quantity' => (int)$row['nums'], 'source_type'=>$row['source_type'], 'source_ref'=>$row['source_ref'], 'source_version'=>(int)$row['source_version']];
        }
        return $items;
    }

    public function remove($userId, $itemId, $version = null)
    {
        $query = Db::name('shop_carts')->where('id', (int)$itemId)->where('user_id', (int)$userId);
        if ($version !== null) $query->where('row_version', (int)$version);
        $changed = $query->delete();
        if ($version !== null && !$changed) throw new DomainException('购物车版本已变化', 40906, 409);
        return $this->listItems($userId);
    }
}
