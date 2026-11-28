<?php

use addons\shop\library\v5\DomainException;
use addons\shop\library\v5\ExclusivePurchaseDeliveryService;

require dirname(__DIR__,2).'/addons/shop/library/v5/DomainException.php';
require dirname(__DIR__,2).'/addons/shop/library/v5/ExclusivePurchaseDeliveryService.php';

function expect($condition, $message) { if (!$condition) throw new RuntimeException($message); }
function reject($requirements, $items, $reason) {
    try { ExclusivePurchaseDeliveryService::allocate($requirements,$items); }
    catch (DomainException $error) { expect(($error->getDetails()['reason'] ?? '') === $reason,'Wrong rejection'); return; }
    throw new RuntimeException('Expected '.$reason);
}
function entry($id,$days,$width) {
    return ['sku_id'=>$id,'food'=>$id,'uses'=>array_map(static function($day){return ['day_no'=>$day,'weight'=>100];},$days),
        'storage_rule'=>['review_status'=>'approved','max_days'=>$width,'condition'=>'refrigerated','source'=>'synthetic-only','version'=>'test-v1']];
}
$rules=['version'=>1,'period_days'=>7,'items'=>[entry('rice',[6,7],7),entry('greens',range(1,7),3)]];
$selected=[['sku_id'=>'rice','quantity'=>2,'unit_price_cent'=>500],['sku_id'=>'greens','quantity'=>5,'unit_price_cent'=>300]];
$result=ExclusivePurchaseDeliveryService::allocate($rules,$selected);
expect(array_keys($result)===[1,4,7],'Actual storage windows must determine trips');
expect($result[1][0]['sku_id']==='rice' && $result[1][0]['quantity']===2,'Durable food first used late still arrives in first trip');
$totals=[];$amount=0;
foreach($result as $batch)foreach($batch as $item){$totals[$item['sku_id']]=($totals[$item['sku_id']]??0)+$item['quantity'];$amount+=$item['line_amount_cent'];}
expect($totals===['rice'=>2,'greens'=>5],'Pack quantities must exactly equal actual selected totals');
expect($amount===2500,'Batch goods amounts sum to selected amount');
$onlyRice=ExclusivePurchaseDeliveryService::allocate($rules,[$selected[0]]);
expect(count($onlyRice)===1 && count($onlyRice[1])===1,'Deselected fresh item cannot leave phantom trips');
reject($rules,[['sku_id'=>'greens','quantity'=>2]],'insufficient_delivery_packs');
$draft=$rules;$draft['items'][1]['storage_rule']['review_status']='draft';
reject($draft,[$selected[1]],'storage_rule_pending');
$unknown=$rules;$unknown['items'][1]['storage_rule']=null;
reject($unknown,[$selected[1]],'storage_rule_pending');
reject($rules,[['sku_id'=>'foreign','quantity'=>3]],'storage_rule_pending');
for($quantity=3;$quantity<=50;$quantity++) {
    $allocation=ExclusivePurchaseDeliveryService::allocate($rules,[['sku_id'=>'greens','quantity'=>$quantity]]);
    expect(array_sum(array_map(static function($rows){return $rows[0]['quantity'];},$allocation))===$quantity,'Rounding must conserve packages');
    foreach($allocation as $rows)expect($rows[0]['quantity']>=1,'Each freshness window receives a whole pack');
}
echo "Exclusive purchase allocation, selection, rounding and rule rejection passed.\n";
