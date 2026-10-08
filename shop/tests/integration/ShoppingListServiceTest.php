<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\service\ShoppingListService;
use think\Db;

function listAssertSame($expected, $actual, $message)
{
    if ($expected !== $actual) {
        throw new RuntimeException($message . ': expected ' . var_export($expected, true) . ', got ' . var_export($actual, true));
    }
}

$goods = Db::name('shop_goods')->where('status', 'normal')->where('spectype', 0)->order('id ASC')->find();
if (!$goods) {
    throw new RuntimeException('No single-spec goods are available for integration testing.');
}

$suffix = date('His') . bin2hex(random_bytes(2));
$userId = 900000 + random_int(1, 9999);
$menuVersion = 'TEST-MENU-' . $suffix;
$items = [];

Db::startTrans();
try {
    $ingredientId = Db::name('shop_ingredient')->insertGetId([
        'code' => 'TEST-LIST-' . $suffix,
        'name' => '清单测试食材',
        'category' => '测试',
        'default_unit' => 'g',
        'aliases_json' => '[]',
        'status' => 'normal',
        'createtime' => time(),
        'updatetime' => time(),
    ]);
    Db::name('shop_ingredient_product_map')->insert([
        'ingredient_id' => $ingredientId,
        'goods_id' => $goods['id'],
        'goods_sku_id' => 0,
        'content_quantity' => '300.000',
        'content_unit' => 'g',
        'conversion_rate' => '1.000000',
        'priority' => 10,
        'status' => 'normal',
        'createtime' => time(),
        'updatetime' => time(),
    ]);
    $items = [[
        'ingredient_id' => $ingredientId,
        'required_quantity' => '500',
        'home_quantity' => '100',
        'unit' => 'g',
        'source_refs' => ['recipe:test', 'member:anonymous'],
        'constraint_result' => ['allowed' => true],
    ]];

    $list = ShoppingListService::create($userId, $menuVersion, 1, $items);
    listAssertSame('400.000', (string)$list['items'][0]['net_quantity'], 'Home inventory must be deducted');
    listAssertSame(2, (int)$list['items'][0]['purchase_quantity'], 'Purchase quantity must cover net demand');

    $repeated = ShoppingListService::create($userId, $menuVersion, 1, $items);
    listAssertSame((int)$list['id'], (int)$repeated['id'], 'Repeated create must be idempotent');

    $listPage = ShoppingListService::listForUser($userId, 1, 10);
    listAssertSame(1, (int)$listPage['pagination']['total'], 'User list query must return the created list');
    listAssertSame((int)$list['id'], (int)$listPage['items'][0]['id'], 'User list query must return the owned list');
    listAssertSame(1, (int)$listPage['items'][0]['item_count'], 'User list query must aggregate item count');
    listAssertSame(0, (int)ShoppingListService::listForUser($userId + 1, 1, 10)['pagination']['total'], 'Another user must not see the list');

    $updated = ShoppingListService::updateItem($list['id'], $list['items'][0]['id'], $userId, [
        'home_quantity' => '250',
        'unit' => 'g',
    ]);
    listAssertSame('250.000', (string)$updated['items'][0]['net_quantity'], 'Updating home inventory must recalculate net demand');
    listAssertSame(1, (int)$updated['items'][0]['purchase_quantity'], 'Updating demand must recalculate package quantity');

    $confirmed = ShoppingListService::confirm($list['id'], $userId);
    listAssertSame('CONFIRMED', $confirmed['status'], 'Valid list must be confirmable');

    $conflictRaised = false;
    try {
        $changedItems = $items;
        $changedItems[0]['required_quantity'] = '600';
        ShoppingListService::create($userId, $menuVersion, 1, $changedItems);
    } catch (RuntimeException $e) {
        $conflictRaised = (int)$e->getCode() === 409;
    }
    listAssertSame(true, $conflictRaised, 'Changed content must require a new list version');

    Db::rollback();
} catch (Throwable $e) {
    Db::rollback();
    throw $e;
}

echo "ShoppingListService integration test passed.\n";
