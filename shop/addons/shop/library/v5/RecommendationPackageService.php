<?php

namespace addons\shop\library\v5;

use think\Db;

class RecommendationPackageService
{
    public function revalidateTrade($packageId)
    {
        $package = Db::name('shop_recommendation_package')->where('id', (int)$packageId)->find();
        if (!$package) {
            throw new DomainException('推荐包不存在', 40402, 404);
        }
        if (in_array($package['status'], ['ordered', 'expired'], true)) {
            throw new DomainException('已下单或已过期推荐包不可重新校验', 40907, 409);
        }
        $version = Db::name('shop_recommendation_package_version')->where('package_id', $package['id'])
            ->where('version_no', $package['current_version'])->find();
        $items = Db::name('shop_recommendation_package_item')->where('package_version_id', $version['id'])->select();
        $issues = [];
        $total = 0;
        foreach ($items as $item) {
            try {
                $sku = (new CatalogService())->getSku($item['sku_id'], false);
                $total += (int)$sku['price_cent'] * (int)$item['quantity'];
            } catch (DomainException $e) {
                $issues[] = ['issue_code' => 'sku_unavailable', 'sku_id' => (string)$item['sku_id'], 'message' => $e->getMessage()];
            }
        }
        $trade = $issues ? 'failed' : 'passed';
        $status = $trade === 'passed' && $package['nutrition_status'] === 'passed' ? 'available' : 'blocked';
        Db::name('shop_recommendation_package')->where('id', $package['id'])->update([
            'trade_status' => $trade, 'status' => $status, 'total_amount_cent' => $total,
            'last_issue_code' => $issues ? $issues[0]['issue_code'] : '',
            'version' => (int)$package['version'] + 1, 'updatetime' => time(),
        ]);
        return ['package_sn' => $package['package_sn'], 'trade_status' => $trade, 'status' => $status, 'issues' => $issues];
    }

    public function create($clientId, array $payload, $requestId)
    {
        $this->requireFields($payload, ['agent_task_id', 'family_ref', 'user_ref', 'menu_version_ref', 'catalog_version', 'nutrition_validation']);
        if (empty($payload['ingredient_requirements']) || !is_array($payload['ingredient_requirements'])) {
            throw new DomainException('ingredient_requirements不能为空', 40004, 400);
        }
        $digest=hash('sha256',Json::canonical($payload));
        $existing=Db::name('shop_recommendation_package')->where('agent_client_id',$clientId)->where('agent_task_id',$payload['agent_task_id'])->find();
        if($existing){if($existing['request_digest']&& !hash_equals($existing['request_digest'],$digest))throw new DomainException('相同Agent任务号对应了不同请求内容',40901,409);return $this->getBySn($existing['package_sn']);}
        $userId = (new IdentityService())->resolveUserId($clientId, $payload['user_ref']);
        $matched = $this->buildItems($payload);
        $nutrition = $payload['nutrition_validation'];
        $nutritionStatus = isset($nutrition['status']) ? $nutrition['status'] : 'pending';
        $tradeStatus = empty($matched['issues']) ? 'passed' : 'failed';
        $status = $nutritionStatus === 'passed' && $tradeStatus === 'passed' ? 'available' : 'blocked';
        $packageSn = Identifiers::make('pkg');
        $now = time();

        Db::startTrans();
        try {
            $packageId = Db::name('shop_recommendation_package')->insertGetId([
                'package_sn'       => $packageSn,
                'agent_client_id'  => $clientId,
                'agent_task_id'    => $payload['agent_task_id'],
                'request_digest'   => $digest,
                'user_id'          => $userId,
                'user_ref'         => $payload['user_ref'],
                'family_ref'       => $payload['family_ref'],
                'current_version'  => 1,
                'menu_version_ref' => $payload['menu_version_ref'],
                'catalog_version'  => $payload['catalog_version'],
                'meal_date'        => !empty($payload['meal_date']) ? $payload['meal_date'] : null,
                'nutrition_status' => $nutritionStatus,
                'trade_status'     => $tradeStatus,
                'confirm_status'   => 'unconfirmed',
                'expires_at'       => !empty($payload['expires_at']) ? strtotime($payload['expires_at']) : $now + 1800,
                'total_amount_cent'=> $matched['total_amount_cent'],
                'currency'         => 'CNY',
                'last_issue_code'  => $matched['issues'] ? $matched['issues'][0]['issue_code'] : '',
                'status'           => $status,
                'version'          => 1,
                'createtime'       => $now,
                'updatetime'       => $now,
            ]);
            $versionId = Db::name('shop_recommendation_package_version')->insertGetId([
                'package_id'                  => $packageId,
                'version_no'                  => 1,
                'base_version_no'             => 0,
                'menu_version_ref'            => $payload['menu_version_ref'],
                'catalog_version'             => $payload['catalog_version'],
                'change_type'                 => 'create',
                'nutrition_validation_id'     => isset($nutrition['validation_id']) ? $nutrition['validation_id'] : '',
                'nutrition_rules_version'     => isset($nutrition['rules_version']) ? $nutrition['rules_version'] : '',
                'nutrition_status'            => $nutritionStatus,
                'nutrition_summary'           => isset($nutrition['summary']) ? $nutrition['summary'] : '',
                'validated_at'                => !empty($nutrition['validated_at']) ? strtotime($nutrition['validated_at']) : $now,
                'trade_status'                => $tradeStatus,
                'trade_checked_at'            => $now,
                'recipes_snapshot_json'       => Json::encode(isset($payload['recipes']) ? $payload['recipes'] : []),
                'requirements_snapshot_json'  => Json::encode($payload['ingredient_requirements']),
                'issues_json'                 => Json::encode($matched['issues']),
                'total_amount_cent'           => $matched['total_amount_cent'],
                'created_by_type'             => 'agent',
                'created_by_ref'              => $clientId,
                'createtime'                  => $now,
            ]);
            $this->insertItems($versionId, $matched['items'], $now);
            (new OutboxService())->append('recommendation.package.created', 'recommendation_package', $packageSn, 1, 'miniapp', [
                'package_sn' => $packageSn,
                'user_ref'   => $payload['user_ref'],
                'status'     => $status,
                'request_id' => $requestId,
            ]);
            Db::commit();
        } catch (\Exception $e) {
            Db::rollback();
            throw $e;
        }
        return $this->getBySn($packageSn);
    }

    public function createSwapVersion($clientId, $packageSn, array $payload, $requestId)
    {
        // Accept the frozen V5 contract names while retaining compatibility with early clients.
        if (empty($payload['menu_version_ref']) && !empty($payload['result_menu_version_ref'])) {
            $payload['menu_version_ref'] = $payload['result_menu_version_ref'];
        }
        if (empty($payload['ingredient_requirements']) && !empty($payload['full_menu_ingredient_requirements'])) {
            $payload['ingredient_requirements'] = $payload['full_menu_ingredient_requirements'];
        }
        $this->requireFields($payload, ['swap_request_id', 'agent_task_id', 'base_version', 'menu_version_ref', 'nutrition_validation', 'ingredient_requirements']);
        $package = Db::name('shop_recommendation_package')->where('package_sn', $packageSn)->find();
        if (!$package || $package['agent_client_id'] !== $clientId) {
            throw new DomainException('推荐包不存在', 40402, 404);
        }
        if ((int)$payload['base_version'] !== (int)$package['current_version']) {
            throw new DomainException('推荐包版本已变化，请刷新后重试', 40906, 409, [
                'resource' => 'recommendation_package',
                'current_version' => (int)$package['current_version'],
                'submitted_version' => (int)$payload['base_version'],
                'retryable' => false,
            ]);
        }
        if ($package['confirm_status'] === 'confirmed' || $package['status'] === 'ordered') {
            throw new DomainException('已确认或已下单的推荐包不可换菜', 40907, 409);
        }
        $matched = $this->buildItems($payload);
        $nutrition = $payload['nutrition_validation'];
        $nutritionStatus = isset($nutrition['status']) ? $nutrition['status'] : 'pending';
        $tradeStatus = empty($matched['issues']) ? 'passed' : 'failed';
        $status = $nutritionStatus === 'passed' && $tradeStatus === 'passed' ? 'available' : 'blocked';
        $newVersion = (int)$package['current_version'] + 1;
        $now = time();

        Db::startTrans();
        try {
            $affected = Db::name('shop_recommendation_package')->where('id', $package['id'])
                ->where('current_version', $package['current_version'])->update([
                    'current_version'  => $newVersion,
                    'menu_version_ref' => $payload['menu_version_ref'],
                    'nutrition_status' => $nutritionStatus,
                    'trade_status'     => $tradeStatus,
                    'total_amount_cent'=> $matched['total_amount_cent'],
                    'last_issue_code'  => $matched['issues'] ? $matched['issues'][0]['issue_code'] : '',
                    'status'           => $status,
                    'version'          => (int)$package['version'] + 1,
                    'updatetime'       => $now,
                ]);
            if (!$affected) {
                throw new DomainException('推荐包版本冲突', 40906, 409);
            }
            $versionId = Db::name('shop_recommendation_package_version')->insertGetId([
                'package_id'                 => $package['id'],
                'version_no'                 => $newVersion,
                'base_version_no'            => $package['current_version'],
                'menu_version_ref'           => $payload['menu_version_ref'],
                'catalog_version'            => isset($payload['catalog_version']) ? $payload['catalog_version'] : (new CatalogService())->currentVersion(),
                'change_type'                => 'dish_swap',
                'nutrition_validation_id'    => isset($nutrition['validation_id']) ? $nutrition['validation_id'] : '',
                'nutrition_rules_version'    => isset($nutrition['rules_version']) ? $nutrition['rules_version'] : '',
                'nutrition_status'           => $nutritionStatus,
                'nutrition_summary'          => isset($nutrition['summary']) ? $nutrition['summary'] : '',
                'validated_at'               => !empty($nutrition['validated_at']) ? strtotime($nutrition['validated_at']) : $now,
                'trade_status'               => $tradeStatus,
                'trade_checked_at'           => $now,
                'recipes_snapshot_json'      => Json::encode(isset($payload['recipes']) ? $payload['recipes'] : []),
                'requirements_snapshot_json' => Json::encode($payload['ingredient_requirements']),
                'issues_json'                => Json::encode($matched['issues']),
                'total_amount_cent'          => $matched['total_amount_cent'],
                'created_by_type'            => 'agent',
                'created_by_ref'             => $clientId,
                'createtime'                 => $now,
            ]);
            $this->insertItems($versionId, $matched['items'], $now);
            Db::name('shop_recommendation_swap')->insert([
                'swap_request_id'        => $payload['swap_request_id'],
                'agent_task_id'          => $payload['agent_task_id'],
                'package_id'             => $package['id'],
                'base_version_no'        => $package['current_version'],
                'result_version_no'      => $newVersion,
                'base_menu_version_ref'  => $package['menu_version_ref'],
                'result_menu_version_ref'=> $payload['menu_version_ref'],
                'swap_type'              => isset($payload['swap_type']) ? $payload['swap_type'] : 'recipe',
                'change_reason'          => isset($payload['change_reason']) ? $payload['change_reason'] : '',
                'old_recipe_ref'         => isset($payload['old_recipe_ref']) ? $payload['old_recipe_ref'] : '',
                'new_recipe_ref'         => isset($payload['new_recipe_ref']) ? $payload['new_recipe_ref'] : '',
                'ingredient_changes_json'=> Json::encode(isset($payload['ingredient_changes']) ? $payload['ingredient_changes'] : []),
                'nutrition_validation_id'=> isset($nutrition['validation_id']) ? $nutrition['validation_id'] : '',
                'nutrition_status'       => $nutritionStatus,
                'trade_status'           => $tradeStatus,
                'user_id'                => $package['user_id'],
                'status'                 => $status === 'available' ? 'completed' : 'blocked',
                'createtime'             => $now,
                'updatetime'             => $now,
            ]);
            (new OutboxService())->append('recommendation.package.version.created', 'recommendation_package', $packageSn, $newVersion, 'miniapp', [
                'package_sn' => $packageSn, 'version' => $newVersion, 'request_id' => $requestId,
            ]);
            Db::commit();
        } catch (\Exception $e) {
            Db::rollback();
            throw $e;
        }
        return $this->getBySn($packageSn);
    }

    public function getBySn($packageSn, $userId = null)
    {
        $package = Db::name('shop_recommendation_package')->where('package_sn', $packageSn)->find();
        if (!$package) {
            throw new DomainException('推荐包不存在', 40402, 404);
        }
        if ($userId !== null) {
            (new IdentityService())->assertOwner($userId, $package['user_id']);
        }
        $version = Db::name('shop_recommendation_package_version')->where('package_id', $package['id'])
            ->where('version_no', $package['current_version'])->find();
        $items = Db::name('shop_recommendation_package_item')->where('package_version_id', $version['id'])->order('sort', 'asc')->select();
        foreach ($items as &$item) {
            $item['product_snapshot'] = Json::decode($item['product_snapshot_json'], []);
            unset($item['product_snapshot_json']);
        }
        return [
            'package_sn' => $package['package_sn'],
            'package_version' => (int)$package['current_version'],
            'status' => $package['status'],
            'nutrition_validation_status' => $package['nutrition_status'],
            'trade_validation_status' => $package['trade_status'],
            'confirm_status' => $package['confirm_status'],
            'items' => $items,
            'total_amount_cent' => (int)$package['total_amount_cent'],
            'trade_issues' => Json::decode($version['issues_json'], []),
            'expires_at' => date(DATE_ATOM, (int)$package['expires_at']),
        ];
    }

    protected function buildItems(array $payload)
    {
        $matcher = new ProductMatchService();
        $items = [];
        $issues = [];
        if (!empty($payload['items'])) {
            foreach ($payload['items'] as $item) {
                $result = $matcher->validateSubmittedItem($item);
                if ($result['issue']) {
                    $issues[] = $result['issue'];
                } else {
                    $items[] = $result['selected'];
                }
            }
        } else {
            foreach ($payload['ingredient_requirements'] as $requirement) {
                $result = $matcher->matchRequirement($requirement);
                if ($result['issue']) {
                    if (empty($requirement['is_optional'])) {
                        $issues[] = $result['issue'];
                    }
                } else {
                    $items[] = $result['selected'];
                }
            }
        }
        $total = 0;
        foreach ($items as $item) {
            $total += (int)$item['total_price_cent'];
        }
        return ['items' => $items, 'issues' => $issues, 'total_amount_cent' => $total];
    }

    protected function insertItems($versionId, array $items, $now)
    {
        foreach ($items as $index => $item) {
            $snapshot = $item['product_snapshot'];
            Db::name('shop_recommendation_package_item')->insert([
                'package_version_id' => $versionId,
                'goods_id'           => (int)$snapshot['product_id'],
                'sku_id'             => (int)$item['sku_id'],
                'ingredient_id'      => (int)$item['ingredient_id'],
                'quantity'           => (int)$item['quantity'],
                'planned_value'      => isset($item['covered_value']) ? $item['covered_value'] : 0,
                'planned_unit'       => isset($item['covered_unit']) ? $item['covered_unit'] : '',
                'unit_price_cent'    => (int)$item['unit_price_cent'],
                'line_amount_cent'   => (int)$item['total_price_cent'],
                'product_snapshot_json' => Json::encode($snapshot),
                'sort'               => $index,
                'createtime'         => $now,
            ]);
        }
    }

    protected function requireFields(array $payload, array $fields)
    {
        foreach ($fields as $field) {
            if (!array_key_exists($field, $payload) || $payload[$field] === '' || $payload[$field] === null) {
                throw new DomainException('缺少必填字段: ' . $field, 40001, 400, ['field' => $field]);
            }
        }
    }
}
