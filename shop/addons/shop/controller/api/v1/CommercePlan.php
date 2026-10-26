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
            $group = trim((string)$this->request->get('group_ref',''));
            if ($group === '') throw new \addons\shop\library\v5\DomainException('请指定当前推荐组',40001,400);
            $rows=Db::name('shop_service_plan')->where('user_id',$this->userId())->where('recommendation_group_ref',$group)->order('id','asc')->select();
            $items=[];
            foreach ($rows as $row) {
                $item=(new ServicePlanService())->getBySn($row['plan_sn'],$this->userId());
                if ($item['estimate_valid_until']<=time() || $item['trade_validation_status']!=='passed') $item=(new ServicePlanService())->revalidateTrade($row['plan_sn'],$this->userId(),$item['plan_version']);
                unset($item['days'],$item['trade_draft']);
                $items[]=$item;
            }
            return ['recommendation_group_ref'=>$group,'items'=>$items];
        });
    }

    public function detail($plan_sn = null)
    {
        return $this->execute(function () use ($plan_sn) {
            $plan=(new ServicePlanService())->getBySn($plan_sn,$this->userId());
            $this->assertVersion($plan,$this->request->get('plan_version'));
            return $plan;
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
            $this->assertVersion($plan,$payload['source_version'] ?? null);
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
        return $this->execute(function () use ($plan_sn) { $this->requireMethod('POST');$p=$this->input();$uid=$this->userId();return(new IdempotencyService())->run('commerce.plan.trade_validate','miniapp:'.$uid,$this->request->header('idempotency-key'),['plan_sn'=>$plan_sn]+$p,function()use($uid,$plan_sn,$p){if(!empty($p['address_id']))(new DeliveryService())->validateAddress($uid,$p['address_id'],isset($p['delivery_slot_id'])?$p['delivery_slot_id']:0);return(new ServicePlanService())->revalidateTrade($plan_sn,$uid,$p['plan_version'] ?? 0);}); });
    }

    public function availableDates($plan_sn = null)
    {
        return $this->execute(function () use ($plan_sn) {
            $plan=(new ServicePlanService())->getBySn($plan_sn,$this->userId());
            $this->assertVersion($plan,$this->request->get('plan_version'));
            $delivery=(new DeliveryService())->validateAddress($this->userId(),$this->request->get('address_id'),$this->request->get('delivery_slot_id',0));
            return (new \addons\shop\library\v5\PlanScheduleService())->availableDates((new \addons\shop\library\v5\PlanPolicyService())->current(),$delivery);
        });
    }

    public function schedulePreview($plan_sn = null)
    {
        return $this->execute(function () use ($plan_sn) {
            $this->requireMethod('POST');$p=$this->input();
            $plan=(new ServicePlanService())->getBySn($plan_sn,$this->userId());
            $this->assertVersion($plan,$p['plan_version'] ?? null);
            $delivery=(new DeliveryService())->validateAddress($this->userId(),$p['address_id'] ?? 0,$p['delivery_slot_id'] ?? 0);
            $schedule=(new \addons\shop\library\v5\PlanScheduleService())->preview((new \addons\shop\library\v5\PlanPolicyService())->current(),$delivery,$p['first_delivery_date'] ?? '');
            return ['plan_sn'=>$plan_sn,'plan_version'=>$plan['plan_version']]+$schedule;
        });
    }

    protected function assertVersion(array $plan, $selected)
    {
        if (!$selected || (int)$selected!==$plan['plan_version']) throw new \addons\shop\library\v5\DomainException('计划已变化，请重新查看后选择',40906,409,['current_version'=>$plan['plan_version']]);
    }
}
