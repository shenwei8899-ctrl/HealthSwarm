<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\IdempotencyService;
use addons\shop\library\v5\PurchaseListService;
use addons\shop\library\v5\RecommendationPackageService;
use addons\shop\library\v5\DeliveryService;
use think\Db;

class CommerceRecommendation extends Base
{
    public function detail($package_sn = null)
    {
        return $this->execute(function () use ($package_sn) {
            return (new RecommendationPackageService())->getBySn($package_sn, $this->userId());
        });
    }

    public function confirm($package_sn = null)
    {
        return $this->execute(function () use ($package_sn) {
            $this->requireMethod('POST');
            $payload = $this->input();
            $userId = $this->userId();
            return (new IdempotencyService())->run('commerce.recommendation.confirm', 'miniapp:' . $userId, $this->request->header('idempotency-key'), $payload, function () use ($userId, $package_sn, $payload) {
                return (new PurchaseListService())->confirmRecommendation($userId, $package_sn, $payload['package_version'], $this->requestId);
            });
        });
    }

    public function purchaseList($package_sn = null)
    {
        return $this->confirm($package_sn);
    }

    public function versions($package_sn = null)
    {
        return $this->execute(function () use ($package_sn) {$pkg=Db::name('shop_recommendation_package')->where('package_sn',$package_sn)->where('user_id',$this->userId())->find();if(!$pkg)throw new \addons\shop\library\v5\DomainException('推荐包不存在',40402,404);return ['items'=>Db::name('shop_recommendation_package_version')->where('package_id',$pkg['id'])->field('version_no,base_version_no,menu_version_ref,change_type,nutrition_status,trade_status,total_amount_cent,createtime')->order('version_no','desc')->select()];});
    }

    public function tradeValidate($package_sn = null)
    {
        return $this->execute(function () use ($package_sn) {$this->requireMethod('POST');$p=$this->input();$uid=$this->userId();return(new IdempotencyService())->run('commerce.recommendation.trade_validate','miniapp:'.$uid,$this->request->header('idempotency-key'),['package_sn'=>$package_sn]+$p,function()use($uid,$package_sn,$p){$pkg=Db::name('shop_recommendation_package')->where('package_sn',$package_sn)->where('user_id',$uid)->find();if(!$pkg)throw new \addons\shop\library\v5\DomainException('推荐包不存在',40402,404);if(isset($p['package_version'])&&(int)$p['package_version']!==(int)$pkg['current_version'])throw new \addons\shop\library\v5\DomainException('推荐包版本冲突',40906,409,['current_version'=>(int)$pkg['current_version']]);if(!empty($p['address_id']))(new DeliveryService())->validateAddress($pkg['user_id'],$p['address_id'],isset($p['delivery_slot_id'])?$p['delivery_slot_id']:0);return(new RecommendationPackageService())->revalidateTrade($pkg['id']);});});
    }
}
