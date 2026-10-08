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
            return (new IdempotencyService())->run('commerce.cart.add','miniapp:'.$uid,$this->request->header('idempotency-key'),$payload,function()use($uid,$payload){
                return (new CartService())->add($uid,$payload['sku_id'],$payload['quantity'],isset($payload['source'])?$payload['source']:[]);
            });
        });
    }

    public function update($id=null)
    {
        return $this->execute(function () use ($id) { $this->requireMethod('PUT');$p=$this->input();$uid=$this->userId();return(new IdempotencyService())->run('commerce.cart.update','miniapp:'.$uid,$this->request->header('idempotency-key'),['cart_item_id'=>$id]+$p,function()use($uid,$id,$p){return (new CartService())->update($uid,$id,$p['quantity'],$p['version']);}); });
    }

    public function remove($id=null)
    {
        return $this->execute(function () use ($id) { $this->requireMethod('DELETE');$p=$this->input();$uid=$this->userId();return(new IdempotencyService())->run('commerce.cart.remove','miniapp:'.$uid,$this->request->header('idempotency-key'),['cart_item_id'=>$id]+$p,function()use($uid,$id){return (new CartService())->remove($uid,$id);}); });
    }

    public function validateCart()
    {
        return $this->execute(function () { return (new CartService())->listItems($this->userId()); });
    }
}
