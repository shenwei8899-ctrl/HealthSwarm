<?php

namespace addons\shop\library\v5;

use think\Db;

class ServicePlanService
{
    public function revalidateTrade($planSn, $userId = null)
    {
        $plan=Db::name('shop_service_plan')->where('plan_sn',$planSn)->find();
        if(!$plan)throw new DomainException('专属计划不存在',40404,404);
        if($userId!==null)(new IdentityService())->assertOwner($userId,$plan['user_id']);
        $version=Db::name('shop_service_plan_version')->where('plan_id',$plan['id'])->where('version_no',$plan['current_version'])->find();
        $draft=Json::decode($version['pricing_draft_json'],[]);$issues=[];$total=0;
        foreach((array)(isset($draft['days'])?$draft['days']:[]) as $day){foreach((array)$day['items'] as $item){try{$sku=(new CatalogService())->getSku($item['sku_id'],false);$total+=(int)$sku['price_cent']*max(1,(int)$item['quantity']);}catch(DomainException $e){$issues[]=['issue_code'=>'sku_unavailable','sku_id'=>(string)$item['sku_id'],'day_no'=>$day['day_no'],'message'=>$e->getMessage(),'requires_agent_revalidation'=>true];}}}
        $trade=$issues?'failed':'passed';$reviewAllowed=$plan['review_gate_status']==='not_required'||$plan['review_gate_status']==='allowed';
        $status=$trade==='passed'&&$plan['nutrition_status']==='passed'&&$reviewAllowed?'available':'blocked';
        if(!Db::name('shop_service_plan_order')->where('plan_id',$plan['id'])->where('status','in',['active','paused','exception_handling','completed'])->find())Db::name('shop_service_plan')->where('id',$plan['id'])->update(['trade_status'=>$trade,'estimated_amount_cent'=>$total,'status'=>$status,'version'=>(int)$plan['version']+1,'updatetime'=>time()]);
        return ['plan_sn'=>$planSn,'plan_version'=>(int)$plan['current_version'],'trade_validation_status'=>$trade,'status'=>$status,'estimated_amount_cent'=>$total,'issues'=>$issues];
    }

    public function create($clientId, array $payload, $requestId)
    {
        $this->validatePayload($payload);
        $digest=hash('sha256',Json::canonical($payload));
        $existing=Db::name('shop_service_plan')->where('agent_client_id',$clientId)->where('agent_task_id',$payload['agent_task_id'])->find();
        if($existing){if($existing['request_digest']&&!hash_equals($existing['request_digest'],$digest))throw new DomainException('相同Agent任务号对应了不同请求内容',40901,409);return $this->getBySn($existing['plan_sn']);}
        $userId = (new IdentityService())->resolveUserId($clientId, $payload['user_ref']);
        $draft = $this->buildTradeDraft($payload['days']);
        $nutrition = $payload['nutrition_validation'];
        $nutritionStatus = isset($nutrition['status']) ? $nutrition['status'] : 'pending';
        $config = get_addon_config('shop');
        $requiresReview = !empty($config['v5_professional_review_enabled']) && !empty($payload['requires_professional_review']);
        $reviewGate = $requiresReview ? 'pending' : 'not_required';
        $tradeStatus = empty($draft['issues']) ? 'passed' : 'failed';
        $status = $nutritionStatus === 'passed' && $tradeStatus === 'passed' && !$requiresReview ? 'available' : 'blocked';
        $planSn = Identifiers::make('plan');
        $now = time();

        Db::startTrans();
        try {
            $planId = Db::name('shop_service_plan')->insertGetId([
                'plan_sn' => $planSn, 'agent_client_id' => $clientId, 'agent_task_id' => $payload['agent_task_id'],
                'request_digest' => $digest,
                'user_id' => $userId, 'user_ref' => $payload['user_ref'], 'family_ref' => $payload['family_ref'],
                'plan_name' => $payload['plan_name'], 'plan_days' => 21, 'delivery_frequency' => 'daily',
                'delivery_lead_days' => 1, 'current_version' => 1,
                'requires_professional_review' => $requiresReview ? 1 : 0,
                'review_gate_status' => $reviewGate, 'nutrition_status' => $nutritionStatus,
                'trade_status' => $tradeStatus, 'estimated_amount_cent' => $draft['total_amount_cent'],
                'currency' => 'CNY', 'status' => $status, 'version' => 1,
                'createtime' => $now, 'updatetime' => $now,
            ]);
            $versionId = $this->insertVersion($planId, 1, 0, $payload, $draft, $reviewGate, $now);
            $this->insertDays($versionId, $payload['days'], $now);
            foreach ($payload['member_refs'] as $index => $memberRef) {
                Db::name('shop_service_plan_member')->insert([
                    'plan_id' => $planId, 'member_ref' => $memberRef,
                    'profile_version_ref' => isset($payload['profile_version_refs'][$index]) ? $payload['profile_version_refs'][$index] : '',
                    'role' => $index === 0 ? 'primary' : 'member', 'display_alias' => '',
                    'status' => 'normal', 'createtime' => $now, 'updatetime' => $now,
                ]);
            }
            (new OutboxService())->append('service_plan.created', 'service_plan', $planSn, 1, 'miniapp', [
                'plan_sn' => $planSn, 'user_ref' => $payload['user_ref'], 'status' => $status, 'request_id' => $requestId,
            ]);
            Db::commit();
        } catch (\Exception $e) {
            Db::rollback();
            throw $e;
        }
        return $this->getBySn($planSn);
    }

    public function createVersion($clientId, $planSn, array $payload, $requestId)
    {
        $this->validatePayload($payload, true);
        Db::startTrans();
        try {
            $plan = Db::name('shop_service_plan')->where('plan_sn', $planSn)->lock(true)->find();
            if (!$plan || $plan['agent_client_id'] !== $clientId) {
                throw new DomainException('专属计划不存在', 40404, 404);
            }
            if ((int)$payload['base_version'] !== (int)$plan['current_version']) {
                throw new DomainException('专属计划版本冲突', 40906, 409, ['current_version' => (int)$plan['current_version']]);
            }
            $paid = Db::name('shop_service_plan_order')->where('plan_id', $plan['id'])
                ->where('status', 'in', ['active', 'paused', 'exception_handling', 'completed'])->find();
            if ($paid) {
                throw new DomainException('已支付计划内容不可修改', 40913, 409);
            }
            $draft = $this->buildTradeDraft($payload['days']);
            $nutrition = $payload['nutrition_validation'];
            $nutritionStatus = isset($nutrition['status']) ? $nutrition['status'] : 'pending';
            $config = get_addon_config('shop');
            $requiresReview = !empty($config['v5_professional_review_enabled']) && !empty($payload['requires_professional_review']);
            $reviewGate = $requiresReview ? 'pending' : 'not_required';
            $tradeStatus = empty($draft['issues']) ? 'passed' : 'failed';
            $status = $nutritionStatus === 'passed' && $tradeStatus === 'passed' && $reviewGate === 'not_required' ? 'available' : 'blocked';
            $newVersion = (int)$plan['current_version'] + 1;
            $affected = Db::name('shop_service_plan')->where('id', $plan['id'])->where('current_version', $plan['current_version'])->update([
                'current_version' => $newVersion, 'plan_name' => $payload['plan_name'],
                'requires_professional_review' => $requiresReview ? 1 : 0,
                'review_gate_status' => $reviewGate, 'nutrition_status' => $nutritionStatus,
                'trade_status' => $tradeStatus, 'estimated_amount_cent' => $draft['total_amount_cent'],
                'status' => $status, 'version' => (int)$plan['version'] + 1, 'updatetime' => time(),
            ]);
            if (!$affected) {
                throw new DomainException('专属计划版本冲突', 40906, 409);
            }
            $versionId = $this->insertVersion($plan['id'], $newVersion, $plan['current_version'], $payload, $draft, $reviewGate, time());
            $this->insertDays($versionId, $payload['days'], time());
            (new OutboxService())->append('service_plan.version.created', 'service_plan', $planSn, $newVersion, 'miniapp', [
                'plan_sn' => $planSn, 'version' => $newVersion, 'request_id' => $requestId,
            ]);
            Db::commit();
        } catch (\Exception $e) {
            Db::rollback();
            throw $e;
        }
        return $this->getBySn($planSn);
    }

    public function getBySn($planSn, $userId = null)
    {
        $plan = Db::name('shop_service_plan')->where('plan_sn', $planSn)->find();
        if (!$plan) {
            throw new DomainException('专属计划不存在', 40404, 404);
        }
        if ($userId !== null) {
            (new IdentityService())->assertOwner($userId, $plan['user_id']);
        }
        $version = Db::name('shop_service_plan_version')->where('plan_id', $plan['id'])
            ->where('version_no', $plan['current_version'])->find();
        $days = Db::name('shop_service_plan_day')->where('plan_version_id', $version['id'])->order('day_no', 'asc')->select();
        foreach ($days as &$day) {
            $day['ingredient_requirements'] = Json::decode($day['ingredient_requirements_json'], []);
            $day['meals'] = Db::name('shop_service_plan_meal')->where('plan_day_id', $day['id'])->order('sort', 'asc')->select();
            foreach ($day['meals'] as &$meal) {
                $meal['ingredient_requirements'] = Json::decode($meal['ingredient_requirements_json'], []);
                $meal['recipe_snapshot'] = Json::decode($meal['recipe_snapshot_json'], []);
                unset($meal['ingredient_requirements_json'], $meal['recipe_snapshot_json']);
            }
            unset($day['ingredient_requirements_json']);
        }
        return [
            'plan_sn' => $plan['plan_sn'], 'plan_name' => $plan['plan_name'],
            'plan_version' => (int)$plan['current_version'], 'plan_days' => 21,
            'delivery_frequency' => 'daily', 'delivery_lead_days' => 1,
            'status' => $plan['status'], 'nutrition_validation_status' => $plan['nutrition_status'],
            'trade_validation_status' => $plan['trade_status'],
            'professional_review_status' => $plan['requires_professional_review'] ? $plan['review_gate_status'] : 'not_required',
            'purchase_gate' => $plan['requires_professional_review'] ? $plan['review_gate_status'] : 'allowed',
            'estimated_amount_cent' => (int)$plan['estimated_amount_cent'],
            'trade_draft' => Json::decode($version['pricing_draft_json'], []),
            'days' => $days,
        ];
    }

    public function policy()
    {
        $policy = Db::name('shop_policy_version')->where('policy_type', 'plan_non_refund')
            ->where('status', 'active')->where('effective_at', '<=', time())->order('effective_at', 'desc')->find();
        if (!$policy) {
            throw new DomainException('专属计划交易政策尚未配置', 50301, 503);
        }
        return [
            'policy_version' => $policy['policy_version'], 'title' => $policy['title'],
            'content' => $policy['content'], 'content_hash' => $policy['content_hash'],
            'confirmation_required' => true,
        ];
    }

    protected function validatePayload(array $payload, $isVersion = false)
    {
        $fields = ['agent_task_id', 'family_ref', 'user_ref', 'member_refs', 'profile_version_refs', 'plan_name', 'plan_days', 'delivery_frequency', 'days', 'nutrition_validation'];
        if ($isVersion) {
            $fields[] = 'base_version';
            $fields[] = 'change_reason';
        }
        foreach ($fields as $field) {
            if (!array_key_exists($field, $payload) || $payload[$field] === '' || $payload[$field] === null) {
                throw new DomainException('缺少必填字段: ' . $field, 40001, 400, ['field' => $field]);
            }
        }
        if ((int)$payload['plan_days'] !== 21 || $payload['delivery_frequency'] !== 'daily') {
            throw new DomainException('一期专属计划必须为21天且每日配送', 40006, 400);
        }
        if (!is_array($payload['days']) || count($payload['days']) !== 21) {
            throw new DomainException('专属计划必须包含完整21天菜单', 40007, 400);
        }
        $dayNos = [];
        foreach ($payload['days'] as $day) {
            $dayNo = isset($day['day_no']) ? (int)$day['day_no'] : 0;
            $dayNos[] = $dayNo;
            if (empty($day['meals']) || !is_array($day['meals'])) {
                throw new DomainException('每天至少需要一个餐次', 40008, 400, ['day_no' => $dayNo]);
            }
        }
        sort($dayNos);
        if ($dayNos !== range(1, 21)) {
            throw new DomainException('计划天序必须为1至21且不可重复', 40009, 400);
        }
        $config = get_addon_config('shop');
        if (!empty($config['v5_professional_review_enabled']) && !empty($payload['requires_professional_review']) && empty($payload['professional_review_ref'])) {
            throw new DomainException('启用专业审核时必须提供审核引用', 40010, 400);
        }
    }

    protected function buildTradeDraft(array $days)
    {
        $matcher = new ProductMatchService();
        $total = 0;
        $issues = [];
        $dayDrafts = [];
        foreach ($days as $day) {
            $dayItems = [];
            foreach ($day['meals'] as $meal) {
                foreach ((array)(isset($meal['ingredient_requirements']) ? $meal['ingredient_requirements'] : []) as $requirement) {
                    $requirement['recipe_ref'] = isset($meal['recipe_ref']) ? $meal['recipe_ref'] : '';
                    $result = $matcher->matchRequirement($requirement);
                    if ($result['issue']) {
                        if (empty($requirement['is_optional'])) {
                            $issue = $result['issue'];
                            $issue['day_no'] = (int)$day['day_no'];
                            $issues[] = $issue;
                        }
                    } else {
                        $item = $result['selected'];
                        $item['recipe_ref'] = $requirement['recipe_ref'];
                        $dayItems[] = $item;
                        $total += (int)$item['total_price_cent'];
                    }
                }
            }
            $dayDrafts[] = ['day_no' => (int)$day['day_no'], 'items' => $dayItems];
        }
        return ['days' => $dayDrafts, 'issues' => $issues, 'total_amount_cent' => $total];
    }

    protected function insertVersion($planId, $versionNo, $baseVersion, array $payload, array $draft, $reviewGate, $now)
    {
        $nutrition = $payload['nutrition_validation'];
        return Db::name('shop_service_plan_version')->insertGetId([
            'plan_id' => $planId, 'version_no' => $versionNo, 'base_version_no' => $baseVersion,
            'profile_version_refs_json' => Json::encode($payload['profile_version_refs']),
            'catalog_version' => isset($payload['catalog_version']) ? $payload['catalog_version'] : (new CatalogService())->currentVersion(),
            'change_reason' => isset($payload['change_reason']) ? $payload['change_reason'] : 'create',
            'nutrition_validation_id' => isset($nutrition['validation_id']) ? $nutrition['validation_id'] : '',
            'nutrition_rules_version' => isset($nutrition['rules_version']) ? $nutrition['rules_version'] : '',
            'nutrition_status' => isset($nutrition['status']) ? $nutrition['status'] : 'pending',
            'nutrition_summary' => isset($nutrition['summary']) ? $nutrition['summary'] : '',
            'review_ref' => isset($payload['professional_review_ref']) ? $payload['professional_review_ref'] : '',
            'review_gate_status' => $reviewGate,
            'trade_status' => empty($draft['issues']) ? 'passed' : 'failed',
            'pricing_draft_json' => Json::encode($draft), 'createtime' => $now,
        ]);
    }

    protected function insertDays($versionId, array $days, $now)
    {
        foreach ($days as $day) {
            $requirements = [];
            foreach ($day['meals'] as $meal) {
                $requirements = array_merge($requirements, isset($meal['ingredient_requirements']) ? $meal['ingredient_requirements'] : []);
            }
            $dayId = Db::name('shop_service_plan_day')->insertGetId([
                'plan_version_id' => $versionId, 'day_no' => (int)$day['day_no'],
                'relative_date_offset' => (int)$day['day_no'] - 1,
                'display_title' => isset($day['display_title']) ? $day['display_title'] : '第' . (int)$day['day_no'] . '天',
                'daily_summary' => isset($day['daily_summary']) ? $day['daily_summary'] : '',
                'ingredient_requirements_json' => Json::encode($requirements), 'createtime' => $now,
            ]);
            foreach ($day['meals'] as $sort => $meal) {
                Db::name('shop_service_plan_meal')->insert([
                    'plan_day_id' => $dayId, 'meal_type' => $meal['meal_type'], 'sort' => $sort,
                    'recipe_ref' => $meal['recipe_ref'],
                    'recipe_version_ref' => isset($meal['recipe_version_ref']) ? $meal['recipe_version_ref'] : '',
                    'recipe_name' => isset($meal['recipe_name']) ? $meal['recipe_name'] : '',
                    'recipe_summary' => isset($meal['summary']) ? $meal['summary'] : '',
                    'recipe_snapshot_json' => Json::encode($meal),
                    'ingredient_requirements_json' => Json::encode(isset($meal['ingredient_requirements']) ? $meal['ingredient_requirements'] : []),
                    'mapped_bundle_sku_id' => isset($meal['mapped_bundle_sku_id']) ? (int)$meal['mapped_bundle_sku_id'] : 0,
                    'mapping_status' => !empty($meal['mapped_bundle_sku_id']) ? 'mapped' : 'dynamic',
                    'createtime' => $now,
                ]);
            }
        }
    }
}
