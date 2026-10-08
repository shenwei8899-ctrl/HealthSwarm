<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\IdempotencyService;
use addons\shop\library\v5\PlanOrderService;
use addons\shop\library\v5\ServicePlanService;

class IntegrationAiPlan extends IntegrationBase
{
    protected $expectedClientType = 'agent';

    public function create()
    {
        return $this->execute(function () {
            $this->requireMethod('POST');
            $payload = $this->input();
            return (new IdempotencyService())->run('ai.plan.create', $this->clientId(), $this->request->header('idempotency-key'), $payload, function () use ($payload) {
                return (new ServicePlanService())->create($this->clientId(), $payload, $this->requestId);
            });
        }, $this->integrationLog('ai_plan_create', 'service_plan'));
    }

    public function version($plan_sn = null)
    {
        return $this->execute(function () use ($plan_sn) {
            $this->requireMethod('POST');
            $payload = $this->input();
            return (new IdempotencyService())->run('ai.plan.version', $this->clientId(), $this->request->header('idempotency-key'), $payload, function () use ($plan_sn, $payload) {
                return (new ServicePlanService())->createVersion($this->clientId(), $plan_sn, $payload, $this->requestId);
            });
        }, $this->integrationLog('ai_plan_version', 'service_plan', $plan_sn));
    }

    public function detail($plan_sn = null)
    {
        return $this->execute(function () use ($plan_sn) {
            $owner = \think\Db::name('shop_service_plan')->where('plan_sn', $plan_sn)->value('agent_client_id');
            if (!$owner || $owner !== $this->clientId()) throw new \addons\shop\library\v5\DomainException('专属计划不存在',40404,404);
            return (new ServicePlanService())->getBySn($plan_sn);
        }, $this->integrationLog('ai_plan_detail', 'service_plan', $plan_sn));
    }

    public function resumeValidation($order_sn = null)
    {
        return $this->execute(function () use ($order_sn) {
            $this->requireMethod('POST');
            $payload = $this->input();
            return (new IdempotencyService())->run('ai.plan.resume_validation', $this->clientId(), $this->request->header('idempotency-key'), $payload, function () use ($order_sn, $payload) {
                return (new PlanOrderService())->applyResumeValidation($this->clientId(), $order_sn, $payload, $this->requestId);
            });
        }, $this->integrationLog('ai_plan_resume_validation', 'plan_order', $order_sn));
    }
}
