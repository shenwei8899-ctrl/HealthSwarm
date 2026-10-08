<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\CheckoutService;
use addons\shop\library\v5\IdempotencyService;
use addons\shop\library\v5\ServicePlanService;
use addons\shop\library\v5\DeliveryService;
use think\Db;

class CommercePlan extends Base
{
    public function index()
    {
        return $this->execute(function () {
            $items = Db::name('shop_service_plan')->where('user_id', $this->userId())->order('id', 'desc')
                ->field('plan_sn,plan_name,plan_days,delivery_frequency,current_version,nutrition_status,trade_status,review_gate_status,estimated_amount_cent,status,createtime')->select();
            return ['items' => $items];
        });
    }

    public function detail($plan_sn = null)
    {
        return $this->execute(function () use ($plan_sn) {
            return (new ServicePlanService())->getBySn($plan_sn, $this->userId());
        });
    }

    public function calendar($plan_sn = null)
    {
        return $this->execute(function () use ($plan_sn) {
            $plan = (new ServicePlanService())->getBySn($plan_sn, $this->userId());
            return ['plan_sn' => $plan_sn, 'plan_version' => $plan['plan_version'], 'days' => $plan['days']];
        });
    }

    public function policy($plan_sn = null)
    {
        return $this->execute(function () use ($plan_sn) {
            (new ServicePlanService())->getBySn($plan_sn, $this->userId());
            return (new ServicePlanService())->policy();
        });
    }

    public function checkout($plan_sn = null)
    {
        return $this->execute(function () use ($plan_sn) {
            $this->requireMethod('POST');
            $payload = $this->input();
            $userId=$this->userId();
            $plan = (new ServicePlanService())->getBySn($plan_sn, $userId);
            $payload['source_type'] = 'service_plan';
            $payload['source_ref'] = $plan_sn;
            $payload['source_version'] = $plan['plan_version'];
            return (new IdempotencyService())->run('commerce.plan.checkout','miniapp:'.$userId,$this->request->header('idempotency-key'),$payload,function()use($userId,$payload){
                return (new CheckoutService())->preview($userId, $payload, [
                    'request_id' => $this->requestId, 'ip' => $this->request->ip(),
                    'device_id' => $this->request->header('x-device-id'),
                    'displayed_at' => !empty($payload['policy_displayed_at']) ? strtotime($payload['policy_displayed_at']) : time(),
                ]);
            },900);
        });
    }

    public function tradeValidate($plan_sn = null)
    {
        return $this->execute(function () use ($plan_sn) { $this->requireMethod('POST');$p=$this->input();$uid=$this->userId();return(new IdempotencyService())->run('commerce.plan.trade_validate','miniapp:'.$uid,$this->request->header('idempotency-key'),['plan_sn'=>$plan_sn]+$p,function()use($uid,$plan_sn,$p){if(!empty($p['address_id']))(new DeliveryService())->validateAddress($uid,$p['address_id'],isset($p['delivery_slot_id'])?$p['delivery_slot_id']:0);return(new ServicePlanService())->revalidateTrade($plan_sn,$uid);}); });
    }

    public function schedulePreview($plan_sn = null)
    {
        return $this->execute(function () use ($plan_sn) {$p=$this->input();$plan=(new ServicePlanService())->getBySn($plan_sn,$this->userId());if(empty($p['first_delivery_date'])||!preg_match('/^\d{4}-\d{2}-\d{2}$/',$p['first_delivery_date']))throw new \addons\shop\library\v5\DomainException('首批配送日期格式错误',40011,400);$delivery=(new DeliveryService())->validateAddress($this->userId(),$p['address_id'],isset($p['delivery_slot_id'])?$p['delivery_slot_id']:0);$first=strtotime($p['first_delivery_date'].' 00:00:00');if($first<strtotime(date('Y-m-d')))throw new \addons\shop\library\v5\DomainException('首批配送日期不能早于今天',40011,400);$items=[];for($i=0;$i<21;$i++){$date=strtotime('+'.$i.' day',$first);$items[]=['batch_no'=>$i+1,'delivery_date'=>date('Y-m-d',$date),'meal_date'=>date('Y-m-d',strtotime('+1 day',$date)),'inventory_lock_at'=>date(DATE_ATOM,strtotime('-3 day',$date)),'address'=>$delivery['snapshot'],'slot'=>$delivery['slot']];}return ['plan_sn'=>$plan_sn,'plan_version'=>$plan['plan_version'],'total_batches'=>21,'items'=>$items];});
    }
}
