<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\IdempotencyService;
use addons\shop\library\v5\PurchaseListService;
use addons\shop\library\v5\CheckoutService;
use think\Db;

class CommercePurchaseList extends Base
{
    public function index()
    {
        return $this->execute(function () {
            $page = max(1, (int)$this->request->get('page', 1));
            $size = min(100, max(1, (int)$this->request->get('page_size', 20)));
            $query = Db::name('shop_purchase_list')->where('user_id', $this->userId());
            if ($this->request->get('status') !== null && $this->request->get('status') !== '') {
                $query->where('status', $this->request->get('status'));
            }
            $total = $query->count();
            $items = $query->order('id', 'desc')->page($page, $size)->select();
            return ['items' => $items, 'total' => $total, 'page' => $page, 'page_size' => $size];
        });
    }

    public function detail($purchase_list_sn = null)
    {
        return $this->execute(function () use ($purchase_list_sn) {
            return (new PurchaseListService())->getBySn($purchase_list_sn, $this->userId());
        });
    }

    public function pantry($purchase_list_sn = null)
    {
        return $this->execute(function () use ($purchase_list_sn) {
            $this->requireMethod('PUT');
            $payload = $this->input();
            $userId = $this->userId();
            return (new IdempotencyService())->run('commerce.purchase.pantry', 'miniapp:' . $userId, $this->request->header('idempotency-key'), $payload, function () use ($userId, $purchase_list_sn, $payload) {
                return (new PurchaseListService())->updatePantry($userId, $purchase_list_sn, $payload['version'], isset($payload['items']) ? $payload['items'] : []);
            });
        });
    }

    public function confirm($purchase_list_sn = null)
    {
        return $this->execute(function () use ($purchase_list_sn) {
            $this->requireMethod('POST');
            $payload = $this->input();
            $userId = $this->userId();
            return (new IdempotencyService())->run('commerce.purchase.confirm', 'miniapp:' . $userId, $this->request->header('idempotency-key'), $payload, function () use ($userId, $purchase_list_sn, $payload) {
                return (new PurchaseListService())->confirm($userId, $purchase_list_sn, $payload['version']);
            });
        });
    }

    public function rematch($purchase_list_sn = null)
    {
        return $this->execute(function () use ($purchase_list_sn) { $p=$this->input(); $uid=$this->userId(); return (new IdempotencyService())->run('commerce.purchase.rematch','miniapp:'.$uid,$this->request->header('idempotency-key'),$p,function()use($uid,$purchase_list_sn,$p){return (new PurchaseListService())->rematch($uid,$purchase_list_sn,$p['version']);}); });
    }

    public function selectMatch($purchase_list_sn = null, $item_id = null)
    {
        return $this->execute(function () use ($purchase_list_sn,$item_id) { $this->requireMethod('PUT');$p=$this->input();$uid=$this->userId();return(new IdempotencyService())->run('commerce.purchase.select_match','miniapp:'.$uid,$this->request->header('idempotency-key'),['purchase_list_sn'=>$purchase_list_sn,'item_id'=>$item_id]+$p,function()use($uid,$purchase_list_sn,$item_id,$p){return (new PurchaseListService())->selectMatch($uid,$purchase_list_sn,$item_id,$p['match_id'],$p['version']);}); });
    }

    public function cart($purchase_list_sn = null)
    {
        return $this->execute(function () use ($purchase_list_sn) { $p=$this->input(); $uid=$this->userId(); return (new IdempotencyService())->run('commerce.purchase.cart','miniapp:'.$uid,$this->request->header('idempotency-key'),$p,function()use($uid,$purchase_list_sn,$p){return (new PurchaseListService())->addToCart($uid,$purchase_list_sn,$p['version']);}); });
    }

    public function checkout($purchase_list_sn = null)
    {
        return $this->execute(function () use ($purchase_list_sn) {
            $this->requireMethod('POST');$p=$this->input();$uid=$this->userId();
            return(new IdempotencyService())->run('commerce.purchase.checkout','miniapp:'.$uid,$this->request->header('idempotency-key'),['purchase_list_sn'=>$purchase_list_sn]+$p,function()use($uid,$purchase_list_sn,$p){
            $list=(new PurchaseListService())->getBySn($purchase_list_sn,$uid); $items=[];
            foreach($list['items'] as $item){foreach($item['matches'] as $m){if($m['is_selected'])$items[]=['sku_id'=>$m['sku_id'],'quantity'=>$m['required_pack_count']];}}
            $p['source_type']='purchase_list';$p['source_ref']=$purchase_list_sn;$p['source_version']=$list['version'];$p['items']=$items;
            return (new CheckoutService())->preview($uid,$p,['request_id'=>$this->requestId,'ip'=>$this->request->ip(),'device_id'=>$this->request->header('x-device-id')]);
            },900);
        });
    }
}
