<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\service\CartService;
use addons\shop\library\service\OrderService;
use think\Db;

function cartAssertSame($expected, $actual, $message)
{
    if ($expected !== $actual) {
        throw new RuntimeException($message . ': expected ' . var_export($expected, true) . ', got ' . var_export($actual, true));
    }
}

$goods = Db::name('shop_goods')->where('status', 'normal')->where('spectype', 0)->order('id ASC')->find();
if (!$goods) {
    throw new RuntimeException('No single-spec goods are available for cart provenance testing.');
}

$suffix = date('His') . bin2hex(random_bytes(3));
$userId = 860000 + random_int(1, 9999);
$now = time();

Db::startTrans();
try {
    $supplierId = Db::name('shop_supplier')->insertGetId([
        'code' => 'TEST-CART-SUP-' . $suffix,
        'name' => '购物车来源测试供应商',
        'company_name' => '购物车来源测试供应商',
        'fulfillment_mode' => 'SUPPLIER_DIRECT',
        'api_type' => 'MANUAL',
        'priority' => 100,
        'status' => 'normal',
        'createtime' => $now,
        'updatetime' => $now,
    ]);
    $supplierSkuId = Db::name('shop_supplier_sku')->insertGetId([
        'supplier_id' => $supplierId,
        'goods_id' => (int)$goods['id'],
        'goods_sku_id' => 0,
        'supplier_goods_code' => 'TEST-G-' . $suffix,
        'supplier_sku_code' => 'TEST-S-' . $suffix,
        'supply_price' => '3.20',
        'min_order_qty' => 1,
        'delivery_days' => 1,
        'fulfillment_mode' => 'SUPPLIER_DIRECT',
        'priority' => 100,
        'sync_status' => 'SUCCESS',
        'status' => 'normal',
        'createtime' => $now,
        'updatetime' => $now,
    ]);
    $warehouseId = Db::name('shop_warehouse')->insertGetId([
        'code' => 'TEST-CART-WH-' . $suffix,
        'name' => '购物车来源测试直发仓',
        'owner_type' => 'SUPPLIER',
        'owner_id' => $supplierId,
        'warehouse_type' => 'VIRTUAL_DIRECT',
        'status' => 'normal',
        'createtime' => $now,
        'updatetime' => $now,
    ]);
    $warehouseSkuId = Db::name('shop_warehouse_sku')->insertGetId([
        'warehouse_id' => $warehouseId,
        'supplier_id' => $supplierId,
        'supplier_sku_id' => $supplierSkuId,
        'goods_id' => (int)$goods['id'],
        'goods_sku_id' => 0,
        'on_hand_qty' => 20,
        'locked_qty' => 0,
        'unavailable_qty' => 0,
        'in_transit_qty' => 0,
        'version' => 0,
        'last_sync_time' => $now,
        'createtime' => $now,
        'updatetime' => $now,
    ]);
    Db::name('shop_supplier_delivery_region')->insert([
        'supplier_id' => $supplierId,
        'province_id' => 0,
        'city_id' => 0,
        'area_id' => 0,
        'shipping_fee' => '0.00',
        'free_shipping_amount' => '0.00',
        'delivery_days' => 1,
        'status' => 'normal',
        'createtime' => $now,
        'updatetime' => $now,
    ]);
    $ingredientId = Db::name('shop_ingredient')->insertGetId([
        'code' => 'TEST-CART-ING-' . $suffix,
        'name' => '购物车来源测试食材',
        'category' => '测试',
        'default_unit' => 'g',
        'aliases_json' => '[]',
        'status' => 'normal',
        'createtime' => $now,
        'updatetime' => $now,
    ]);
    $sourceHash = hash('sha256', 'cart-provenance-' . $suffix);
    $listId = Db::name('shop_shopping_list')->insertGetId([
        'list_sn' => 'TEST-CART-LIST-' . $suffix,
        'user_id' => $userId,
        'menu_version_id' => 'TEST-MENU-' . $suffix,
        'list_version' => 3,
        'source_hash' => $sourceHash,
        'status' => 'CONFIRMED',
        'confirmed_at' => $now,
        'createtime' => $now,
        'updatetime' => $now,
    ]);
    $listItemId = Db::name('shop_shopping_list_item')->insertGetId([
        'shopping_list_id' => $listId,
        'ingredient_id' => $ingredientId,
        'required_quantity' => '500.000',
        'home_quantity' => '0.000',
        'net_quantity' => '500.000',
        'unit' => 'g',
        'source_refs_json' => '[]',
        'constraint_result_json' => '{}',
        'selected_goods_id' => (int)$goods['id'],
        'selected_goods_sku_id' => 0,
        'selected_supplier_id' => $supplierId,
        'purchase_quantity' => 2,
        'covered_quantity' => '500.000',
        'shortage_quantity' => '0.000',
        'excess_quantity' => '0.000',
        'purchase_mode' => 'PLATFORM',
        'substitution_confirmed' => 0,
        'createtime' => $now,
        'updatetime' => $now,
    ]);

    $cart = CartService::addConfirmedShoppingList($userId, $listId, 3);
    cartAssertSame(1, count($cart), 'Confirmed list must create one cart row');
    $cartId = (int)$cart[0]['id'];
    cartAssertSame((int)$listItemId, (int)$cart[0]['source']['shopping_list_item_id'], 'Cart must expose list item provenance');
    cartAssertSame((int)$supplierId, (int)$cart[0]['source']['preferred_supplier_id'], 'Cart must preserve the preferred supplier');

    $repeated = CartService::addConfirmedShoppingList($userId, $listId, 3);
    cartAssertSame($cartId, (int)$repeated[0]['id'], 'Adding the same list again must be idempotent');
    cartAssertSame(1, Db::name('shop_cart_ext')->where('shopping_list_item_id', $listItemId)->count(), 'List item provenance must remain unique');

    $versionConflict = false;
    try {
        CartService::addConfirmedShoppingList($userId, $listId, 2);
    } catch (RuntimeException $e) {
        $versionConflict = (int)$e->getCode() === 409;
    }
    cartAssertSame(true, $versionConflict, 'Changed list version must be rejected');

    $addressId = Db::name('shop_address')->insertGetId([
        'user_id' => $userId,
        'province_id' => 0,
        'city_id' => 0,
        'area_id' => 0,
        'receiver' => '购物车来源测试用户',
        'mobile' => '13800000000',
        'address' => '测试地址',
        'zipcode' => '',
        'usednums' => 0,
        'createtime' => $now,
        'updatetime' => $now,
        'isdefault' => 1,
        'status' => 'normal',
    ]);
    Db::name('shop_goods')->where('id', (int)$goods['id'])->update(['stocks' => 0]);
    $preview = OrderService::previewCart($addressId, $userId, [$cartId]);
    cartAssertSame((int)$supplierId, (int)$preview['items'][0]['supplier_id'], 'Checkout preview must honor the preferred supplier');
    cartAssertSame('0.00', (string)$preview['pricing']['shipping_fee'], 'Checkout preview must calculate supplier shipping independently');
    cartAssertSame(true, !empty($preview['checkout_token']), 'Checkout preview must return a checkout token');

    Db::name('shop_warehouse_sku')->where('id', (int)$warehouseSkuId)->setInc('version');
    $stalePreviewRejected = false;
    try {
        OrderService::createFromCart(
            $addressId,
            $userId,
            [$cartId],
            0,
            '过期结算预览测试',
            'TEST-CART-STALE-' . $suffix,
            0,
            0,
            '',
            $preview['checkout_token']
        );
    } catch (RuntimeException $e) {
        $stalePreviewRejected = (int)$e->getCode() === 409;
    }
    cartAssertSame(true, $stalePreviewRejected, 'Changed inventory must invalidate the checkout preview');
    $preview = OrderService::previewCart($addressId, $userId, [$cartId]);
    $order = OrderService::createFromCart(
        $addressId,
        $userId,
        [$cartId],
        0,
        '购物车来源测试订单',
        'TEST-CART-ORDER-' . $suffix,
        0,
        0,
        '',
        $preview['checkout_token']
    );
    $orderGoodsExtension = Db::name('shop_order_goods_ext')
        ->alias('ext')
        ->join('__SHOP_ORDER_GOODS__ goods', 'goods.id = ext.order_goods_id')
        ->where('goods.order_sn', $order->order_sn)
        ->field('ext.*')
        ->find();
    cartAssertSame((int)$supplierId, (int)$orderGoodsExtension['supplier_id'], 'Order must honor the deliverable preferred supplier');
    cartAssertSame((int)$listItemId, (int)$orderGoodsExtension['shopping_list_item_id'], 'Order item must preserve shopping list item provenance');
    cartAssertSame((int)$ingredientId, (int)$orderGoodsExtension['ingredient_id'], 'Order item must preserve ingredient provenance');
    cartAssertSame(0, Db::name('shop_cart_ext')->where('cart_id', $cartId)->count(), 'Cart provenance must be removed after order creation');
    cartAssertSame(0, Db::name('shop_carts')->where('id', $cartId)->count(), 'Cart row must be removed after order creation');

    $snapshot = Db::name('shop_order_snapshot')->where('order_id', (int)$order->id)->where('snapshot_type', 'ORDER')->find();
    $snapshotData = json_decode($snapshot['snapshot_json'], true);
    cartAssertSame($sourceHash, $snapshotData['allocations'][0]['source_hash'], 'Order snapshot must preserve the source hash');

    Db::rollback();
} catch (Throwable $e) {
    Db::rollback();
    fwrite(STDERR, $e->getTraceAsString() . PHP_EOL);
    throw $e;
}

echo "Cart provenance integration test passed.\n";
