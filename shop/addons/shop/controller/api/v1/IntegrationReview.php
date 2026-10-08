<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\DomainException;
use addons\shop\library\v5\IdempotencyService;
use addons\shop\library\v5\Json;
use think\Db;

class IntegrationReview extends IntegrationBase
{
    protected $expectedClientType = 'review';

    public function result($review_ref = null)
    {
        return $this->execute(function () use ($review_ref) {
            $payload = $this->input();
            if (empty($payload['review_ref']) || $payload['review_ref'] !== $review_ref) {
                throw new DomainException('审核引用不一致', 40013, 400);
            }
            foreach (['event_id','resource_type','resource_ref','resource_version','status','purchase_gate','member_refs','summary','signature'] as $field) {
                if (!array_key_exists($field, $payload) || $payload[$field] === '') throw new DomainException('缺少必填字段: '.$field,40001,400);
            }
            return (new IdempotencyService())->run('review.result', $this->clientId(), $this->request->header('idempotency-key'), $payload, function () use ($payload, $review_ref) {
                $row = Db::name('shop_professional_review_ref')->where('review_ref', $review_ref)->find();
                if ($row && $row['last_event_id'] === $payload['event_id']) return ['review_ref'=>$review_ref,'status'=>$row['review_status'],'purchase_gate'=>$row['purchase_gate'],'duplicate'=>true];
                $incomingAt=!empty($payload['reviewed_at'])?strtotime($payload['reviewed_at']):time();
                if ($row && (int)$row['reviewed_at'] > $incomingAt) return ['review_ref'=>$review_ref,'status'=>$row['review_status'],'purchase_gate'=>$row['purchase_gate'],'ignored_as_older'=>true];
                $data = [
                    'resource_type' => $payload['resource_type'], 'resource_ref' => $payload['resource_ref'],
                    'resource_version' => $payload['resource_version'], 'member_refs_json' => Json::encode($payload['member_refs']),
                    'review_system' => $this->clientId(), 'review_status' => $payload['status'],
                    'purchase_gate' => $payload['purchase_gate'], 'summary' => $payload['summary'],
                    'result_signature' => $payload['signature'], 'reviewed_at' => $incomingAt,
                    'last_event_id' => $payload['event_id'], 'payload_digest' => hash('sha256', Json::canonical($payload)),
                    'status' => 'normal', 'updatetime' => time(),
                ];
                if ($row) {
                    $data['version'] = (int)$row['version'] + 1;
                    Db::name('shop_professional_review_ref')->where('id', $row['id'])->update($data);
                } else {
                    $data['review_ref'] = $review_ref;
                    $data['version'] = 1;
                    $data['createtime'] = time();
                    Db::name('shop_professional_review_ref')->insert($data);
                }
                $config = get_addon_config('shop');
                if (!empty($config['v5_professional_review_enabled']) && $payload['resource_type'] === 'service_plan') {
                    $plan = Db::name('shop_service_plan')->where('plan_sn', $payload['resource_ref'])->find();
                    if ($plan && (int)$plan['current_version'] === (int)$payload['resource_version']) {
                        $allowed = in_array($payload['status'], ['approved', 'passed'], true) && $payload['purchase_gate'] === 'allowed';
                        Db::name('shop_service_plan')->where('id', $plan['id'])->update([
                            'review_gate_status' => $payload['purchase_gate'],
                            'status' => $allowed && $plan['nutrition_status'] === 'passed' && $plan['trade_status'] === 'passed' ? 'available' : 'blocked',
                            'version' => (int)$plan['version'] + 1, 'updatetime' => time(),
                        ]);
                        Db::name('shop_service_plan_version')->where('plan_id', $plan['id'])->where('version_no', $plan['current_version'])->update([
                            'review_ref' => $review_ref, 'review_gate_status' => $payload['purchase_gate'],
                        ]);
                    }
                }
                return ['review_ref' => $review_ref, 'status' => $payload['status'], 'purchase_gate' => $payload['purchase_gate']];
            });
        }, $this->integrationLog('professional_review_result', 'professional_review', $review_ref));
    }
}
