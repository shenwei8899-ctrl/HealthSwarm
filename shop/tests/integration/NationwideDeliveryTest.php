<?php

require dirname(__DIR__) . '/bootstrap.php';

use think\Db;
use addons\shop\library\v5\AddressService;
use addons\shop\library\v5\CartService;
use addons\shop\library\v5\CatalogService;
use addons\shop\library\v5\CheckoutService;
use addons\shop\library\v5\DeliveryService;
use addons\shop\library\v5\DomainException;
use addons\shop\library\v5\Json;

function nationalAssert($condition, $message) { if (!$condition) throw new RuntimeException($message); }
$provinces = Db::name('shop_area')->where('level', 1)->where('status', 'normal')->select();
$districts = Db::name('shop_area')->alias('d')->join('shop_area c', 'c.id=d.pid')->join('shop_area p', 'p.id=c.pid')
    ->where('d.level', 3)->where('d.status', 'normal')->where('c.status', 'normal')->where('p.status', 'normal')
    ->field('d.id,d.name,d.adcode,c.id as city_id,c.name as city_name,p.id as province_id,p.name as province_name,p.adcode as province_code')->select();
$coverage = Db::name('shop_delivery_area')->where('status', 'normal')->where('supplier_id', 0)
    ->where('city_code', '')->where('district_code', '')->column('province_code');
nationalAssert(count($provinces) === count(array_unique($coverage)), 'Every active province has platform delivery coverage');
$samples = [];
foreach ($districts as $district) {
    nationalAssert(in_array($district['province_code'], $coverage, true), 'Uncovered selectable district: ' . $district['adcode']);
    $samples[$district['province_id']] = $district;
}
nationalAssert(count($districts) === (int)Db::name('shop_area')->where('level', 3)->where('status', 'normal')->count(), 'Every active district has a valid province/city hierarchy');
nationalAssert((bool)$samples, 'Selectable district addresses are required for checkout verification');
$sku = (new CatalogService())->listProducts(['limit' => 1])['items'][0] ?? null;
nationalAssert((bool)$sku, 'A published in-stock SKU is required for checkout verification');
$suffix = bin2hex(random_bytes(8));
Db::startTrans();
try {
    $uid = Db::name('user')->insertGetId(['username' => 'national_test_' . $suffix, 'nickname' => 'Nationwide delivery test', 'status' => 'normal']);
    $cartService = new CartService();
    $line = $cartService->add($uid, $sku['sku_id'], 1)['items'][0];
    $addresses = new AddressService();
    $checkout = new CheckoutService();
    foreach ($samples as $district) {
        $address = $addresses->save($uid, [
            'name' => 'TEST ONLY', 'phone' => '13800000000', 'detail' => 'TEST ADDRESS',
            'region' => $district['province_name'] . ' ' . $district['city_name'] . ' ' . $district['name'], 'area_id' => $district['id'],
        ]);
        $delivery = (new DeliveryService())->validateAddress($uid, $address['id']);
        nationalAssert($delivery['snapshot']['district_code'] === $district['adcode'], 'Full district snapshot retained');
        $quote = $checkout->preview($uid, [
            'source_type' => 'cart', 'source_ref' => (string)$uid, 'source_version' => 1, 'address_id' => $address['id'],
            'cart_items' => [['cart_item_id' => $line['cart_item_id'], 'version' => $line['version']]],
        ]);
        nationalAssert($quote['payable_amount_cent'] === $sku['price_cent'], 'Nationwide checkout retains authoritative pricing');
    }
    // More specific regional rules override province coverage, including explicit stops.
    Db::execute('SAVEPOINT delivery_specific_rules');
    $service = new DeliveryService();
    $cityRule = Db::name('shop_delivery_area')->insertGetId([
        'area_code'=>'CITY-TEST-'.$suffix,'name'=>'City stop test','supplier_id'=>0,
        'province_code'=>$delivery['snapshot']['province_code'],'city_code'=>$delivery['snapshot']['city_code'],
        'district_code'=>'','status'=>'hidden',
    ]);
    $unsupported = $service->availability($uid, $address['id']);
    nationalAssert($unsupported['supported'] === false && $unsupported['reason_code'] === 'area_disabled', 'City stop overrides province coverage');
    $districtRule = Db::name('shop_delivery_area')->insertGetId([
        'area_code'=>'DISTRICT-TEST-'.$suffix,'name'=>'District override test','supplier_id'=>0,
        'province_code'=>$delivery['snapshot']['province_code'],'city_code'=>$delivery['snapshot']['city_code'],
        'district_code'=>$delivery['snapshot']['district_code'],'status'=>'normal',
    ]);
    nationalAssert($service->validateAddress($uid, $address['id'])['area']['id'] == $districtRule, 'Specific district rule is chosen over city and province');
    Db::name('shop_delivery_area')->where('id',$districtRule)->update(['status'=>'hidden']);
    nationalAssert($service->availability($uid, $address['id'])['supported'] === false, 'Disabled district cannot fall back to nationwide province');
    try {
        $checkout->createOrder($uid, ['checkout_token'=>$quote['checkout_token']], 'stale_district_'.$suffix);
        throw new RuntimeException('Old province quote bypassed a newly disabled district');
    } catch (DomainException $e) { nationalAssert($e->getCode() === 40914, 'New district stop invalidates the old province quote'); }
    try {
        $checkout->preview($uid, [
            'source_type'=>'cart','source_ref'=>(string)$uid,'source_version'=>1,'address_id'=>$address['id'],
            'cart_items'=>[['cart_item_id'=>$line['cart_item_id'],'version'=>$line['version']]],
        ]);
        throw new RuntimeException('Disabled district unexpectedly accepted checkout');
    } catch (DomainException $e) { nationalAssert($e->getCode() === 40914, 'Disabled district blocks checkout'); }
    try {
        $service->availability($uid + 1000000, $address['id']);
        throw new RuntimeException('Foreign address unexpectedly returned eligibility');
    } catch (DomainException $e) { nationalAssert($e->getCode() === 40407, 'Address ownership is still enforced'); }
    Db::execute('ROLLBACK TO SAVEPOINT delivery_specific_rules');
    Db::execute('SAVEPOINT delivery_slot_changes');
    $slotId = Db::name('shop_delivery_slot')->insertGetId([
        'area_id'=>$delivery['area']['id'],'slot_code'=>'STALE-SLOT-'.$suffix,'name'=>'TEST ONLY',
        'start_time'=>'10:00','end_time'=>'11:00','capacity'=>5,'status'=>'normal',
    ]);
    $slotQuote = $checkout->preview($uid, [
        'source_type'=>'cart','source_ref'=>(string)$uid,'source_version'=>1,'address_id'=>$address['id'],'delivery_slot_id'=>$slotId,
        'cart_items'=>[['cart_item_id'=>$line['cart_item_id'],'version'=>$line['version']]],
    ]);
    Db::name('shop_delivery_slot')->where('id',$slotId)->update(['status'=>'hidden']);
    foreach ([function () use ($checkout,$uid,$slotQuote,$suffix) {
        $checkout->createOrder($uid,['checkout_token'=>$slotQuote['checkout_token']],'stale_slot_'.$suffix);
    }, function () use ($service,$slotId) { $service->reserveSlot('TEST-ONLY',$slotId); }] as $operation) {
        try { $operation(); throw new RuntimeException('Disabled slot accepted'); }
        catch (DomainException $e) { nationalAssert($e->getCode() === 40915, 'Disabled slot rejected before order or reservation'); }
    }
    Db::execute('ROLLBACK TO SAVEPOINT delivery_slot_changes');
    // Disabling coverage must still block checkout; nationwide setup is not a bypass.
    Db::name('shop_delivery_area')->where('id', $delivery['area']['id'])->update(['status' => 'hidden']);
    try {
        $checkout->createOrder($uid, ['checkout_token' => $quote['checkout_token']], 'national_block_' . $suffix);
        throw new RuntimeException('Disabled coverage unexpectedly accepted');
    } catch (DomainException $e) { nationalAssert($e->getCode() === 40914, 'Disabled coverage rejection code'); }
    Db::name('shop_delivery_area')->where('id', $delivery['area']['id'])->update(['status' => 'normal']);
    $order = $checkout->createOrder($uid, ['checkout_token' => $quote['checkout_token']], 'national_' . $suffix);
    $stored = Db::name('shop_order')->where('order_sn', $order['order_sn'])->where('user_id', $uid)->find();
    $ext = Db::name('shop_order_ext')->where('order_sn', $order['order_sn'])->find();
    nationalAssert($stored && $order['pay_status'] === 'unpaid', 'Nationwide order persists unpaid');
    nationalAssert(Json::decode($ext['address_snapshot_json'])['district_code'] === $district['adcode'], 'Order persists its nationwide address snapshot');
    Db::rollback();
    nationalAssert(!Db::name('user')->where('username', 'national_test_' . $suffix)->find(), 'Synthetic member rolled back');
    nationalAssert(!Db::name('shop_order')->where('order_sn', $order['order_sn'])->find(), 'Synthetic order rolled back');
    echo 'Nationwide coverage passed: ' . count($provinces) . ' configured provinces, ' . count($districts) . ' districts; ' . count($samples) . " provinces with complete addresses passed checkout. Order persistence verified; all fixtures rolled back.\n";
    foreach ($provinces as $province) if (!isset($samples[$province['id']])) {
        echo 'No complete third-level address directory: ' . $province['name'] . "\n";
    }
} catch (\Throwable $e) { Db::rollback(); throw $e; }
