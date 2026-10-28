<?php
namespace addons\shop\library\v5;

/** Only the Agent's live, saved meal receipt can authorize direct SKU selection. */
class AgentSkuSelectionService
{
    public static function hasDirect(array $requirements)
    {
        foreach ($requirements as $r) if (is_array($r) && !empty($r['sku_id'])) return true;
        return false;
    }

    public static function assertReceipt(array $payload, array $receipt)
    {
        $authority = $receipt['purchase_authority'] ?? [];
        if (($receipt['available'] ?? null) !== true || !$authority ||
            ($authority['nutrition_validation']['status'] ?? '') !== 'passed') self::invalid();
        foreach (['user_ref', 'family_ref', 'menu_version_ref', 'ingredient_requirements'] as $key) {
            if (!isset($payload[$key], $authority[$key]) || Json::canonical($payload[$key]) !== Json::canonical($authority[$key])) self::invalid();
        }
        if (isset($payload['nutrition_validation']) && Json::canonical($payload['nutrition_validation']) !== Json::canonical($authority['nutrition_validation'])) self::invalid();
        if (self::quantities($payload['items'] ?? []) !== self::quantities($authority['items'] ?? [])) self::invalid();
        foreach ($payload['ingredient_requirements'] as $r) {
            if (empty($r['sku_id']) || empty($r['food_id']) || empty($r['source_ref']) || empty($r['merchant_snapshot']) ||
                ($r['required_unit'] ?? '') !== 'g' || !is_numeric($r['required_value'] ?? null) ||
                !is_finite((float)$r['required_value']) || (float)$r['required_value'] <= 0) self::invalid();
        }
    }

    public static function quantities(array $items)
    {
        if (!$items) self::invalid();
        $result = [];
        foreach ($items as $item) {
            $sid = (string)($item['sku_id'] ?? ''); $q = $item['quantity'] ?? 0;
            if (is_bool($q) || !preg_match('/^[1-9][0-9]{0,15}$/D', $sid) || !preg_match('/^[1-9][0-9]{0,8}$/D', (string)$q) || isset($result[$sid])) self::invalid();
            $result[$sid] = (int)$q;
        }
        ksort($result); return $result;
    }

    public static function assertCatalog(array $requirements, array $items)
    {
        $ids = [];
        foreach ($requirements as $r) {
            $sid = (string)$r['sku_id']; $ids[$sid] = true;
            $sku = (new CatalogService())->getSku($sid, true);
            foreach (['product_id','sku_id','product_name','sku_name','sku_code','category_code','net_content'] as $field) {
                if (Json::canonical($r['merchant_snapshot'][$field] ?? null) !== Json::canonical($sku[$field] ?? null)) {
                    throw new DomainException('商品身份或包装已变化，请由Agent重新核对餐单',40946,409);
                }
            }
        }
        $actual = array_fill_keys(array_keys(self::quantities($items)), true);
        ksort($ids); ksort($actual);
        if ($ids !== $actual) self::invalid();
    }

    public static function assertPayload($clientId, array $payload, $validator = null)
    {
        if ($clientId !== trim((string)getenv('SHOP_AGENT_CLIENT_ID'))) self::invalid();
        $proof = $payload['agent_source_proof'] ?? [];
        $source = Json::decode($proof['payload'] ?? '{}', []);
        if (($source['kind'] ?? '') !== 'daily_arrangement') self::invalid();
        $receipt = ($validator ?: new AgentMealSourceService())->validateProof($proof);
        self::assertReceipt($payload, $receipt);
        self::assertCatalog($payload['ingredient_requirements'], $payload['items']);
        return array_map('strval', array_keys(self::quantities($payload['items'])));
    }

    private static function invalid()
    {
        throw new DomainException('Agent餐单来源、用户或规格数量不匹配，请重新核对',40944,409);
    }
}
