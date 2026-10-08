<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\IdempotencyService;
use addons\shop\library\v5\RecommendationPackageService;

class IntegrationAiRecommendation extends IntegrationBase
{
    protected $expectedClientType = 'agent';

    public function create()
    {
        return $this->execute(function () {
            $this->requireMethod('POST');
            $payload = $this->input();
            return (new IdempotencyService())->run('ai.recommendation.create', $this->clientId(), $this->request->header('idempotency-key'), $payload, function () use ($payload) {
                return (new RecommendationPackageService())->create($this->clientId(), $payload, $this->requestId);
            });
        }, $this->integrationLog('ai_recommendation_create', 'recommendation_package'));
    }

    public function detail($package_sn = null)
    {
        return $this->execute(function () use ($package_sn) {
            $owner = \think\Db::name('shop_recommendation_package')->where('package_sn', $package_sn)->value('agent_client_id');
            if (!$owner || $owner !== $this->clientId()) throw new \addons\shop\library\v5\DomainException('推荐包不存在',40402,404);
            return (new RecommendationPackageService())->getBySn($package_sn);
        }, $this->integrationLog('ai_recommendation_detail', 'recommendation_package', $package_sn));
    }

    public function swap($package_sn = null)
    {
        return $this->execute(function () use ($package_sn) {
            $this->requireMethod('POST');
            $payload = $this->input();
            return (new IdempotencyService())->run('ai.recommendation.swap', $this->clientId(), $this->request->header('idempotency-key'), $payload, function () use ($package_sn, $payload) {
                return (new RecommendationPackageService())->createSwapVersion($this->clientId(), $package_sn, $payload, $this->requestId);
            });
        }, $this->integrationLog('ai_recommendation_swap', 'recommendation_package', $package_sn));
    }
}
