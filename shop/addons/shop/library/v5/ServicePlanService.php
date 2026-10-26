<?php

namespace addons\shop\library\v5;

use think\Db;

class ServicePlanService
{
    /** 重匹配未购买报价，菜单与购买时快照不变。 */
    public function revalidateTrade($planSn, $userId = null, $selectedVersion = null)
    {
        Db::startTrans();
        try {
            $plan=Db::name('shop_service_plan')->where('plan_sn',$planSn)->lock(true)->find();
            if (!$plan) throw new DomainException('专属计划不存在',40404,404);
            if ($userId!==null) (new IdentityService())->assertOwner($userId,$plan['user_id']);
            if ($selectedVersion!==null && (int)$selectedVersion!==(int)$plan['current_version']) throw new DomainException('计划已更新，请重新查看',40906,409);
            $version=Db::name('shop_service_plan_version')->where('plan_id',$plan['id'])->where('version_no',$plan['current_version'])->find();
            $payload=Json::decode($version['source_payload_json'],[]);
            $this->validatePayload($payload,(int)$plan['current_version']>1);
            $draft=$this->buildTradeDraft($payload['days'],$plan['tier_code'],$plan['tier_policy_version']);
            $this->checkBudget($payload,$draft);
            $trade=empty($draft['issues'])?'passed':'failed';
            $status=$trade==='passed' && $plan['nutrition_status']==='passed' && in_array($plan['review_gate_status'],['not_required','allowed'],true)?'available':'blocked';
            if ($plan['status']==='ordered') $status='ordered';
            Db::name('shop_service_plan_version')->where('id',$version['id'])->update(['pricing_draft_json'=>Json::encode($draft),'trade_status'=>$trade]);
            Db::name('shop_service_plan')->where('id',$plan['id'])->update(['trade_status'=>$trade,'status'=>$status,'estimated_amount_cent'=>$draft['total_amount_cent'],
                'estimate_valid_until'=>time()+(new PlanPolicyService())->current($plan['tier_policy_version'])['config']['estimate_ttl_seconds'],'version'=>(int)$plan['version']+1,'updatetime'=>time()]);
            Db::commit();
            return $this->getBySn($planSn,$userId);
        } catch (\Throwable $error) {Db::rollback();throw $error;}
    }

    protected function checkBudget(array $payload, array &$draft)
    {
        if ($draft['issues']) return;
        $policy=(new PlanPolicyService())->current($payload['tier_policy_version']);
        try {PlanPolicyService::assertBudget($policy['config']['tiers'][$payload['tier_code']],count($payload['member_refs']),$draft['total_amount_cent'],$policy['config']['service_fee_cent']);}
        catch (DomainException $error) {$draft['issues'][]=['issue_code'=>'tier_budget','message'=>$error->getMessage(),'blocking'=>true];}
    }

    public function create($clientId, array $payload, $requestId)
    {
        $this->validatePayload($payload);
        $digest=hash('sha256',Json::canonical($payload));
        $existing=Db::name('shop_service_plan')->where('agent_client_id',$clientId)->where('agent_task_id',$payload['agent_task_id'])->find();
        if($existing){if($existing['request_digest']&&!hash_equals($existing['request_digest'],$digest))throw new DomainException('相同Agent任务号对应了不同请求内容',40901,409);return $this->getBySn($existing['plan_sn']);}
        $userId = (new IdentityService())->resolveUserId($clientId, $payload['user_ref']);
        $draft = $this->buildTradeDraft($payload['days'], $payload['tier_code'], $payload['tier_policy_version']);
        $this->checkBudget($payload,$draft);
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
                'recommendation_group_ref'=>$payload['recommendation_group_ref'], 'tier_code'=>$payload['tier_code'],
                'tier_policy_version'=>$payload['tier_policy_version'], 'basis_hash'=>$payload['basis_hash'],
                'display_json'=>Json::encode($payload['display'] ?? []),
                'estimate_valid_until'=>time()+(new PlanPolicyService())->current($payload['tier_policy_version'])['config']['estimate_ttl_seconds'],
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
                    'role' => $index === 0 ? 'primary' : 'member', 'display_alias' => mb_substr((string)($payload['member_aliases'][$memberRef] ?? ''),0,64),
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
            foreach (['recommendation_group_ref','tier_code','tier_policy_version','basis_hash','user_ref','family_ref'] as $field) {
                if ($plan[$field]!==$payload[$field]) throw new DomainException('新档案或推荐组必须建立独立计划',40906,409);
            }
            if ((int)$payload['base_version'] !== (int)$plan['current_version']) {
                throw new DomainException('专属计划版本冲突', 40906, 409, ['current_version' => (int)$plan['current_version']]);
            }
            $paid = Db::name('shop_service_plan_order')->where('plan_id', $plan['id'])
                ->where('status', 'in', ['active', 'paused', 'exception_handling', 'completed'])->find();
            if ($paid) {
                throw new DomainException('已支付计划内容不可修改', 40913, 409);
            }
            $draft = $this->buildTradeDraft($payload['days'], $payload['tier_code'], $payload['tier_policy_version']);
        $this->checkBudget($payload,$draft);
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
        if ($userId !== null) {
            (new AgentMealSourceService())->validateProof(Json::decode($version['agent_source_proof_json'] ?? '{}', []));
        }
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
        $draft=Json::decode($version['pricing_draft_json'], []);
        $first=0;foreach ($draft['days'][0]['items'] ?? [] as $item) $first+=(int)$item['total_price_cent'];
        $members=Db::name('shop_service_plan_member')->where('plan_id',$plan['id'])->field('member_ref,profile_version_ref,display_alias')->select();
        $policy=(new PlanPolicyService())->current($plan['tier_policy_version']);
        return [
            'recommendation_group_ref'=>$plan['recommendation_group_ref'],'tier_code'=>$plan['tier_code'],
            'tier_name'=>PlanPolicyService::TIERS[$plan['tier_code']], 'tier_policy_version'=>$plan['tier_policy_version'],
            'members'=>$members,'display'=>Json::decode($plan['display_json'],[]),
            'difference'=>$policy['config']['tiers'][$plan['tier_code']]['difference'],
            'first_batch_goods_cent'=>$plan['trade_status']==='passed' && (int)$plan['estimate_valid_until']>time() ? $first : null, 'estimated_goods_cent'=>(int)$plan['estimated_amount_cent'],
            'service_fee_cent'=>$policy['config']['service_fee_cent'],'shipping_fee_cent'=>null,
            'estimated_total_cent'=>null,
            'estimated_subtotal_cent'=>$plan['trade_status']==='passed' && (int)$plan['estimate_valid_until']>time() ? (int)$plan['estimated_amount_cent']+$policy['config']['service_fee_cent'] : null,
            'estimate_includes_shipping'=>false, 'estimate_valid_until'=>(int)$plan['estimate_valid_until'],
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
        $policy=(new PlanPolicyService())->current();
        return ['policy_version'=>$policy['version'],'content_hash'=>$policy['hash'],
            'confirmation_required'=>false,'cancel_remaining_allowed'=>true,
            'summary'=>'可取消尚未截单或备货的剩余批次，退款金额以实时预览为准'];
    }

    protected function validatePayload(array $payload, $isVersion = false)
    {
        PlanRequirements::validate($payload);
        $policy=(new PlanPolicyService())->current();
        if ($policy['version']!==$payload['tier_policy_version']) throw new DomainException('计划规则已更新',40906,409);
        PlanRequirements::validateTier($payload,$policy);
        $source=Json::decode($payload['agent_source_proof']['payload'] ?? '',[]);
        if (($source['content_hash'] ?? '')!==PlanRequirements::contentHash($payload) || ($source['kind'] ?? '')!=='service_plan') throw new DomainException('计划内容与校验凭据不一致',40301,403);
        if ((int)($source['plan_version'] ?? 0)!==($isVersion?(int)($payload['base_version'] ?? 0)+1:1)) throw new DomainException('计划版本与来源凭据不一致',40906,409);
        (new AgentMealSourceService())->validateProof($payload['agent_source_proof']);
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

    protected function buildTradeDraft(array $days, $tierCode, $policyVersion)
    {
        $policy=(new PlanPolicyService())->current($policyVersion);
        $allowed=$policy['config']['tiers'][$tierCode]['allowed_sku_ids'];
        $total=0;$issues=[];$drafts=[];
        foreach ($days as $day) {
            $matched=PlanRequirements::matchBatch($day['meals'],array_values(array_intersect($allowed,$day['eligible_sku_ids'])));
            foreach ($matched['issues'] as $issue) $issues[]=$issue+['day_no'=>(int)$day['day_no'],'blocking'=>true];
            foreach ($matched['items'] as $item) $total+=(int)$item['total_price_cent'];
            $drafts[]=['day_no'=>(int)$day['day_no'],'items'=>$matched['items'],'requirements'=>$matched['requirements']];
        }
        return ['days'=>$drafts,'issues'=>$issues,'total_amount_cent'=>$total];
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
            'pricing_draft_json' => Json::encode($draft), 'agent_source_proof_json'=>Json::encode($payload['agent_source_proof']), 'createtime' => $now,
            'source_payload_json'=>Json::encode($payload),
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
