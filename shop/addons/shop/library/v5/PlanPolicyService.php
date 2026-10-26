<?php

namespace addons\shop\library\v5;

use think\Db;

/** 三档、费用、预约和重复限制的版本化业务配置。 */
class PlanPolicyService
{
    const TIERS = ['economy' => '经济型', 'standard' => '标准型', 'premium' => '品质型'];

    public function current($version = null)
    {
        $query = Db::name('shop_plan_policy')->where('status', 'active')->where('effective_at', '<=', time());
        if ($version !== null) $query->where('policy_version', $version);
        $row = $query->order('effective_at desc,id desc')->find();
        if (!$row) throw new DomainException('专属计划规则尚未配置', 50317, 503, ['reason_code' => 'plan_policy_missing']);
        $config = Json::decode($row['config_json'], []);
        self::validate($config);
        if (!hash_equals($row['content_hash'], hash('sha256', Json::canonical($config)))) {
            throw new DomainException('专属计划规则版本无法核对', 50317, 503);
        }
        return ['version' => $row['policy_version'], 'hash' => $row['content_hash'], 'config' => $config];
    }

    public function readiness()
    {
        try {
            $policy = $this->current();
            return ['status' => 'ready', 'policy' => $policy];
        } catch (DomainException $error) {
            if ($error->getCode() !== 50317) throw $error;
            return ['status' => 'unavailable', 'reason_code' => 'plan_policy_missing', 'message' => '专属计划暂未开放'];
        }
    }

    /** 发布后内容不可覆盖，新规则必须另建版本。 */
    public function publish($version, array $config, $effectiveAt)
    {
        if (!preg_match('/^[A-Za-z0-9_.-]{1,64}$/D',(string)$version) || !is_int($effectiveAt) || $effectiveAt < 1) self::invalid('version');
        self::validate($config);
        foreach ($config['tiers'] as $tier) foreach ($tier['allowed_sku_ids'] as $sid) (new CatalogService())->getSku($sid,true);
        Db::startTrans();
        try {
        (new PlanScheduleService())->lockCapacity();
        $hash=hash('sha256',Json::canonical($config));
        $existing=Db::name('shop_plan_policy')->where('policy_version',$version)->find();
        if ($existing) {
            if (!hash_equals($existing['content_hash'],$hash) || (int)$existing['effective_at']!==$effectiveAt) throw new DomainException('已发布规则不可覆盖，请创建新版本',40906,409);
            Db::commit();return ['version'=>$version,'hash'=>$hash];
        }
        Db::name('shop_plan_policy')->insert(['policy_version'=>$version,'config_json'=>Json::encode($config),
            'content_hash'=>$hash,'status'=>'active','effective_at'=>$effectiveAt,'createtime'=>time(),'updatetime'=>time()]);
        Db::commit();return ['version'=>$version,'hash'=>$hash];
        } catch (\Throwable $error) {Db::rollback();throw $error;}
    }

    /** 预算只核对真实计算金额，绝不据此降低成员份量。 */
    public static function assertBudget(array $tier, $members, $goods, $service, $shipping = null)
    {
        foreach ($tier['budget'] as $band) {
            if ($members < $band['min_members'] || $members > $band['max_members']) continue;
            if ($band['includes_delivery_fee'] && $shipping === null) return; // 选地址后的完整报价再检查。
            $amount=$goods+($band['includes_service_fee']?$service:0)+($band['includes_delivery_fee']?$shipping:0);
            if ($amount >= $band['min_cent'] && $amount <= $band['max_cent']) return;
            throw new DomainException('本次实际费用超出当前档位预算，请调整商品配置后重新评估',40962,409);
        }
        throw new DomainException('当前成员组合尚未配置适用预算',50317,503);
    }

    public static function validate(array $config)
    {
        foreach (['tiers', 'service_fee_cent', 'delivery', 'repeat_identity', 'quote_ttl_seconds', 'estimate_ttl_seconds'] as $field) {
            if (!array_key_exists($field, $config)) self::invalid($field);
        }
        foreach (['service_fee_cent', 'quote_ttl_seconds', 'estimate_ttl_seconds'] as $field) {
            if (!is_int($config[$field]) || $config[$field] < ($field === 'service_fee_cent' ? 0 : 1)) self::invalid($field);
        }
        if (!is_array($config['repeat_identity']) || !$config['repeat_identity']) self::invalid('repeat_identity');
        foreach ($config['repeat_identity'] as $recipe => $identity) {
            if (!is_array($identity) || empty($identity['dish_key']) || empty($identity['main_ingredient_key'])) self::invalid('repeat_identity.'.$recipe);
        }
        if (!is_array($config['tiers']) || array_diff(array_keys(self::TIERS), array_keys($config['tiers'])) || count($config['tiers']) !== 3) self::invalid('tiers');
        foreach (self::TIERS as $code => $name) {
            $tier = $config['tiers'][$code];
            foreach (['allowed_sku_ids', 'allowed_recipe_version_ids', 'difference', 'budget', 'repeat'] as $field) {
                if (!isset($tier[$field]) || $tier[$field] === '' || $tier[$field] === []) self::invalid('tiers.'.$code.'.'.$field);
            }
            if (!is_array($tier['allowed_sku_ids']) || !is_array($tier['allowed_recipe_version_ids'])) self::invalid('tiers.'.$code.'.allowed');
            foreach ($tier['allowed_recipe_version_ids'] as $rid) if (!isset($config['repeat_identity'][$rid])) self::invalid('repeat_identity.'.$rid);
            // 人数区间只选择预算上限，不用于估算份量或把成人价乘人数。
            $bands=[];
            foreach ((array)$tier['budget'] as $budget) {
                foreach (['min_members','max_members','min_cent','max_cent'] as $key) {
                    if (!isset($budget[$key]) || !is_int($budget[$key]) || $budget[$key] < 0) self::invalid('tiers.'.$code.'.budget.'.$key);
                }
                if ($budget['min_members'] < 1 || $budget['max_members'] < $budget['min_members'] || $budget['max_cent'] < $budget['min_cent'] ||
                    !isset($budget['includes_service_fee'], $budget['includes_delivery_fee']) ||
                    !is_bool($budget['includes_service_fee']) || !is_bool($budget['includes_delivery_fee'])) self::invalid('tiers.'.$code.'.budget');
                foreach ($bands as $previous) if ($previous['min_members']<=$budget['max_members'] && $budget['min_members']<=$previous['max_members']) self::invalid('tiers.'.$code.'.budget.overlap');
                $bands[]=$budget;
            }
            foreach (['dish_gap_days', 'dish_max_per_7_days', 'main_ingredient_max_per_7_days'] as $key) {
                $value = $tier['repeat'][$key] ?? null;
                if (!is_int($value) || $value < (strpos($key, 'gap') !== false ? 0 : 1) || $value > 21) self::invalid('tiers.'.$code.'.repeat.'.$key);
            }
        }
        $delivery = $config['delivery'];
        foreach (['first_lead_days','resume_lead_days','cutoff_lead_days','pause_max_days','booking_horizon_days'] as $key) {
            if (!isset($delivery[$key]) || !is_int($delivery[$key]) || $delivery[$key] < ($key === 'cutoff_lead_days' ? 0 : 1)) self::invalid('delivery.'.$key);
        }
        if (!preg_match('/^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/D', $delivery['cutoff_time'] ?? '')) self::invalid('delivery.cutoff_time');
        if (($delivery['meal_lead_days'] ?? null) !== 1) self::invalid('delivery.meal_lead_days');
        if (empty($delivery['regions']) || !is_array($delivery['regions'])) self::invalid('delivery.regions');
        $areas=[];
        foreach ($delivery['regions'] as $region) {
            if (empty($region['area_id']) || !isset($region['fee_cent']) || !is_int($region['fee_cent']) || $region['fee_cent'] < 0 ||
                empty($region['weekdays']) || array_diff($region['weekdays'], [1,2,3,4,5,6,7]) ||
                !isset($region['daily_capacity']) || !is_int($region['daily_capacity']) || $region['daily_capacity'] < 1 ||
                !isset($region['closed_dates']) || !is_array($region['closed_dates'])) self::invalid('delivery.regions');
            if (in_array((string)$region['area_id'],$areas,true)) self::invalid('delivery.regions.duplicate');
            $areas[]=(string)$region['area_id'];
            foreach ($region['closed_dates'] as $date) {
                $parsed=\DateTimeImmutable::createFromFormat('!Y-m-d',(string)$date);
                if (!$parsed || $parsed->format('Y-m-d')!==$date) self::invalid('delivery.closed_dates');
            }
        }
    }

    private static function invalid($field)
    {
        throw new DomainException('专属计划配置缺失或无效：'.$field, 50317, 503, ['field' => $field]);
    }
}
