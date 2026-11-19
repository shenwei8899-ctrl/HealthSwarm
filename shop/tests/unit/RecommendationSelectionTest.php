<?php
$library = dirname(__DIR__, 2) . '/addons/shop/library/v5/';
foreach (['DomainException.php','CheckoutService.php'] as $file) require_once $library.$file;
use addons\shop\library\v5\{CheckoutService,DomainException};
$package=[['sku_id'=>'101','quantity'=>2],['sku_id'=>'102','quantity'=>1]];
$subset=[['sku_id'=>'102','quantity'=>3]];
if(CheckoutService::recommendationItems($package)!==$package || CheckoutService::recommendationItems($package,$subset)!==$subset) throw new RuntimeException('selection changed');
foreach ([[],[['sku_id'=>'999','quantity'=>1]],[['sku_id'=>'101','quantity'=>1],['sku_id'=>'101','quantity'=>1]],[['sku_id'=>'101','quantity'=>0]],[['sku_id'=>'101','quantity'=>1.5]],[['sku_id'=>'101','quantity'=>'2']],['invalid']] as $bad) {
    try { CheckoutService::recommendationItems($package,$bad); } catch(DomainException $e) { continue; }
    throw new RuntimeException('invalid selection accepted');
}
echo "Recommendation subset and negative cases passed\n";
