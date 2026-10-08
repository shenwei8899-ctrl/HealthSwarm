<?php

namespace addons\shop\library\service;

use RuntimeException;
use think\Db;

class ShoppingListService
{
    public static function listForUser($userId, $page = 1, $pageSize = 20)
    {
        $page = max(1, (int)$page);
        $pageSize = max(1, min(100, (int)$pageSize));
        $total = Db::name('shop_shopping_list')->where('user_id', (int)$userId)->count();
        $rows = Db::name('shop_shopping_list')
            ->where('user_id', (int)$userId)
            ->order('id DESC')
            ->page($page, $pageSize)
            ->select();
        foreach ($rows as &$row) {
            foreach (['id', 'user_id', 'list_version', 'confirmed_at', 'createtime', 'updatetime'] as $field) {
                $row[$field] = (int)($row[$field] ?? 0);
            }
            $row['item_count'] = (int)Db::name('shop_shopping_list_item')
                ->where('shopping_list_id', (int)$row['id'])
                ->count();
            $row['platform_item_count'] = (int)Db::name('shop_shopping_list_item')
                ->where('shopping_list_id', (int)$row['id'])
                ->where('purchase_mode', 'PLATFORM')
                ->where('net_quantity', '>', 0)
                ->count();
            $row['unmatched_item_count'] = (int)Db::name('shop_shopping_list_item')
                ->where('shopping_list_id', (int)$row['id'])
                ->where('purchase_mode', 'PLATFORM')
                ->where('net_quantity', '>', 0)
                ->where('selected_goods_id', 0)
                ->count();
        }
        unset($row);
        return [
            'items' => $rows,
            'pagination' => ['page' => $page, 'page_size' => $pageSize, 'total' => (int)$total],
        ];
    }

    public static function create($userId, $menuVersionId, $listVersion, array $items)
    {
        $userId = (int)$userId;
        $listVersion = (int)$listVersion;
        $menuVersionId = trim((string)$menuVersionId);
        if ($userId <= 0 || $menuVersionId === '' || $listVersion <= 0 || !$items) {
            throw new RuntimeException('购物清单参数不完整');
        }

        $sourceHash = hash('sha256', self::canonicalJson($items));
        Db::startTrans();
        try {
            $existing = Db::name('shop_shopping_list')
                ->where('user_id', $userId)
                ->where('menu_version_id', $menuVersionId)
                ->where('list_version', $listVersion)
                ->lock(true)
                ->find();
            if ($existing) {
                if ($existing['source_hash'] !== $sourceHash) {
                    throw new RuntimeException('相同菜单版本的购物清单内容不一致，请提升清单版本', 409);
                }
                $result = self::detail((int)$existing['id'], $userId);
                Db::commit();
                return $result;
            }

            $now = time();
            $listSn = self::listNumber($userId, $menuVersionId, $listVersion);
            $listId = Db::name('shop_shopping_list')->insertGetId([
                'list_sn' => $listSn,
                'user_id' => $userId,
                'menu_version_id' => $menuVersionId,
                'list_version' => $listVersion,
                'source_hash' => $sourceHash,
                'status' => 'DRAFT',
                'createtime' => $now,
                'updatetime' => $now,
            ]);

            foreach ($items as $item) {
                self::insertItem($listId, $item, $now);
            }
            $result = self::detail($listId, $userId);
            Db::commit();
            return $result;
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    public static function detail($listId, $userId)
    {
        $list = Db::name('shop_shopping_list')
            ->where('id', (int)$listId)
            ->where('user_id', (int)$userId)
            ->find();
        if (!$list) {
            throw new RuntimeException('购物清单不存在', 404);
        }
        $items = Db::name('shop_shopping_list_item')
            ->alias('i')
            ->join('__SHOP_INGREDIENT__ ingredient', 'ingredient.id = i.ingredient_id')
            ->join('__SHOP_GOODS__ goods', 'goods.id = i.selected_goods_id', 'LEFT')
            ->join('__SHOP_SUPPLIER__ supplier', 'supplier.id = i.selected_supplier_id', 'LEFT')
            ->where('i.shopping_list_id', (int)$listId)
            ->field('i.*,ingredient.code AS ingredient_code,ingredient.name AS ingredient_name,goods.title AS selected_goods_title,goods.image AS selected_goods_image,supplier.name AS selected_supplier_name')
            ->order('i.id ASC')
            ->select();
        foreach ($items as &$item) {
            $item['source_refs'] = self::decodeJson($item['source_refs_json']);
            $item['constraint_result'] = self::decodeJson($item['constraint_result_json']);
            unset($item['source_refs_json'], $item['constraint_result_json']);
        }
        unset($item);
        $list['items'] = $items;
        return $list;
    }

    public static function updateItem($listId, $itemId, $userId, array $changes)
    {
        Db::startTrans();
        try {
            $list = self::lockEditableList($listId, $userId);
            $item = Db::name('shop_shopping_list_item')
                ->where('id', (int)$itemId)
                ->where('shopping_list_id', (int)$list['id'])
                ->lock(true)
                ->find();
            if (!$item) {
                throw new RuntimeException('购物清单明细不存在', 404);
            }

            $requiredQuantity = (string)$item['required_quantity'];
            $homeQuantity = (string)$item['home_quantity'];
            if (array_key_exists('home_quantity', $changes)) {
                $inputUnit = isset($changes['unit']) ? $changes['unit'] : $item['unit'];
                $homeQuantity = UnitConverter::convert($changes['home_quantity'], $inputUnit, $item['unit'], 3);
            }
            if ((float)$homeQuantity < 0) {
                throw new RuntimeException('家中已有数量不能为负数');
            }
            $netQuantity = bccomp($requiredQuantity, $homeQuantity, 3) > 0
                ? bcsub($requiredQuantity, $homeQuantity, 3)
                : '0.000';
            $purchaseMode = isset($changes['purchase_mode']) ? (string)$changes['purchase_mode'] : $item['purchase_mode'];
            if (!in_array($purchaseMode, ['PLATFORM', 'SELF_PURCHASE', 'SKIP'], true)) {
                throw new RuntimeException('不支持的购买方式');
            }

            $selection = self::emptySelection();
            if ($purchaseMode === 'PLATFORM' && bccomp($netQuantity, '0', 3) > 0) {
                $match = ProductMatchService::match(
                    (int)$item['ingredient_id'],
                    $netQuantity,
                    $item['unit'],
                    self::decodeJson($item['constraint_result_json'])
                );
                $selection = self::selectionFromMatch($match);
            }

            Db::name('shop_shopping_list_item')->where('id', (int)$item['id'])->update(array_merge([
                'home_quantity' => $homeQuantity,
                'net_quantity' => $netQuantity,
                'purchase_mode' => $purchaseMode,
                'updatetime' => time(),
            ], $selection));
            Db::name('shop_shopping_list')->where('id', (int)$list['id'])->update(['updatetime' => time()]);

            $result = self::detail((int)$list['id'], (int)$userId);
            Db::commit();
            return $result;
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    public static function confirm($listId, $userId)
    {
        Db::startTrans();
        try {
            $list = self::lockEditableList($listId, $userId);
            $invalidCount = Db::name('shop_shopping_list_item')
                ->where('shopping_list_id', (int)$list['id'])
                ->where('purchase_mode', 'PLATFORM')
                ->where('net_quantity', '>', 0)
                ->where('selected_goods_id', 0)
                ->count();
            if ($invalidCount > 0) {
                throw new RuntimeException('购物清单存在无法匹配的食材，请选择自购或重新匹配', 409);
            }

            $now = time();
            Db::name('shop_shopping_list')->where('id', (int)$list['id'])->update([
                'status' => 'CONFIRMED',
                'confirmed_at' => $now,
                'updatetime' => $now,
            ]);
            $result = self::detail((int)$list['id'], (int)$userId);
            Db::commit();
            return $result;
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    private static function insertItem($listId, array $item, $now)
    {
        $ingredientId = isset($item['ingredient_id']) ? (int)$item['ingredient_id'] : 0;
        $ingredient = Db::name('shop_ingredient')->where('id', $ingredientId)->where('status', 'normal')->find();
        if (!$ingredient) {
            throw new RuntimeException('购物清单包含无效的标准食材', 404);
        }
        $inputUnit = isset($item['unit']) ? $item['unit'] : $ingredient['default_unit'];
        $required = UnitConverter::convert(isset($item['required_quantity']) ? $item['required_quantity'] : 0, $inputUnit, $ingredient['default_unit'], 3);
        $home = UnitConverter::convert(isset($item['home_quantity']) ? $item['home_quantity'] : 0, $inputUnit, $ingredient['default_unit'], 3);
        if (bccomp($required, '0', 3) <= 0) {
            throw new RuntimeException('食材需求数量必须大于0');
        }
        $net = bccomp($required, $home, 3) > 0 ? bcsub($required, $home, 3) : '0.000';
        $purchaseMode = isset($item['purchase_mode']) ? (string)$item['purchase_mode'] : 'PLATFORM';
        if (!in_array($purchaseMode, ['PLATFORM', 'SELF_PURCHASE', 'SKIP'], true)) {
            throw new RuntimeException('不支持的购买方式');
        }
        $constraints = isset($item['constraint_result']) && is_array($item['constraint_result']) ? $item['constraint_result'] : [];
        $selection = self::emptySelection();
        if ($purchaseMode === 'PLATFORM' && bccomp($net, '0', 3) > 0) {
            $selection = self::selectionFromMatch(ProductMatchService::match(
                $ingredientId,
                $net,
                $ingredient['default_unit'],
                $constraints
            ));
        }

        Db::name('shop_shopping_list_item')->insert(array_merge([
            'shopping_list_id' => (int)$listId,
            'ingredient_id' => $ingredientId,
            'required_quantity' => $required,
            'home_quantity' => $home,
            'net_quantity' => $net,
            'unit' => $ingredient['default_unit'],
            'source_refs_json' => json_encode(isset($item['source_refs']) ? $item['source_refs'] : [], JSON_UNESCAPED_UNICODE),
            'constraint_result_json' => json_encode($constraints, JSON_UNESCAPED_UNICODE),
            'purchase_mode' => $purchaseMode,
            'substitution_confirmed' => 0,
            'createtime' => $now,
            'updatetime' => $now,
        ], $selection));
    }

    private static function selectionFromMatch(array $match)
    {
        if (empty($match['selected'])) {
            return self::emptySelection();
        }
        $selected = $match['selected'];
        return [
            'selected_goods_id' => (int)$selected['goods_id'],
            'selected_goods_sku_id' => (int)$selected['goods_sku_id'],
            'selected_supplier_id' => (int)$selected['supplier_id'],
            'purchase_quantity' => (int)$selected['purchase_quantity'],
            'covered_quantity' => $selected['covered_quantity'],
            'shortage_quantity' => $selected['shortage_quantity'],
            'excess_quantity' => $selected['excess_quantity'],
        ];
    }

    private static function emptySelection()
    {
        return [
            'selected_goods_id' => 0,
            'selected_goods_sku_id' => 0,
            'selected_supplier_id' => 0,
            'purchase_quantity' => 0,
            'covered_quantity' => '0.000',
            'shortage_quantity' => '0.000',
            'excess_quantity' => '0.000',
        ];
    }

    private static function lockEditableList($listId, $userId)
    {
        $list = Db::name('shop_shopping_list')
            ->where('id', (int)$listId)
            ->where('user_id', (int)$userId)
            ->lock(true)
            ->find();
        if (!$list) {
            throw new RuntimeException('购物清单不存在', 404);
        }
        if ($list['status'] !== 'DRAFT') {
            throw new RuntimeException('购物清单当前状态不允许修改', 409);
        }
        return $list;
    }

    private static function listNumber($userId, $menuVersionId, $listVersion)
    {
        return 'SL' . strtoupper(substr(hash('sha256', $userId . '|' . $menuVersionId . '|' . $listVersion), 0, 30));
    }

    private static function canonicalJson(array $data)
    {
        return json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRESERVE_ZERO_FRACTION);
    }

    private static function decodeJson($value)
    {
        if (!$value) {
            return [];
        }
        if (is_array($value)) {
            return $value;
        }
        $decoded = json_decode($value, true);
        return is_array($decoded) ? $decoded : [];
    }
}
