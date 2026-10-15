<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\CartService;
use addons\shop\library\v5\IdempotencyService;

class CommerceCart extends Base
{
    public function index()
    {
        return $this->execute(function () { return (new CartService())->listItems($this->userId()); });
    }

    public function add()
    {
        return $this->execute(function () {
            $payload=$this->input(); $uid=$this->userId();
            if (!isset($payload['sku_id'], $payload['quantity']) || (int)$payload['sku_id'] <= 0 || (isset($payload['source']) && !is_array($payload['source']))) {
                throw new \addons\shop\library\v5\DomainException('商品和购买数量无效', 40001, 400);
            }
            return (new IdempotencyService())->run('commerce.cart.add','miniapp:'.$uid,$this->request->header('idempotency-key'),$payload,function()use($uid,$payload){
                return (new CartService())->add($uid,$payload['sku_id'],$payload['quantity'],isset($payload['source'])?$payload['source']:[]);
            });
        });
    }

    public function update($id=null)
    {
        $id = $id ?? $this->request->route('id');
        return $this->execute(function () use ($id) {
            $this->requireMethod('PUT'); $p=$this->input(); $uid=$this->userId();
            if (!isset($p['quantity'], $p['version'])) throw new \addons\shop\library\v5\DomainException('缺少数量或版本', 40001, 400);
            return (new IdempotencyService())->run('commerce.cart.update','miniapp:'.$uid,$this->request->header('idempotency-key'),['cart_item_id'=>$id]+$p,function()use($uid,$id,$p){return (new CartService())->update($uid,$id,$p['quantity'],$p['version']);});
        });
    }

    public function remove($id=null)
    {
        $id = $id ?? $this->request->route('id');
        return $this->execute(function () use ($id) {
            $this->requireMethod('DELETE'); $p=$this->input(); $uid=$this->userId();
            return (new IdempotencyService())->run('commerce.cart.remove','miniapp:'.$uid,$this->request->header('idempotency-key'),['cart_item_id'=>$id]+$p,function()use($uid,$id,$p){return (new CartService())->remove($uid,$id,isset($p['version'])?$p['version']:null);});
        });
    }

    public function validateCart()
    {
        return $this->execute(function () { return (new CartService())->listItems($this->userId()); });
    }

    public function selection($id = null)
    {
        $id = $id ?? $this->request->route('id');
        return $this->execute(function () use ($id) {
            $p = $this->input(); $uid = $this->userId();
            if (!isset($p['selected'], $p['version'])) throw new \addons\shop\library\v5\DomainException('缺少勾选状态或版本', 40001, 400);
            return (new IdempotencyService())->run('commerce.cart.selection', 'miniapp:' . $uid, $this->request->header('idempotency-key'), ['id' => $id] + $p, function () use ($uid, $id, $p) {
                return (new CartService())->select($uid, $id, $p['selected'], $p['version']);
            });
        });
    }
}
