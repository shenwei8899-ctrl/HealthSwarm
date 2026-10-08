<?php

namespace addons\shop\library\service;

use addons\shop\model\Carts;
use RuntimeException;
use think\Db;

class CartService
{
    public static function addItem($userId, $goodsId, $goodsSkuId, $quantity = 1, $scene = 1)
    {
        $userId = (int)$userId;
        $goodsId = (int)$goodsId;
        $goodsSkuId = (int)$goodsSkuId;
        $quantity = self::positiveQuantity($quantity);
        $scene = (int)$scene ?: 1;
        self::validateGoods($goodsId, $goodsSkuId);

        Db::startTrans();
        try {
            $row = Db::name('shop_carts')
                ->alias('cart')
                ->join('__SHOP_CART_EXT__ ext', 'ext.cart_id = cart.id', 'LEFT')
                ->where('cart.user_id', $userId)
                ->where('cart.goods_id', $goodsId)
                ->where('cart.goods_sku_id', $goodsSkuId)
                ->where('cart.sceneval', $scene)
                ->whereNull('ext.id')
                ->field('cart.*')
                ->lock(true)
                ->find();
            $targetQuantity = $scene === 2 || !$row ? $quantity : (int)$row['nums'] + $quantity;
            self::assertAvailable($goodsId, $goodsSkuId, $targetQuantity);

            $now = time();
            if ($row) {
                Db::name('shop_carts')->where('id', (int)$row['id'])->update([
                    'nums' => $targetQuantity,
                    'updatetime' => $now,
                ]);
                $cartId = (int)$row['id'];
            } else {
                $cartId = Db::name('shop_carts')->insertGetId([
                    'user_id' => $userId,
                    'goods_id' => $goodsId,
                    'goods_sku_id' => $goodsSkuId,
                    'sceneval' => $scene,
                    'nums' => $targetQuantity,
                    'createtime' => $now,
                    'updatetime' => $now,
                ]);
            }
            Db::commit();
            return $cartId;
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    public static function addConfirmedShoppingList($userId, $shoppingListId, $shoppingListVersion)
    {
        $userId = (int)$userId;
        $shoppingListId = (int)$shoppingListId;
        $shoppingListVersion = (int)$shoppingListVersion;
        Db::startTrans();
        try {
            $list = Db::name('shop_shopping_list')
                ->where('id', $shoppingListId)
                ->where('user_id', $userId)
                ->lock(true)
                ->find();
            if (!$list || $list['status'] !== 'CONFIRMED') {
                throw new RuntimeException('购物清单不存在或尚未确认', 409);
            }
            if ((int)$list['list_version'] !== $shoppingListVersion) {
                throw new RuntimeException('购物清单版本已变化，请重新确认', 409);
            }

            $items = Db::name('shop_shopping_list_item')
                ->where('shopping_list_id', $shoppingListId)
                ->where('purchase_mode', 'PLATFORM')
                ->where('purchase_quantity', '>', 0)
                ->order('id ASC')
                ->lock(true)
                ->select();
            if (!$items) {
                throw new RuntimeException('购物清单没有可加入购物车的商品', 409);
            }

            $now = time();
            $cartIds = [];
            foreach ($items as $item) {
                $goodsId = (int)$item['selected_goods_id'];
                $goodsSkuId = (int)$item['selected_goods_sku_id'];
                $quantity = self::positiveQuantity($item['purchase_quantity']);
                self::validateGoods($goodsId, $goodsSkuId);
                $sources = self::assertAvailable($goodsId, $goodsSkuId, $quantity);
                $preferredSupplierId = (int)$item['selected_supplier_id'];
                $selectedSupplierId = self::selectSupplier($sources, $preferredSupplierId);

                $extension = Db::name('shop_cart_ext')
                    ->where('user_id', $userId)
                    ->where('shopping_list_item_id', (int)$item['id'])
                    ->lock(true)
                    ->find();
                $cart = $extension
                    ? Db::name('shop_carts')->where('id', (int)$extension['cart_id'])->where('user_id', $userId)->lock(true)->find()
                    : null;
                if ($extension && !$cart) {
                    Db::name('shop_cart_ext')->where('id', (int)$extension['id'])->delete();
                    $extension = null;
                }

                if ($cart) {
                    if ((int)$cart['goods_id'] !== $goodsId || (int)$cart['goods_sku_id'] !== $goodsSkuId) {
                        throw new RuntimeException('购物清单商品已变化，请清理购物车后重试', 409);
                    }
                    Db::name('shop_carts')->where('id', (int)$cart['id'])->update([
                        'nums' => $quantity,
                        'updatetime' => $now,
                    ]);
                    $cartId = (int)$cart['id'];
                } else {
                    $cartId = Db::name('shop_carts')->insertGetId([
                        'user_id' => $userId,
                        'goods_id' => $goodsId,
                        'goods_sku_id' => $goodsSkuId,
                        'sceneval' => 1,
                        'nums' => $quantity,
                        'createtime' => $now,
                        'updatetime' => $now,
                    ]);
                }

                $extensionData = [
                    'cart_id' => $cartId,
                    'user_id' => $userId,
                    'shopping_list_id' => $shoppingListId,
                    'shopping_list_item_id' => (int)$item['id'],
                    'ingredient_id' => (int)$item['ingredient_id'],
                    'preferred_supplier_id' => $preferredSupplierId,
                    'selected_supplier_id' => $selectedSupplierId,
                    'shopping_list_version' => $shoppingListVersion,
                    'source_hash' => $list['source_hash'],
                    'updatetime' => $now,
                ];
                if ($extension) {
                    Db::name('shop_cart_ext')->where('id', (int)$extension['id'])->update($extensionData);
                } else {
                    $extensionData['createtime'] = $now;
                    Db::name('shop_cart_ext')->insert($extensionData);
                }
                $cartIds[] = $cartId;
            }
            Db::commit();
            return self::listing($userId, $cartIds, 1);
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    public static function updateQuantity($userId, $cartId, $quantity)
    {
        $quantity = self::positiveQuantity($quantity);
        $cart = Db::name('shop_carts')->where('id', (int)$cartId)->where('user_id', (int)$userId)->find();
        if (!$cart) {
            throw new RuntimeException('购物车商品不存在', 404);
        }
        self::validateGoods((int)$cart['goods_id'], (int)$cart['goods_sku_id']);
        self::assertAvailable((int)$cart['goods_id'], (int)$cart['goods_sku_id'], $quantity);
        Db::name('shop_carts')->where('id', (int)$cart['id'])->update(['nums' => $quantity, 'updatetime' => time()]);
        return self::detail((int)$userId, (int)$cart['id']);
    }

    public static function remove($userId, $cartIds)
    {
        $ids = self::normalizeIds($cartIds);
        if (!$ids) {
            throw new RuntimeException('购物车商品不能为空');
        }
        $ownedIds = Db::name('shop_carts')->where('user_id', (int)$userId)->where('id', 'in', $ids)->column('id');
        if (!$ownedIds) {
            throw new RuntimeException('购物车商品不存在', 404);
        }
        Db::startTrans();
        try {
            Db::name('shop_cart_ext')->where('cart_id', 'in', $ownedIds)->delete();
            Db::name('shop_carts')->where('id', 'in', $ownedIds)->delete();
            Db::commit();
            return count($ownedIds);
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    public static function listing($userId, $cartIds = [], $scene = 1)
    {
        $ids = self::normalizeIds($cartIds);
        $rows = Carts::getGoodsList($ids, (int)$userId, (int)$scene);
        $rowIds = [];
        foreach ($rows as $row) {
            $rowIds[] = (int)$row->id;
        }
        $provenance = self::provenanceMap((int)$userId, $rowIds, false);
        $result = [];
        foreach ($rows as $row) {
            if (empty($row->goods)) {
                continue;
            }
            $item = $row->getData();
            $item['goods'] = $row->goods ? $row->goods->getData() : null;
            $item['sku'] = $row->sku ? $row->sku->getData() : null;
            $price = !empty($row->sku) ? $row->sku->price : $row->goods->price;
            $item['subtotal'] = bcmul((string)$row->nums, (string)$price, 2);
            $item['source'] = isset($provenance[(int)$row->id]) ? $provenance[(int)$row->id] : null;
            $item['available_sources'] = self::publicSources(InventoryService::listAvailableSources(
                (int)$row->goods_id,
                (int)$row->goods_sku_id,
                (int)$row->nums
            ));
            $result[] = $item;
        }
        return $result;
    }

    public static function detail($userId, $cartId)
    {
        $items = self::listing($userId, [(int)$cartId], 0);
        if (!$items) {
            throw new RuntimeException('购物车商品不存在', 404);
        }
        return $items[0];
    }

    public static function provenanceMap($userId, $cartIds, $strict = true)
    {
        $ids = self::normalizeIds($cartIds);
        if (!$ids) {
            return [];
        }
        $rows = Db::name('shop_cart_ext')
            ->alias('ext')
            ->join('__SHOP_CARTS__ cart', 'cart.id = ext.cart_id')
            ->join('__SHOP_SHOPPING_LIST__ list', 'list.id = ext.shopping_list_id')
            ->join('__SHOP_SHOPPING_LIST_ITEM__ item', 'item.id = ext.shopping_list_item_id')
            ->where('ext.cart_id', 'in', $ids)
            ->where('cart.user_id', (int)$userId)
            ->field('ext.*,cart.goods_id,cart.goods_sku_id,cart.nums,list.status AS list_status,list.list_version AS current_list_version,list.source_hash AS current_source_hash,item.shopping_list_id AS current_item_list_id,item.ingredient_id AS current_ingredient_id,item.selected_goods_id,item.selected_goods_sku_id,item.selected_supplier_id AS current_preferred_supplier_id')
            ->select();
        $result = [];
        foreach ($rows as $row) {
            $valid = $row['list_status'] === 'CONFIRMED'
                && (int)$row['shopping_list_version'] === (int)$row['current_list_version']
                && hash_equals((string)$row['source_hash'], (string)$row['current_source_hash'])
                && (int)$row['shopping_list_id'] === (int)$row['current_item_list_id']
                && (int)$row['ingredient_id'] === (int)$row['current_ingredient_id']
                && (int)$row['goods_id'] === (int)$row['selected_goods_id']
                && (int)$row['goods_sku_id'] === (int)$row['selected_goods_sku_id']
                && (int)$row['preferred_supplier_id'] === (int)$row['current_preferred_supplier_id'];
            if (!$valid && $strict) {
                throw new RuntimeException('购物清单来源已变化，请重新加入购物车', 409);
            }
            if (!$valid) {
                continue;
            }
            $result[(int)$row['cart_id']] = [
                'shopping_list_id' => (int)$row['shopping_list_id'],
                'shopping_list_item_id' => (int)$row['shopping_list_item_id'],
                'ingredient_id' => (int)$row['ingredient_id'],
                'preferred_supplier_id' => (int)$row['preferred_supplier_id'],
                'selected_supplier_id' => (int)$row['selected_supplier_id'],
                'shopping_list_version' => (int)$row['shopping_list_version'],
                'source_hash' => $row['source_hash'],
            ];
        }
        return $result;
    }

    public static function clearExtensions($cartIds)
    {
        $ids = self::normalizeIds($cartIds);
        return $ids ? Db::name('shop_cart_ext')->where('cart_id', 'in', $ids)->delete() : 0;
    }

    private static function validateGoods($goodsId, $goodsSkuId)
    {
        $goods = Db::name('shop_goods')->where('id', (int)$goodsId)->where('status', 'normal')->find();
        if (!$goods) {
            throw new RuntimeException('商品已下架', 409);
        }
        if ((int)$goods['spectype'] === 1 && !$goodsSkuId) {
            throw new RuntimeException('请选择商品规格', 422);
        }
        if ($goodsSkuId) {
            $sku = Db::name('shop_goods_sku')->where('id', (int)$goodsSkuId)->where('goods_id', (int)$goodsId)->find();
            if (!$sku) {
                throw new RuntimeException('商品规格不存在', 409);
            }
        }
    }

    private static function assertAvailable($goodsId, $goodsSkuId, $quantity)
    {
        $sources = InventoryService::listAvailableSources((int)$goodsId, (int)$goodsSkuId, self::positiveQuantity($quantity));
        if (!$sources) {
            throw new RuntimeException('仓库可售库存不足', 409);
        }
        return $sources;
    }

    private static function selectSupplier(array $sources, $preferredSupplierId)
    {
        foreach ($sources as $source) {
            if ((int)$source['supplier_id'] === (int)$preferredSupplierId) {
                return (int)$source['supplier_id'];
            }
        }
        return (int)$sources[0]['supplier_id'];
    }

    private static function publicSources(array $sources)
    {
        $result = [];
        foreach ($sources as $source) {
            $result[] = [
                'supplier_id' => (int)$source['supplier_id'],
                'supplier_name' => $source['supplier_name'] ?: '平台自营',
                'warehouse_id' => (int)$source['warehouse_id'],
                'warehouse_name' => $source['warehouse_name'],
                'available_quantity' => (int)$source['available_qty'],
                'delivery_days' => $source['delivery_days'] === null ? 0 : (int)$source['delivery_days'],
                'fulfillment_mode' => $source['fulfillment_mode'] ?: 'PLATFORM_WAREHOUSE',
            ];
        }
        return $result;
    }

    private static function normalizeIds($ids)
    {
        if (is_string($ids)) {
            $ids = preg_split('/\s*,\s*/', trim($ids), -1, PREG_SPLIT_NO_EMPTY);
        }
        if (!is_array($ids)) {
            $ids = $ids ? [$ids] : [];
        }
        return array_values(array_unique(array_filter(array_map('intval', $ids), function ($id) {
            return $id > 0;
        })));
    }

    private static function positiveQuantity($quantity)
    {
        $quantity = filter_var($quantity, FILTER_VALIDATE_INT);
        if ($quantity === false || $quantity <= 0) {
            throw new RuntimeException('商品数量必须是正整数', 422);
        }
        return (int)$quantity;
    }
}
