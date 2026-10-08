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
            ->field('c.*,g.title,g.image,g.status as goods_status,s.sku_code,s.sku_id as sku_name,s.price,s.stocks,s.reserved_stock,s.safety_stock,s.net_content_value,s.net_content_unit')
            ->order('c.id', 'desc')->select();
        $items = [];
        $total = 0;
        foreach ($rows as $row) {
            $available = max(0, (int)$row['stocks'] - (int)$row['reserved_stock'] - (int)$row['safety_stock']);
            $valid = $row['goods_status'] === 'normal' && $available >= (int)$row['nums'];
            $line = (int)round((float)$row['price'] * 100) * (int)$row['nums'];
            if ($valid) {
                $total += $line;
            }
            $items[] = [
                'cart_item_id' => (string)$row['id'], 'product_id' => (string)$row['goods_id'],
                'sku_id' => (string)$row['goods_sku_id'], 'product_name' => $row['title'],
                'sku_name' => $row['sku_name'], 'sku_code' => $row['sku_code'], 'image_url' => $row['image'],
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
        $quantity = (int)$quantity;
        if ($quantity <= 0) {
            throw new DomainException('购买数量必须大于0', 40005, 400);
        }
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
            Db::name('shop_carts')->where('id', $row['id'])->update(['nums'=>$newQuantity,'row_version'=>(int)$row['row_version']+1,'updatetime'=>$now]);
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
        $row = Db::name('shop_carts')->where('id', (int)$itemId)->where('user_id', (int)$userId)->find();
        if (!$row) throw new DomainException('购物车项不存在', 40412, 404);
        if ((int)$row['row_version'] !== (int)$baseVersion) throw new DomainException('购物车版本冲突', 40906, 409, ['current_version'=>(int)$row['row_version']]);
        if ((int)$quantity <= 0) return $this->remove($userId, $itemId);
        $sku = (new CatalogService())->getSku($row['goods_sku_id'], false);
        Db::name('shop_carts')->where('id', $row['id'])->where('row_version', $baseVersion)->update(['nums'=>(int)$quantity,'row_version'=>(int)$baseVersion+1,'updatetime'=>time()]);
        return $this->listItems($userId);
    }

    public function remove($userId, $itemId)
    {
        Db::name('shop_carts')->where('id', (int)$itemId)->where('user_id', (int)$userId)->delete();
        return $this->listItems($userId);
    }
}
