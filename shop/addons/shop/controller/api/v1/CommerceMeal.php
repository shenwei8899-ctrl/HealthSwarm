<?php
namespace addons\shop\controller\api\v1;
use addons\shop\library\v5\MealCommerceService;
use addons\shop\library\v5\IdempotencyService;

class CommerceMeal extends Base
{
    public function current()
    {
        return $this->execute(function () { return (new MealCommerceService())->current($this->userId(), $this->request->get('date', date('Y-m-d')), $this->request->get('meal', 'dinner')); });
    }
    public function cart()
    {
        return $this->execute(function () {
            $this->requireMethod('POST'); $uid=$this->userId(); $p=$this->input();
            return (new IdempotencyService())->run('commerce.meal.cart', 'miniapp:'.$uid, $this->request->header('idempotency-key'), $p, function () use ($uid,$p) {
                return (new MealCommerceService())->addToCart($uid, $p['package_sn'] ?? '', $p['package_version'] ?? 0);
            });
        });
    }
    public function cooking($order_sn=null)
    {
        $order_sn=$order_sn??$this->request->route('order_sn');
        return $this->execute(function () use ($order_sn) { return (new MealCommerceService())->cooking($this->userId(), $order_sn); });
    }
}
