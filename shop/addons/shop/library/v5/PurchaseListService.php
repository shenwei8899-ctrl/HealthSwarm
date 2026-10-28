<?php

namespace addons\shop\library\v5;

use think\Db;

class PurchaseListService
{
    public function confirmRecommendation($userId, $packageSn, $submittedVersion, $requestId)
    {
        (new AgentMealSourceService())->assertSource($userId, 'recommendation_package', $packageSn, $submittedVersion);
        Db::startTrans();
        try {
            $package = Db::name('shop_recommendation_package')->where('package_sn', $packageSn)->lock(true)->find();
            if (!$package) {
                throw new DomainException('推荐包不存在', 40402, 404);
            }
            (new IdentityService())->assertOwner($userId, $package['user_id']);
            if ((int)$package['current_version'] !== (int)$submittedVersion) {
                throw new DomainException('推荐包版本已变化，请刷新后重试', 40906, 409, [
                    'current_version' => (int)$package['current_version'],
                    'submitted_version' => (int)$submittedVersion,
                ]);
            }
            if (!in_array($package['status'], ['available', 'confirmed'], true) || !AgentMealSourceService::nutritionAllowsTrade($package) || $package['trade_status'] !== 'passed') {
                throw new DomainException('推荐包尚未通过营养和交易双校验', 40908, 409);
            }
            if ((int)$package['expires_at'] <= time()) {
                throw new DomainException('推荐包已过期', 40909, 409);
            }
            $existing = Db::name('shop_purchase_list')->where([
                'user_id' => $userId, 'source_type' => 'recommendation_package',
                'source_ref' => $packageSn, 'source_version' => $submittedVersion,
            ])->find();
            if ($existing) {
                Db::commit();
                return $this->getBySn($existing['purchase_list_sn'], $userId);
            }

            $version = Db::name('shop_recommendation_package_version')->where('package_id', $package['id'])
                ->where('version_no', $submittedVersion)->find();
            $requirements = Json::decode($version['requirements_snapshot_json'], []);
            $listSn = Identifiers::make('purchase');
            $now = time();
            $listId = Db::name('shop_purchase_list')->insertGetId([
                'purchase_list_sn' => $listSn,
                'user_id' => $userId,
                'source_type' => 'recommendation_package',
                'source_ref' => $packageSn,
                'source_version' => $submittedVersion,
                'current_version' => 1,
                'match_status' => 'matching',
                'confirm_status' => 'unconfirmed',
                'currency' => 'CNY',
                'expires_at' => min((int)$package['expires_at'], $now + 1800),
                'status' => 'matching',
                'version' => 1,
                'createtime' => $now,
                'updatetime' => $now,
            ]);
            $reference = AgentMealSourceService::referenceSource(Json::decode($package['agent_source_proof_json'] ?? '{}', []));
            $result = $reference !== null
                ? $this->insertReferenceSelection($listId, $version['id'], $now)
                : (AgentSkuSelectionService::hasDirect($requirements)
                    ? $this->insertAgentSelection($listId, $version['id'], $requirements, $now)
                    : $this->insertRequirementsAndMatches($listId, 1, $requirements, $now));
            Db::name('shop_purchase_list')->where('id', $listId)->update([
                'match_status' => $result['ready'] ? 'ready' : 'failed',
                'estimated_total_cent' => $result['total_amount_cent'],
                'status' => $result['ready'] ? 'ready' : 'matching',
                'updatetime' => $now,
            ]);
            Db::name('shop_recommendation_package')->where('id', $package['id'])->update([
                'confirm_status' => 'confirmed',
                'confirmed_at' => $now,
                'status' => 'confirmed',
                'updatetime' => $now,
            ]);
            (new OutboxService())->append('purchase.list.created', 'purchase_list', $listSn, 1, 'miniapp', [
                'purchase_list_sn' => $listSn, 'package_sn' => $packageSn, 'request_id' => $requestId,
            ]);
            Db::commit();
        } catch (\Exception $e) {
            Db::rollback();
            throw $e;
        }
        return $this->getBySn($listSn, $userId);
    }

    public function updatePantry($userId, $listSn, $baseVersion, array $pantryItems)
    {
        Db::startTrans();
        try {
            $list = Db::name('shop_purchase_list')->where('purchase_list_sn', $listSn)->lock(true)->find();
            if (!$list) {
                throw new DomainException('采购清单不存在', 40403, 404);
            }
            (new IdentityService())->assertOwner($userId, $list['user_id']);
            $this->assertLegacyRematch($list);
            if ((int)$list['current_version'] !== (int)$baseVersion) {
                throw new DomainException('采购清单版本冲突', 40906, 409, ['current_version' => (int)$list['current_version']]);
            }
            if (in_array($list['status'], ['confirmed', 'ordered', 'expired'], true)) {
                throw new DomainException('当前采购清单不可修改', 40910, 409);
            }
            $newVersion = (int)$baseVersion + 1;
            $oldItems = Db::name('shop_purchase_item')->where('purchase_list_id', $list['id'])
                ->where('list_version_no', $baseVersion)->order('sort', 'asc')->select();
            $pantryByIngredient = [];
            $pantryByItem = [];
            foreach ($pantryItems as $item) {
                if (isset($item['ingredient_id'])) $pantryByIngredient[(string)$item['ingredient_id']] = $item;
                if (isset($item['purchase_item_id'])) $pantryByItem[(string)$item['purchase_item_id']] = $item;
            }
            $requirements = [];
            foreach ($oldItems as $old) {
                $pantry = isset($pantryByItem[(string)$old['id']]) ? $pantryByItem[(string)$old['id']] : (isset($pantryByIngredient[(string)$old['ingredient_id']]) ? $pantryByIngredient[(string)$old['ingredient_id']] : []);
                $pantryValue = isset($pantry['available_quantity']) ? max(0, (float)$pantry['available_quantity']) : (isset($pantry['value']) ? max(0, (float)$pantry['value']) : 0);
                $requirements[] = [
                    'recipe_ref' => $old['recipe_ref'],
                    'ingredient_id' => $old['ingredient_id'],
                    'required_value' => $old['required_value'],
                    'required_unit' => $old['required_unit'],
                    'pantry_value' => $pantryValue,
                    'pantry_unit' => isset($pantry['unit']) ? $pantry['unit'] : $old['required_unit'],
                    'is_optional' => $old['is_optional'],
                ];
            }
            $result = $this->insertRequirementsAndMatches($list['id'], $newVersion, $requirements, time());
            $affected = Db::name('shop_purchase_list')->where('id', $list['id'])->where('current_version', $baseVersion)->update([
                'current_version' => $newVersion,
                'match_status' => $result['ready'] ? 'ready' : 'failed',
                'estimated_total_cent' => $result['total_amount_cent'],
                'status' => $result['ready'] ? 'ready' : 'matching',
                'version' => (int)$list['version'] + 1,
                'updatetime' => time(),
            ]);
            if (!$affected) {
                throw new DomainException('采购清单版本冲突', 40906, 409);
            }
            Db::commit();
        } catch (\Exception $e) {
            Db::rollback();
            throw $e;
        }
        return $this->getBySn($listSn, $userId);
    }

    public function rematch($userId, $listSn, $baseVersion)
    {
        $list = Db::name('shop_purchase_list')->where('purchase_list_sn', $listSn)->find();
        if (!$list) throw new DomainException('采购清单不存在', 40403, 404);
        (new IdentityService())->assertOwner($userId, $list['user_id']);
        $items = Db::name('shop_purchase_item')->where('purchase_list_id', $list['id'])->where('list_version_no', $baseVersion)->select();
        $pantry = [];
        foreach ($items as $item) {
            $pantry[] = ['purchase_item_id'=>$item['id'],'available_quantity'=>$item['pantry_value'],'unit'=>$item['pantry_unit']];
        }
        return $this->updatePantry($userId, $listSn, $baseVersion, $pantry);
    }

    public function selectMatch($userId, $listSn, $purchaseItemId, $matchId, $baseVersion)
    {
        Db::startTrans();
        try {
            $list = Db::name('shop_purchase_list')->where('purchase_list_sn', $listSn)->lock(true)->find();
            if (!$list) throw new DomainException('采购清单不存在', 40403, 404);
            (new IdentityService())->assertOwner($userId, $list['user_id']);
            $this->assertLegacyRematch($list);
            if ((int)$list['current_version'] !== (int)$baseVersion || in_array($list['status'], ['ordered','expired'], true)) throw new DomainException('采购清单版本或状态不允许修改', 40906, 409);
            $item = Db::name('shop_purchase_item')->where('id', (int)$purchaseItemId)->where('purchase_list_id', $list['id'])->where('list_version_no', $baseVersion)->find();
            $match = $item ? Db::name('shop_purchase_match')->where('id', (int)$matchId)->where('purchase_item_id', $item['id'])->where('list_version_no', $baseVersion)->find() : null;
            if (!$match || $match['trade_status'] !== 'passed') throw new DomainException('候选商品不可用', 40904, 409);
            Db::name('shop_purchase_match')->where('purchase_item_id', $item['id'])->where('list_version_no', $baseVersion)->update(['is_selected'=>0,'updatetime'=>time()]);
            Db::name('shop_purchase_match')->where('id', $match['id'])->update(['is_selected'=>1,'updatetime'=>time()]);
            Db::name('shop_purchase_item')->where('id', $item['id'])->update(['selected_match_id'=>$match['id'],'match_status'=>'matched','updatetime'=>time()]);
            $total = (int)Db::name('shop_purchase_match')->alias('m')->join('shop_purchase_item i','i.id=m.purchase_item_id')
                ->where('i.purchase_list_id',$list['id'])->where('i.list_version_no',$baseVersion)->where('m.is_selected',1)->sum('m.total_price_cent');
            Db::name('shop_purchase_list')->where('id',$list['id'])->update(['estimated_total_cent'=>$total,'version'=>(int)$list['version']+1,'updatetime'=>time()]);
            Db::commit();
        } catch (\Exception $e) { Db::rollback(); throw $e; }
        return $this->getBySn($listSn, $userId);
    }

    public function addToCart($userId, $listSn, $baseVersion)
    {
        (new AgentMealSourceService())->assertSource($userId, 'purchase_list', $listSn, $baseVersion);
        $list = Db::name('shop_purchase_list')->where('purchase_list_sn', $listSn)->find();
        if (!$list) throw new DomainException('采购清单不存在', 40403, 404);
        (new IdentityService())->assertOwner($userId, $list['user_id']);
        if ((int)$list['current_version'] !== (int)$baseVersion || !in_array($list['status'], ['ready','confirmed'], true)) throw new DomainException('采购清单未就绪或版本已变化', 40906, 409);
        $matches = Db::name('shop_purchase_match')->alias('m')->join('shop_purchase_item i','i.id=m.purchase_item_id')
            ->where('i.purchase_list_id',$list['id'])->where('i.list_version_no',$baseVersion)->where('m.is_selected',1)
            ->field('m.*,i.id as item_id')->select();
        $cart = new CartService();
        Db::startTrans();
        try {
            Db::name('user')->where('id', (int)$userId)->lock(true)->find();
            $needed = [];
            foreach ($matches as $match) {
                $skuId = (string)$match['sku_id'];
                if (!isset($needed[$skuId])) $needed[$skuId] = ['quantity'=>0,'item_id'=>$match['item_id']];
                $needed[$skuId]['quantity'] += (int)$match['required_pack_count'];
            }
            foreach ($needed as $skuId => $requirement) {
                $existing = Db::name('shop_carts')->where(['user_id'=>(int)$userId,'goods_sku_id'=>(int)$skuId,
                    'sceneval'=>1,'source_type'=>'purchase_list','source_ref'=>$listSn])->find();
                if ($existing && (int)$existing['source_version'] !== (int)$baseVersion) {
                    throw new DomainException('购物车已有旧版本采购清单，请先移除后重新加入',40906,409);
                }
                $delta = max(0, $requirement['quantity'] - (int)($existing['nums'] ?? 0));
                if (!$delta) continue;
                $cart->add($userId,$skuId,$delta,[
                    'source_type'=>'purchase_list','source_ref'=>$listSn,'source_version'=>$baseVersion,'purchase_item_id'=>$requirement['item_id'],
                ]);
            }
            Db::commit();
        } catch (\Exception $e) { Db::rollback(); throw $e; }
        return $cart->listItems($userId);
    }

    public function confirm($userId, $listSn, $baseVersion)
    {
        $list = Db::name('shop_purchase_list')->where('purchase_list_sn', $listSn)->find();
        if (!$list) {
            throw new DomainException('采购清单不存在', 40403, 404);
        }
        (new IdentityService())->assertOwner($userId, $list['user_id']);
        if ((int)$list['current_version'] !== (int)$baseVersion || $list['status'] !== 'ready') {
            throw new DomainException('采购清单未就绪或版本已变化', 40906, 409);
        }
        if ((int)$list['expires_at'] <= time()) {
            throw new DomainException('采购清单已过期', 40909, 409);
        }
        Db::name('shop_purchase_list')->where('id', $list['id'])->where('current_version', $baseVersion)->update([
            'confirm_status' => 'confirmed', 'status' => 'confirmed', 'updatetime' => time(),
        ]);
        return $this->getBySn($listSn, $userId);
    }

    public function getBySn($listSn, $userId = null)
    {
        $list = Db::name('shop_purchase_list')->where('purchase_list_sn', $listSn)->find();
        if (!$list) {
            throw new DomainException('采购清单不存在', 40403, 404);
        }
        if ($userId !== null) {
            (new IdentityService())->assertOwner($userId, $list['user_id']);
        }
        $items = Db::name('shop_purchase_item')->where('purchase_list_id', $list['id'])
            ->where('list_version_no', $list['current_version'])->order('sort', 'asc')->select();
        foreach ($items as &$item) {
            $item['matches'] = Db::name('shop_purchase_match')->where('purchase_item_id', $item['id'])
                ->where('list_version_no', $list['current_version'])->order('rank_no', 'asc')->select();
            foreach ($item['matches'] as &$match) {
                $match['match_reason'] = Json::decode($match['match_reason_json'], []);
                unset($match['match_reason_json']);
            }
        }
        return [
            'purchase_list_sn' => $list['purchase_list_sn'],
            'version' => (int)$list['current_version'],
            'status' => $list['status'],
            'match_status' => $list['match_status'],
            'confirm_status' => $list['confirm_status'],
            'estimated_total_cent' => (int)$list['estimated_total_cent'],
            'expires_at' => date(DATE_ATOM, (int)$list['expires_at']),
            'items' => $items,
        ];
    }

    /** Carry the authoritative Agent selection forward; do not rematch nutrition in the mall. */
    protected function insertAgentSelection($listId, $versionId, array $requirements, $now)
    {
        $items = Db::name('shop_recommendation_package_item')->where('package_version_id',$versionId)->order('sort','asc')->select();
        $total = 0;
        foreach ($items as $sort => $item) {
            $required = 0;
            foreach ($requirements as $r) if ((string)$r['sku_id'] === (string)$item['sku_id']) $required += (float)$r['required_value'];
            $result = (new ProductMatchService())->validateSubmittedItem(['sku_id'=>$item['sku_id'],'quantity'=>(int)$item['quantity']]);
            if ($result['issue']) throw new DomainException('Agent所选商品暂不可售，请重新核对',40904,409);
            $selected = $result['selected']; $sku = $selected['product_snapshot'];
            $net = $sku['net_content'];
            if (!in_array($net['unit'],['g','kg'],true) || (float)$net['value'] <= 0) throw new DomainException('商品包装无法核对',40946,409);
            $covered = (float)$net['value'] * ($net['unit']==='kg' ? 1000 : 1) * (int)$item['quantity'];
            if ($required <= 0 || $covered + 0.000001 < $required) throw new DomainException('Agent采购数量不足，请重新核对',40944,409);
            $itemId = Db::name('shop_purchase_item')->insertGetId([
                'purchase_list_id'=>$listId, 'list_version_no'=>1, 'recipe_ref'=>'agent-sku:'.$item['sku_id'],
                'ingredient_id'=>0, 'required_value'=>$required, 'required_unit'=>'g',
                'pantry_value'=>0, 'pantry_unit'=>'g', 'net_required_value'=>$required, 'net_required_unit'=>'g',
                'is_optional'=>0, 'match_status'=>'matched', 'sort'=>$sort,'createtime'=>$now,'updatetime'=>$now,
            ]);
            $matchId = Db::name('shop_purchase_match')->insertGetId([
                'purchase_item_id'=>$itemId,'list_version_no'=>1,'sku_id'=>$item['sku_id'],'rank_no'=>1,
                'required_pack_count'=>(int)$item['quantity'],'covered_value'=>$covered,'covered_unit'=>'g',
                'surplus_value'=>max(0,$covered-$required),'surplus_unit'=>'g',
                'unit_price_cent'=>$selected['unit_price_cent'],'total_price_cent'=>$selected['total_price_cent'],
                'match_score'=>100,'match_reason_json'=>Json::encode(['reason'=>'agent_selected_sku','snapshot'=>$sku]),
                'trade_status'=>'passed','requires_agent_revalidation'=>0,'is_selected'=>1,'createtime'=>$now,'updatetime'=>$now,
            ]);
            Db::name('shop_purchase_item')->where('id',$itemId)->update(['selected_match_id'=>$matchId]);
            $total += (int)$selected['total_price_cent'];
        }
        return ['ready'=>true,'total_amount_cent'=>$total];
    }

    /** 参考商品按实际包装数量采购，不生成虚构的食材或营养换算。 */
    protected function insertReferenceSelection($listId, $versionId, $now)
    {
        $items = Db::name('shop_recommendation_package_item')->where('package_version_id',$versionId)->order('sort','asc')->select();
        if (!$items) throw new DomainException('采购商品不能为空',40012,400);
        $total = 0;
        foreach ($items as $sort => $item) {
            $result = (new ProductMatchService())->validateSubmittedItem(['sku_id'=>$item['sku_id'],'quantity'=>(int)$item['quantity']]);
            if ($result['issue']) throw new DomainException('所选商品暂不可售，请重新核对',40904,409);
            $selected = $result['selected']; $quantity = (int)$item['quantity'];
            $itemId = Db::name('shop_purchase_item')->insertGetId([
                'purchase_list_id'=>$listId,'list_version_no'=>1,'recipe_ref'=>'catalog-sku:'.$item['sku_id'],
                'ingredient_id'=>0,'required_value'=>$quantity,'required_unit'=>'pack',
                'pantry_value'=>0,'pantry_unit'=>'pack','net_required_value'=>$quantity,'net_required_unit'=>'pack',
                'is_optional'=>0,'match_status'=>'matched','sort'=>$sort,'createtime'=>$now,'updatetime'=>$now,
            ]);
            $matchId = Db::name('shop_purchase_match')->insertGetId([
                'purchase_item_id'=>$itemId,'list_version_no'=>1,'sku_id'=>$item['sku_id'],'rank_no'=>1,
                'required_pack_count'=>$quantity,'covered_value'=>$quantity,'covered_unit'=>'pack',
                'surplus_value'=>0,'surplus_unit'=>'pack','unit_price_cent'=>$selected['unit_price_cent'],
                'total_price_cent'=>$selected['total_price_cent'],'match_score'=>100,
                'match_reason_json'=>Json::encode(['reason'=>'agent_catalog_selection','snapshot'=>$selected['product_snapshot']]),
                'trade_status'=>'passed','requires_agent_revalidation'=>0,'is_selected'=>1,'createtime'=>$now,'updatetime'=>$now,
            ]);
            Db::name('shop_purchase_item')->where('id',$itemId)->update(['selected_match_id'=>$matchId]);
            $total += (int)$selected['total_price_cent'];
        }
        return ['ready'=>true,'total_amount_cent'=>$total];
    }

    protected function assertLegacyRematch(array $list)
    {
        if ($list['source_type'] !== 'recommendation_package') return;
        $package = Db::name('shop_recommendation_package')->where('package_sn',$list['source_ref'])->find();
        if ($package && AgentMealSourceService::referenceSource(Json::decode($package['agent_source_proof_json'] ?? '{}', [])) !== null) {
            throw new DomainException('商品按已选规格采购，调整商品请重新查询',40944,409);
        }
        $packageId = $package['id'] ?? 0;
        $v = Db::name('shop_recommendation_package_version')->where('package_id',$packageId)->where('version_no',$list['source_version'])->find();
        if ($v && AgentSkuSelectionService::hasDirect(Json::decode($v['requirements_snapshot_json'],[]))) {
            throw new DomainException('本清单由Agent选定规格，食材准备或替换请由Agent重新生成采购来源',40944,409);
        }
    }


    protected function insertRequirementsAndMatches($listId, $version, array $requirements, $now)
    {
        $matcher = new ProductMatchService();
        $ready = true;
        $total = 0;
        foreach ($requirements as $sort => $requirement) {
            $ingredientId = !empty($requirement['ingredient_id']) ? (int)$requirement['ingredient_id'] : 0;
            if (!$ingredientId && !empty($requirement['ingredient_code'])) {
                $ingredientId = (int)Db::name('shop_ingredient')->where('ingredient_code', $requirement['ingredient_code'])->value('id');
            }
            $required = (float)$requirement['required_value'];
            $pantry = isset($requirement['pantry_value']) ? (float)$requirement['pantry_value'] : 0;
            $net = max(0, $required - $pantry);
            $itemId = Db::name('shop_purchase_item')->insertGetId([
                'purchase_list_id' => $listId,
                'list_version_no' => $version,
                'recipe_ref' => isset($requirement['recipe_ref']) ? $requirement['recipe_ref'] : '',
                'ingredient_id' => $ingredientId,
                'required_value' => $required,
                'required_unit' => $requirement['required_unit'],
                'pantry_value' => $pantry,
                'pantry_unit' => isset($requirement['pantry_unit']) ? $requirement['pantry_unit'] : $requirement['required_unit'],
                'net_required_value' => $net,
                'net_required_unit' => $requirement['required_unit'],
                'is_optional' => empty($requirement['is_optional']) ? 0 : 1,
                'match_status' => $net <= 0 ? 'not_needed' : 'pending',
                'sort' => $sort,
                'createtime' => $now,
                'updatetime' => $now,
            ]);
            if ($net <= 0) {
                continue;
            }
            $ingredientCode = !empty($requirement['ingredient_code']) ? $requirement['ingredient_code'] : Db::name('shop_ingredient')->where('id', $ingredientId)->value('ingredient_code');
            $matchResult = $matcher->matchRequirement([
                'ingredient_code' => $ingredientCode,
                'required_value' => $net,
                'required_unit' => $requirement['required_unit'],
            ]);
            if (!$matchResult['selected']) {
                if (empty($requirement['is_optional'])) {
                    $ready = false;
                }
                Db::name('shop_purchase_item')->where('id', $itemId)->update(['match_status' => 'failed']);
                continue;
            }
            $selectedMatchId = 0;
            foreach ($matchResult['candidates'] as $rank => $match) {
                $matchId = Db::name('shop_purchase_match')->insertGetId([
                    'purchase_item_id' => $itemId,
                    'list_version_no' => $version,
                    'sku_id' => $match['sku_id'],
                    'rank_no' => $rank + 1,
                    'required_pack_count' => $match['quantity'],
                    'covered_value' => $match['covered_value'],
                    'covered_unit' => $match['covered_unit'],
                    'surplus_value' => $match['surplus_value'],
                    'surplus_unit' => $match['covered_unit'],
                    'unit_price_cent' => $match['unit_price_cent'],
                    'total_price_cent' => $match['total_price_cent'],
                    // 匹配器以基点排序，持久化为百分制以适配 numeric(8,4)。
                    'match_score' => min(9999.9999, (float)$match['match_score'] / 100),
                    'match_reason_json' => Json::encode(['reason' => 'same_ingredient', 'snapshot' => $match['product_snapshot']]),
                    'trade_status' => 'passed',
                    'requires_agent_revalidation' => 0,
                    'is_selected' => $rank === 0 ? 1 : 0,
                    'createtime' => $now,
                    'updatetime' => $now,
                ]);
                if ($rank === 0) {
                    $selectedMatchId = $matchId;
                    $total += (int)$match['total_price_cent'];
                }
            }
            Db::name('shop_purchase_item')->where('id', $itemId)->update([
                'selected_match_id' => $selectedMatchId, 'match_status' => 'matched', 'updatetime' => $now,
            ]);
        }
        return ['ready' => $ready, 'total_amount_cent' => $total];
    }
}
