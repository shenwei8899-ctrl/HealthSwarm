<?php

namespace addons\shop\library\v5;

use think\Db;

/** Agent 来源由后端保存并回源核对，客户端不可替换。 */
class AgentMealSourceService
{
    public function assertSource($userId, $type, $ref, $version)
    {
        $client = trim((string)getenv('SHOP_AGENT_CLIENT_ID'));
        $linked = $client !== '' && Db::name('shop_external_identity')->where([
            'client_id' => $client, 'user_id' => (int)$userId, 'status' => 'normal',
        ])->find();
        if ($type === 'purchase_list') {
            $list = Db::name('shop_purchase_list')->where('purchase_list_sn', $ref)->find();
            if (!$list) throw new DomainException('采购清单不存在', 40403, 404);
            (new IdentityService())->assertOwner($userId, $list['user_id']);
            if ((int)$list['current_version'] !== (int)$version || (int)$list['expires_at'] <= time() ||
                !in_array($list['status'], ['ready', 'confirmed'], true)) {
                throw new DomainException('采购清单已变化或过期', 40906, 409);
            }
            return $this->assertSource($userId, $list['source_type'], $list['source_ref'], $list['source_version']);
        }
        if ($type !== 'recommendation_package') {
            if ($linked) throw new DomainException('请从本餐、汇总采购或对话食材包继续购买', 40301, 403);
            return;
        }
        $row = Db::name('shop_recommendation_package')->where('package_sn', $ref)->find();
        if (!$row) throw new DomainException('推荐包不存在', 40402, 404);
        (new IdentityService())->assertOwner($userId, $row['user_id']);
        if ((int)$row['current_version'] !== (int)$version || (int)$row['expires_at'] <= time() ||
            !in_array($row['status'], ['available', 'confirmed'], true)) {
            throw new DomainException('餐单采购来源已变化或过期', 40906, 409);
        }
        if ($row['nutrition_status'] !== 'passed' || $row['trade_status'] !== 'passed') throw new DomainException('餐单采购尚未通过校验',40908,409);
        $v=Db::name('shop_recommendation_package_version')->where('package_id',$row['id'])->where('version_no',$version)->find();
        if (!$v) throw new DomainException('餐单采购版本不存在，请重新核对',40906,409);
        foreach (Db::name('shop_recommendation_package_item')->where('package_version_id',$v['id']??0)->select() as $item) {
            // Checkout performs stock validation while accounting for its own reservation.
            // Here only verify the provenance mapping, including when all stock is reserved.
            $sku=(new CatalogService())->getSku($item['sku_id'],true);
            // Submitted SKU items can carry ingredient_id=0; their saved composition is still binding.
            $saved = Json::decode($item['product_snapshot_json'] ?? '{}', []);
            $savedMappings = $saved['ingredients'] ?? [];
            $beforeCodes = array_values(array_unique(array_column($savedMappings, 'ingredient_code')));
            $currentCodes = array_values(array_unique(array_column($sku['ingredients'], 'ingredient_code')));
            $beforeAllergens = $saved['allergen_codes'] ?? [];
            $currentAllergens = $sku['allergen_codes'] ?? [];
            sort($beforeCodes); sort($currentCodes); sort($beforeAllergens); sort($currentAllergens);
            $compositionIncomplete = in_array('component_mapping_unapproved', array_column($sku['data_issues'] ?? [], 'code'), true);
            $packChanged = isset($saved['net_content']) && (
                $saved['net_content']['unit'] !== $sku['net_content']['unit'] ||
                (float)$saved['net_content']['value'] !== (float)$sku['net_content']['value']);
            if ($beforeCodes !== $currentCodes || $beforeAllergens !== $currentAllergens || $compositionIncomplete || $packChanged) {
                throw new DomainException('餐单商品配料、过敏原或包装已变化，请重新核对',40946,409);
            }
            if (!$savedMappings && empty($item['ingredient_id'])) throw new DomainException('餐单商品缺少食材来源，请重新核对',40946,409);
            foreach ($savedMappings as $before) {
                $current = null;
                foreach ($sku['ingredients'] as $candidate) {
                    if ($candidate['ingredient_code'] === $before['ingredient_code']) { $current = $candidate; break; }
                }
                if (!$current || $current['net_unit'] !== $before['net_unit']) throw new DomainException('餐单商品食材关联已失效或未审核，请重新核对',40946,409);
                foreach (['net_value','convert_ratio','loss_rate'] as $field) {
                    if ((float)$current[$field] !== (float)$before[$field]) throw new DomainException('餐单商品食材换算已变化，请重新核对',40946,409);
                }
            }
            if (empty($item['ingredient_id'])) continue;
            $ingredientCode=Db::name('shop_ingredient')->where('id',$item['ingredient_id'])->value('ingredient_code');
            $approved=false;
            foreach ($sku['ingredients'] as $map) if ($map['ingredient_code'] === $ingredientCode) $approved=true;
            if (!$approved) throw new DomainException('餐单商品食材关联已失效或未审核，请重新核对',40946,409);
        }
        $proof = Json::decode($row['agent_source_proof_json'] ?? '{}', []);
        $source = Json::decode($proof['payload'] ?? '{}', []);
        if ($linked && (!$proof || $row['agent_client_id'] !== $client ||
            !in_array($source['kind'] ?? '', ['daily_arrangement', 'conversation_package'], true))) {
            throw new DomainException('请从有效餐单或对话食材包继续购买', 40301, 403);
        }
        if (!$proof) return; // Unrelated legacy consumers retain their contract.
        (new IdentityService())->assertOwner($userId, (new IdentityService())->resolveUserId($row['agent_client_id'], $row['user_ref']));
        $sessionUrl = trim((string)getenv('SHOP_AGENT_SESSION_URL'));
        $parts = parse_url($sessionUrl);
        $hosts = ['localhost', '127.0.0.1'];
        if (getenv('SHOP_AGENT_ALLOW_DOCKER_HOST') === '1') $hosts[] = 'host.docker.internal';
        if (!$parts || !empty($parts['user']) || !empty($parts['pass']) || !empty($parts['query']) ||
            !empty($parts['fragment']) || !preg_match('~/api/auth/wechat/session$~D', $sessionUrl) ||
            (($parts['scheme'] ?? '') !== 'https' && !(($parts['scheme'] ?? '') === 'http' && in_array($parts['host'] ?? '', $hosts, true)))) {
            throw new DomainException('餐单来源校验服务未配置', 50301, 503);
        }
        $url = substr($sessionUrl, 0, -strlen('/auth/wechat/session')) . '/health/v1/commerce/source-validation';
        $curl = curl_init($url);
        curl_setopt_array($curl, [CURLOPT_POST => true, CURLOPT_POSTFIELDS => Json::encode($proof),
            CURLOPT_RETURNTRANSFER => true, CURLOPT_FOLLOWLOCATION => false, CURLOPT_CONNECTTIMEOUT => 3,
            CURLOPT_TIMEOUT => 10, CURLOPT_SSL_VERIFYPEER => true, CURLOPT_SSL_VERIFYHOST => 2,
            CURLOPT_HTTPHEADER => ['Content-Type: application/json', 'Accept: application/json']]);
        $body = curl_exec($curl);
        $status = (int)curl_getinfo($curl, CURLINFO_HTTP_CODE);
        curl_close($curl);
        $data = json_decode((string)$body, true);
        if ($status !== 200 || ($data['available'] ?? null) !== true) {
            throw new DomainException('餐单采用、授权或采购换算已失效，或来源服务暂不可用，请重新核对', 40944, 409);
        }
        if ($linked) {
            $package = (new RecommendationPackageService())->getBySn($ref, $userId);
            return array_map('strval', array_column($package['items'], 'sku_id'));
        }
    }

    public function assertCart($userId, array $items)
    {
        $sources = [];
        foreach ($items as $item) {
            $key = ($item['source_type'] ?? '') . ':' . ($item['source_ref'] ?? '') . ':' . ($item['source_version'] ?? 0);
            if (!array_key_exists($key, $sources)) {
                $sources[$key] = $this->assertSource($userId, $item['source_type'] ?? '', $item['source_ref'] ?? '', $item['source_version'] ?? 0);
            }
            if (is_array($sources[$key]) && !in_array((string)$item['sku_id'], $sources[$key], true)) {
                throw new DomainException('商品不属于本次采购来源，请重新选择', 40301, 403);
            }
        }
    }
}
