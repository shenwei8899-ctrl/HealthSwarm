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
    /** Read only the authenticated user's existing, current server menu version. */
    public function detail($package_sn = null)
    {
        $package_sn = $package_sn ?? $this->request->route('package_sn');
        return $this->execute(function () use ($package_sn) {
            $this->requireMethod('GET');
            $uid = $this->userId();
            $query = $this->request->get();
            $version = $query['version'] ?? null;
            if (!is_string($package_sn) || !preg_match('/^[A-Za-z0-9_-]{1,64}$/D', $package_sn) ||
                !is_scalar($version) || !preg_match('/^[1-9][0-9]{0,8}$/D', (string)$version)) {
                throw new \addons\shop\library\v5\DomainException('餐单编号或版本无效，请重新选择餐单', 40001, 400);
            }
            return (new MealCommerceService())->package($uid, $package_sn, (int)$version);
        });
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
