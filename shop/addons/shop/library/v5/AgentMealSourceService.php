<?php

namespace addons\shop\library\v5;

use think\Db;

/** Agent 来源由后端保存并回源核对，客户端不可替换。 */
class AgentMealSourceService
{
    public function assertSource($userId, $type, $ref, $version)
    {
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
        if ($type !== 'recommendation_package') return;
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
            if (empty($item['ingredient_id'])) continue;
            $ingredientCode=Db::name('shop_ingredient')->where('id',$item['ingredient_id'])->value('ingredient_code');
            $approved=false;
            foreach ($sku['ingredients'] as $map) if ($map['ingredient_code'] === $ingredientCode) $approved=true;
            if (!$approved) throw new DomainException('餐单商品食材关联已失效或未审核，请重新核对',40946,409);
        }
        $proof = Json::decode($row['agent_source_proof_json'] ?? '{}', []);
        if (!$proof) return; // Legacy packages retain their existing contract.
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
    }

    public function assertCart($userId, array $items)
    {
        $seen = [];
        foreach ($items as $item) {
            $key = ($item['source_type'] ?? '') . ':' . ($item['source_ref'] ?? '') . ':' . ($item['source_version'] ?? 0);
            if (isset($seen[$key])) continue;
            $seen[$key] = true;
            $this->assertSource($userId, $item['source_type'] ?? '', $item['source_ref'] ?? '', $item['source_version'] ?? 0);
        }
    }
}
