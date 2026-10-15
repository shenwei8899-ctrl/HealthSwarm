<?php
namespace addons\shop\library\v5;

use think\Db;

class MealCommerceService
{
    /** 从当前会员已保存的推荐版本读取一餐，价格和库存重新查询。 */
    public function current($uid, $date, $meal)
    {
        if (!preg_match('/^\d{4}-\d{2}-\d{2}$/D', (string)$date) || !in_array($meal, ['breakfast','lunch','dinner'], true)) {
            throw new DomainException('餐次或日期无效', 40001, 400);
        }
        $rows = Db::name('shop_recommendation_package')->where('user_id', $uid)->where('meal_date', $date)->order('id', 'desc')->limit(30)->select();
        foreach ($rows as $row) {
            $version = Db::name('shop_recommendation_package_version')->where('package_id', $row['id'])->where('version_no', $row['current_version'])->find();
            $recipes = Json::decode($version['recipes_snapshot_json'] ?? '', []);
            if ($recipes && ($recipes[0]['meal_type'] ?? '') === $meal) return $this->package($uid, $row['package_sn'], $row['current_version']);
        }
        return ['available'=>false, 'date'=>$date, 'meal'=>$meal, 'message'=>'这一餐尚未有服务端确认的菜单，请等待营养师生成或运营接入。', 'dishes'=>[], 'items'=>[]];
    }

    /** 只接受服务器已有且归属当前会员的菜谱版本，客户端不能提供菜谱快照。 */
    public function package($uid, $sn, $versionNo)
    {
        $row = Db::name('shop_recommendation_package')->where('package_sn', $sn)->where('user_id', $uid)->find();
        if (!$row) throw new DomainException('本餐菜单不存在', 40402, 404);
        if ((int)$row['current_version'] !== (int)$versionNo) throw new DomainException('菜单已更新，请重新确认本餐', 40906, 409);
        $version = Db::name('shop_recommendation_package_version')->where('package_id', $row['id'])->where('version_no', $versionNo)->find();
        if (!$version) throw new DomainException('菜单版本不存在',40402,404);
        $recipes = Json::decode($version['recipes_snapshot_json'], []);
        $issues = Json::decode($version['issues_json'], []);
        $items = [];
        foreach (Db::name('shop_recommendation_package_item')->where('package_version_id', $version['id'])->order('sort', 'asc')->select() as $item) {
            try {
                $sku = (new CatalogService())->getSku($item['sku_id'], false);
                if ((int)$sku['available_quantity'] < (int)$item['quantity']) throw new DomainException('本餐食材库存不足', 40904, 409);
                $items[] = ['quantity'=>(int)$item['quantity'], 'ingredient_id'=>(string)$item['ingredient_id'], 'sku'=>$sku];
            } catch (DomainException $e) { $issues[] = ['issue_code'=>'sku_unavailable', 'sku_id'=>(string)$item['sku_id'], 'message'=>$e->getMessage()]; }
        }
        $completeRecipes = (bool)$recipes;
        foreach ($recipes as $recipe) {
            if (empty($recipe['recipe_ref']) || empty($recipe['recipe_version']) || empty($recipe['steps']) || !is_array($recipe['steps']) || empty($recipe['ingredients'])) $completeRecipes = false;
        }
        if (!$completeRecipes) $issues[] = ['issue_code'=>'recipe_incomplete', 'message'=>'菜谱版本或制作步骤尚未接入'];
        $available = $row['status'] === 'available' && $row['trade_status'] === 'passed' && $row['nutrition_status'] === 'passed' && (int)$row['expires_at'] > time() && $completeRecipes && !$issues && (bool)$items;
        return ['available'=>$available, 'package_sn'=>$sn, 'package_version'=>(int)$versionNo, 'menu_version_ref'=>$version['menu_version_ref'],
            'date'=>$row['meal_date'], 'meal'=>$recipes[0]['meal_type'] ?? '', 'dishes'=>$recipes, 'items'=>$items, 'issues'=>$issues,
            'nutrition_validation_status'=>$row['nutrition_status'], 'is_local_fixture'=>$version['created_by_type'] === 'local_fixture', 'expires_at'=>date(DATE_ATOM,(int)$row['expires_at'])];
    }

    /** 把审核过的本餐 SKU 加入本人购物车，保留其他采购项。 */
    public function addToCart($uid, $sn, $versionNo)
    {
        Db::startTrans();
        try {
            Db::name('user')->where('id', $uid)->lock(true)->find();
            Db::name('shop_recommendation_package')->where('package_sn', $sn)->where('user_id', $uid)->lock(true)->find();
            $menu = $this->package($uid, $sn, $versionNo);
            if (!$menu['available']) throw new DomainException('本餐菜单或商品尚不可购买', 40917, 409, ['issues'=>$menu['issues']]);
            Db::name('shop_carts')->where('user_id', $uid)->where('sceneval', 1)->where('is_selected', 1)->update(['is_selected'=>0, 'row_version'=>Db::raw('row_version+1')]);
            foreach ($menu['items'] as $item) {
                $existing=Db::name('shop_carts')->where('user_id',$uid)->where('sceneval',1)->where('goods_sku_id',$item['sku']['sku_id'])->where('source_type','recommendation_package')->where('source_ref',$sn)->find();
                if ($existing) {
                    Db::name('shop_carts')->where('id',$existing['id'])->update(['nums'=>$item['quantity'],'source_version'=>(int)$versionNo,'is_selected'=>1,'row_version'=>Db::raw('row_version+1'),'updatetime'=>time()]);
                } else {
                    (new CartService())->add($uid, $item['sku']['sku_id'], $item['quantity'], ['source_type'=>'recommendation_package', 'source_ref'=>$sn, 'source_version'=>$versionNo]);
                }
            }
            Db::commit();
            return (new CartService())->listItems($uid);
        } catch (\Throwable $e) { Db::rollback(); throw $e; }
    }

    /** 将服务端菜谱固定到报价，数量调整不会改写菜谱或营养结论。 */
    public function quoteSnapshot($uid, array $payload, array $pricing)
    {
        if (empty($payload['meal_package_sn'])) return null;
        $menu = $this->package($uid, $payload['meal_package_sn'], $payload['meal_package_version'] ?? 0);
        if (!$menu['available']) throw new DomainException('本餐依据已变化，请重新确认', 40917, 409, ['issues'=>$menu['issues']]);
        $allowed = array_map(function ($i) { return (string)$i['sku']['sku_id']; }, $menu['items']);
        foreach ($pricing['items'] as $item) if (!in_array((string)$item['sku_id'], $allowed, true)) throw new DomainException('所选商品不属于当前菜单，请分别结算', 40906, 409);
        foreach ($pricing['cart_items'] as $item) {
            if (($item['source_type'] ?? '') !== 'recommendation_package' || ($item['source_ref'] ?? '') !== $menu['package_sn'] || (int)($item['source_version'] ?? 0) !== $menu['package_version']) throw new DomainException('购物车菜单来源已变化，请重新采购', 40906, 409);
        }
        unset($menu['items']);
        $menu['purchased_sku_ids'] = array_map(function ($i) { return (string)$i['sku_id']; }, $pricing['items']);
        return $menu;
    }

    /** 做饭只读取已付款且已收货订单的固定菜谱。 */
    public function cooking($uid, $orderSn)
    {
        $order = Db::name('shop_order')->where('order_sn', $orderSn)->where('user_id', $uid)->find();
        if (!$order) throw new DomainException('订单不存在', 40409, 404);
        if ((int)$order['paystate'] !== 1 || (int)$order['shippingstate'] !== 2) throw new DomainException('收货后才能进入制作与记餐', 40910, 409);
        $ext = Db::name('shop_order_ext')->where('order_sn', $orderSn)->find();
        $pricing = Json::decode($ext['pricing_snapshot_json'], []);
        if (empty($pricing['meal_snapshot']['dishes'])) throw new DomainException('这笔订单没有关联菜谱，可自行安排制作', 40414, 404);
        return ['order_sn'=>$orderSn, 'meal_snapshot'=>$pricing['meal_snapshot']];
    }
}
