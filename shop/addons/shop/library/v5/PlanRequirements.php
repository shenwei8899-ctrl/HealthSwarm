<?php

namespace addons\shop\library\v5;

/** 计划完整性与每批采购需求；不负责医学或营养判断。 */
class PlanRequirements
{
    public static function validate(array $payload)
    {
        foreach (['recommendation_group_ref','tier_code','tier_policy_version','basis_hash','agent_source_proof'] as $key) {
            if (empty($payload[$key])) throw new DomainException('专属计划来源不完整',40007,400,['field'=>$key]);
        }
        if (!isset(PlanPolicyService::TIERS[$payload['tier_code']]) || !preg_match('/^[a-f0-9]{64}$/D',$payload['basis_hash'])) throw new DomainException('专属计划档次或档案依据无效',40007,400);
        $members=$payload['member_refs'] ?? [];
        if (!$members || count($members)!==count(array_unique($members)) || count($members)!==count($payload['profile_version_refs'] ?? [])) throw new DomainException('计划适用成员及档案版本不完整',40007,400);
        if (count($payload['days'] ?? [])!==21) throw new DomainException('必须提供完整21天三餐',40007,400);
        foreach ($payload['days'] as $day) {
            if (empty($day['eligible_sku_ids']) || !is_array($day['eligible_sku_ids'])) throw new DomainException('每日计划缺少经适用性核对的商品范围',40008,400);
            $coverage=[];
            foreach ($day['meals'] ?? [] as $meal) {
                if (!in_array($meal['meal_type'] ?? '',['breakfast','lunch','dinner'],true) || empty($meal['recipe_ref']) ||
                    empty($meal['recipe_version_ref']) || empty($meal['recipe_name']) || empty($meal['ingredient_requirements']) || empty($meal['member_portions'])) {
                    throw new DomainException('餐次、食谱版本、配料或成员份量不完整',40008,400,['day_no'=>$day['day_no']]);
                }
                foreach ($meal['member_portions'] as $portion) {
                    if (!in_array($portion['member_ref'] ?? '',$members,true) || !is_numeric($portion['grams'] ?? null) || !is_finite((float)$portion['grams']) || (float)$portion['grams']<=0) throw new DomainException('成员份量无效',40008,400);
                    $coverage[$meal['meal_type']][$portion['member_ref']]=true;
                }
                foreach ($meal['ingredient_requirements'] as $requirement) self::amount($requirement);
            }
            foreach (['breakfast','lunch','dinner'] as $type) {
                if (array_diff($members,array_keys($coverage[$type] ?? []))) throw new DomainException('每位适用成员都须有完整三餐',40008,400,['day_no'=>$day['day_no'],'meal_type'=>$type]);
            }
        }
        if (($payload['nutrition_validation']['status'] ?? '')!=='passed' || empty($payload['nutrition_validation']['validation_id']) || empty($payload['nutrition_validation']['rules_version'])) throw new DomainException('完整计划尚未通过饮食安全校验',40008,400);
    }

    public static function aggregate(array $meals)
    {
        $totals=[];
        foreach ($meals as $meal) foreach ($meal['ingredient_requirements'] as $requirement) {
            [$value,$unit]=self::amount($requirement);
            $key=$requirement['ingredient_code'].'|'.$unit;
            if (!isset($totals[$key])) $totals[$key]=['ingredient_code'=>$requirement['ingredient_code'],'required_value'=>0,'required_unit'=>$unit,'sources'=>[]];
            $totals[$key]['required_value']+=$value;
            $totals[$key]['sources'][]=['meal_type'=>$meal['meal_type'],'recipe_ref'=>$meal['recipe_ref'],'recipe_version_ref'=>$meal['recipe_version_ref'],'required_value'=>$value,'required_unit'=>$unit];
        }
        ksort($totals);
        return array_values($totals);
    }

    public static function contentHash(array $payload)
    {
        $content = array_intersect_key($payload,array_flip(['family_ref','user_ref','member_refs','profile_version_refs',
            'recommendation_group_ref','tier_code','tier_policy_version','basis_hash','days','nutrition_validation']));
        $normalize = function ($value) use (&$normalize) {
            if (is_array($value)) return array_map($normalize,$value);
            if (is_int($value)) return (string)$value;
            if (is_float($value)) return rtrim(rtrim(sprintf('%.8F',$value),'0'),'.');
            return $value;
        };
        return hash('sha256',Json::canonical($normalize($content)));
    }

    public static function validateTier(array $payload, array $policy)
    {
        $config=$policy['config'];$tier=$config['tiers'][$payload['tier_code']];$seen=[];
        $days=$payload['days'];usort($days,function ($a,$b) {return $a['day_no']-$b['day_no'];});
        foreach ($days as $day) {
            $keys=[];
            foreach ($day['meals'] as $meal) {
                $id=(string)$meal['recipe_version_ref'];
                if (!in_array($id,array_map('strval',$tier['allowed_recipe_version_ids']),true)) throw new DomainException('食谱不属于当前档位的审核范围',40008,400);
                $identity=$config['repeat_identity'][$id];
                $keys['dish'][$identity['dish_key']]=true;
                $keys['main'][$identity['main_ingredient_key']]=true;
            }
            if (array_diff(array_map('strval',$day['eligible_sku_ids']),array_map('strval',$tier['allowed_sku_ids']))) throw new DomainException('每日商品不属于当前档位',40008,400);
            $number=(int)$day['day_no'];
            foreach ($keys as $kind=>$values) foreach ($values as $key=>$unused) {
                $history=$seen[$kind][$key] ?? [];
                if ($kind==='dish' && $history && $number-end($history)<=$tier['repeat']['dish_gap_days']) throw new DomainException('菜品间隔不符合档位规则',40008,400);
                $count=count(array_filter($history,function ($n) use ($number) {return $n>=$number-6;}));
                $limit=$tier['repeat'][$kind==='dish'?'dish_max_per_7_days':'main_ingredient_max_per_7_days'];
                if ($count >= $limit) throw new DomainException('菜品丰富度不符合档位规则',40008,400);
                $seen[$kind][$key][]=$number;
            }
        }
    }

    public static function matchBatch(array $meals, array $allowedSkus)
    {
        $requirements=self::aggregate($meals);$visits=0;$failure=null;
        // 每步扣除同批已选库存；无解时回退候选，不把贪心选择当成真实缺货。
        $search=function ($remaining, $items) use (&$search, &$visits, &$failure, $requirements, $allowedSkus) {
            if (++$visits>10000) return null;
            $index=null;
            foreach ($remaining as $key=>$requirement) {
                if ($requirement['required_value']>0.000001) {$index=$key;break;}
            }
            if ($index===null) return $items;
            $requirement=$remaining[$index];
            $result=(new ProductMatchService())->matchRequirement($requirement,$allowedSkus,array_column($requirements,'ingredient_code'));
            if ($result['issue']) {$failure=$result['issue'];return null;}
            foreach ($result['candidates'] as $item) {
                $sid=(string)$item['sku_id'];$quantity=(int)$item['quantity'];
                if ($quantity+($items[$sid]['quantity'] ?? 0)>(int)$item['product_snapshot']['available_quantity']) continue;
                $selected=$items;$rest=$remaining;
                if (!isset($selected[$sid])) $selected[$sid]=$item+['ingredient_codes'=>[],'sources'=>[]];
                else {$selected[$sid]['quantity']+=$quantity;$selected[$sid]['total_price_cent']+=$item['total_price_cent'];}
                foreach ($remaining as $otherIndex=>$other) {
                    $covered=0;
                    foreach ($item['product_snapshot']['ingredients'] ?? [] as $map) {
                        if ($map['ingredient_code']!==$other['ingredient_code']) continue;
                        $net=CatalogEligibility::convert($map['net_value'],$map['net_unit'],$other['required_unit']);
                        if ($net!==null) $covered+=(float)$net*(float)$map['convert_ratio']*(1-(float)$map['loss_rate'])*$quantity;
                    }
                    if ($covered<=0 && $otherIndex===$index) $covered=(float)$item['covered_value'];
                    if ($covered>0) {
                        $rest[$otherIndex]['required_value']=max(0,$other['required_value']-$covered);
                        $selected[$sid]['ingredient_codes'][]=$other['ingredient_code'];
                        $selected[$sid]['sources']=array_merge($selected[$sid]['sources'],$other['sources']);
                    }
                }
                $matched=$search($rest,$selected);
                if ($matched!==null) return $matched;
            }
            return null;
        };
        $items=$search($requirements,[]);
        if ($items===null) return ['items'=>[],'issues'=>[$visits>10000
            ? ['issue_code'=>'match_search_exhausted','message'=>'商品组合较多，请调整商品范围后重新核对','blocking'=>true]
            : ($failure ?: ['issue_code'=>'out_of_stock','message'=>'没有满足本批全部食材的库存组合','blocking'=>true])], 'requirements'=>$requirements];
        foreach ($items as &$item) {
            $item['ingredient_codes']=array_values(array_unique($item['ingredient_codes']));
        }
        return ['items'=>array_values($items),'issues'=>[],'requirements'=>$requirements];
    }

    private static function amount(array $requirement)
    {
        $value=$requirement['required_value'] ?? null;$unit=$requirement['required_unit'] ?? '';
        if (empty($requirement['ingredient_code']) || !is_numeric($value) || !is_finite((float)$value) || (float)$value<=0 || !in_array($unit,['g','kg','ml','l'],true)) throw new DomainException('计划食材需求或单位不完整',40008,400);
        return [(float)$value*(in_array($unit,['kg','l'],true)?1000:1),in_array($unit,['g','kg'],true)?'g':'ml'];
    }
}
