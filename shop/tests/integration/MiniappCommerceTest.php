<?php

$_SERVER['REMOTE_ADDR'] = '127.0.0.1';
require dirname(__DIR__) . '/bootstrap.php';

use think\Db;
use addons\shop\library\v5\AddressService;
use addons\shop\library\v5\CartService;
use addons\shop\library\v5\CatalogService;
use addons\shop\library\v5\CheckoutService;
use addons\shop\library\v5\DeliveryService;
use addons\shop\library\v5\DomainException;
use addons\shop\library\v5\IdempotencyService;
use addons\shop\library\v5\InventoryService;
use addons\shop\library\v5\Json;
use addons\shop\controller\api\v1\CommerceOrder;

function miniAssert($condition, $message) { if (!$condition) throw new RuntimeException($message); }
function miniReject(callable $callback, $code) {
    try { $callback(); } catch (DomainException $e) { miniAssert($e->getCode() === $code, 'Unexpected rejection code: ' . $e->getCode()); return; }
    throw new RuntimeException('Expected rejection: ' . $code);
}
function miniOrderRequest($sn, $action, $method, $key) {
    $request = \think\Request::create('http://localhost/api/v1/commerce/orders/' . $sn, $method, [], [], [], [
        'REMOTE_ADDR' => '127.0.0.1', 'HTTP_IDEMPOTENCY_KEY' => $key,
    ]);
    $request->controller('api.v1.commerce_order')->action($action)->route(['order_sn' => $sn]);
    (new \ReflectionProperty(\think\Request::class, 'instance'))->setValue(null, $request);
    return new CommerceOrder($request);
}

$suffix = bin2hex(random_bytes(5));
Db::startTrans();
try {
    $uid = Db::name('user')->insertGetId(['username' => 'mini_test_' . $suffix, 'nickname' => 'Miniapp integration test', 'status' => 'normal']);
    $other = $uid + 10000000;
    $original = Db::name('shop_goods_sku')->alias('s')->join('shop_goods g', 'g.id=s.goods_id')->where('g.catalog_status', 'published')->field('s.id')->find();
    miniAssert((bool)$original, 'Published fixture template required');
    $sku = Db::name('shop_goods_sku')->where('id', $original['id'])->find();
    $goods = Db::name('shop_goods')->where('id', $sku['goods_id'])->find();
    unset($goods['id'], $sku['id']);
    $goods['title'] = 'MINIAPP-TEST-' . $suffix; $goods['goods_sn'] = 'MINI-' . $suffix;
    $goods['image'] = '/uploads/test.jpg'; $goods['agent_visible'] = 1; $goods['status'] = 'normal';
    $gid = Db::name('shop_goods')->insertGetId($goods);
    $sku['goods_id'] = $gid; $sku['sku_code'] = 'MINI-' . $suffix; $sku['image'] = '/uploads/test.jpg'; $sku['stocks'] = 20; $sku['reserved_stock'] = 0; $sku['safety_stock'] = 0; $sku['price'] = '12.34';
    $sid = Db::name('shop_goods_sku')->insertGetId($sku);
    $addresses = new AddressService(); $cart = new CartService(); $checkout = new CheckoutService();
    $a = $addresses->save($uid, ['name' => 'TEST ONLY', 'phone' => '13800000000', 'region' => '上海市 徐汇区', 'detail' => 'TEST ADDRESS']);
    miniAssert($a['isDefault'] && $a['version'] === 1, 'Address persisted with default and version');
    miniReject(function () use ($addresses, $other, $a) { $addresses->selectDefault($other, $a['id']); }, 40407);
    $area = Db::name('shop_area')->where('id', $a['area_id'])->find();
    $deliveryId = Db::name('shop_delivery_area')->insertGetId(['area_code' => 'MINI-' . $suffix, 'name' => 'TEST ONLY', 'district_code' => $area['adcode'], 'status' => 'normal']);
    $idem = new IdempotencyService(); $intent = ['sku_id' => $sid, 'quantity' => 2];
    $add = function () use ($uid, $sid, $cart) { return $cart->add($uid, $sid, 2); };
    $first = $idem->run('mini.test', 'test:' . $uid, $suffix, $intent, $add);
    $again = $idem->run('mini.test', 'test:' . $uid, $suffix, $intent, $add);
    miniAssert($first['items'][0]['quantity'] === 2 && $again['items'][0]['quantity'] === 2, 'Add retry is idempotent');
    $line = $first['items'][0];
    miniAssert(strpos($line['image_url'], '/uploads/test.jpg') !== false, 'Image URL survives adapter');
    miniReject(function () use ($cart, $uid, $line) { $cart->update($uid, $line['cart_item_id'], 21, $line['version']); }, 40904);
    $cart->select($uid, $line['cart_item_id'], false, $line['version']);
    miniAssert($cart->listItems($uid)['valid_total_amount_cent'] === 0, 'Deselection persisted');
    miniReject(function () use ($cart, $uid, $line) { $cart->update($uid, $line['cart_item_id'], 3, $line['version']); }, 40906);
    $line = $cart->listItems($uid)['items'][0];
    $cart->select($uid, $line['cart_item_id'], true, $line['version']);
    $line = $cart->listItems($uid)['items'][0];
    $refs = [['cart_item_id' => $line['cart_item_id'], 'version' => $line['version']]];
    miniReject(function () use ($cart, $other, $refs) { $cart->checkoutItems($other, $refs); }, 40906);
    $payload = ['source_type' => 'cart', 'source_ref' => (string)$uid, 'source_version' => 1, 'address_id' => $a['id'], 'cart_items' => $refs, 'items' => [['sku_id' => $sid, 'quantity' => 999]], 'payable_amount_cent' => 1];
    $quote = $checkout->preview($uid, $payload);
    miniAssert($quote['payable_amount_cent'] === 2468, 'Quote ignores client amount and item override');
    $addresses->save($uid, array_merge($a, ['detail' => 'CHANGED ADDRESS']));
    $otherGoods = $goods; $otherGoods['goods_sn'] = 'MINI2-' . $suffix;
    $otherGid = Db::name('shop_goods')->insertGetId($otherGoods);
    $otherSku = $sku; $otherSku['goods_id'] = $otherGid; $otherSku['sku_code'] = 'MINI2-' . $suffix;
    $otherSid = Db::name('shop_goods_sku')->insertGetId($otherSku);
    $cart->add($uid, $otherSid, 1);
    $created = $checkout->createOrder($uid, ['checkout_token' => $quote['checkout_token']], 'mini_' . $suffix);
    miniAssert($created['pay_status'] === 'unpaid', 'Creating order does not mark it paid');
    miniAssert((int)Db::name('shop_goods_sku')->where('id', $sid)->value('reserved_stock') === 2, 'Order reserves inventory');
    miniAssert(count($cart->listItems($uid)['items']) === 1, 'Only purchased cart lines removed');
    $ext = Db::name('shop_order_ext')->where('order_sn', $created['order_sn'])->find();
    miniAssert(Json::decode($ext['address_snapshot_json'])['detail'] === 'TEST ADDRESS', 'Order uses immutable quote address');
    miniReject(function () use ($checkout, $uid, $quote, $suffix) { $checkout->createOrder($uid, ['checkout_token' => $quote['checkout_token']], 'again_' . $suffix); }, 40918);
    $request = \think\Request::create('http://localhost/', 'GET', [], [], [], ['REMOTE_ADDR' => '127.0.0.1']);
    (new \ReflectionProperty(\think\Request::class, 'instance'))->setValue(null, $request);
    miniAssert(\app\common\library\Auth::instance()->direct($uid), 'Synthetic member authentication: ' . \app\common\library\Auth::instance()->getError());
    $detail = miniOrderRequest($created['order_sn'], 'detail', 'GET', 'mini_' . $suffix)->detail()->getData();
    miniAssert($detail['code'] === 0 && (int)$detail['data']['items'][0]['quantity'] === 2, 'Order detail resolves route and joins SKU/quantity');
    miniAssert($detail['data']['extension']['address_snapshot']['region'] === $a['region'], 'Order keeps full region snapshot');
    $listing = miniOrderRequest($created['order_sn'], 'index', 'GET', 'mini_' . $suffix)->index()->getData();
    miniAssert($listing['code'] === 0, 'Order list: ' . $listing['message']);
    miniAssert(count($listing['data']['items']) === 1 && count($listing['data']['items'][0]['items']) === 1, 'Order list includes only this member with real line previews');
    $receipt = miniOrderRequest($created['order_sn'], 'receipt', 'POST', 'receipt_' . $suffix)->receipt()->getData();
    miniAssert($receipt['code'] === 40910, 'Unpaid order receipt rejected by server');
    $cancelled = miniOrderRequest($created['order_sn'], 'cancel', 'POST', 'cancel_' . $suffix)->cancel()->getData();
    miniAssert($cancelled['code'] === 0, 'User cancels the owned unpaid order');
    miniAssert((int)Db::name('shop_order')->where('order_sn', $created['order_sn'])->value('orderstate') === 1, 'Cancellation persisted');
    miniAssert((int)Db::name('shop_goods_sku')->where('id', $sid)->value('reserved_stock') === 0, 'Released inventory restored');
    // A synthetic shipped/paid state exercises receipt without calling a payment gateway.
    Db::name('shop_order')->where('order_sn', $created['order_sn'])->update(['paystate' => 1, 'shippingstate' => 1, 'orderstate' => 0]);
    $received = miniOrderRequest($created['order_sn'], 'receipt', 'POST', 'received_' . $suffix)->receipt()->getData();
    miniAssert($received['code'] === 0, 'Shipped paid fixture may be received');
    miniAssert((int)Db::name('shop_order')->where('order_sn', $created['order_sn'])->value('shippingstate') === 2, 'Receipt persisted on server');
    miniAssert(Db::name('shop_order_ext')->where('order_sn', $created['order_sn'])->value('business_status') === 'completed', 'Receipt updates business status');
    $addresses->remove($uid, $a['id']);
    miniReject(function () use ($uid, $a) { (new DeliveryService())->validateAddress($uid, $a['id']); }, 40407);
    Db::rollback();
    miniAssert(!Db::name('user')->where('username', 'mini_test_' . $suffix)->find(), 'Test user rolled back');
    miniAssert(!Db::name('shop_goods')->where('goods_sn', 'MINI-' . $suffix)->find(), 'Test goods rolled back');
    echo "Miniapp commerce integration passed; all fixtures rolled back.\n";
} catch (\Throwable $e) { Db::rollback(); throw $e; }
