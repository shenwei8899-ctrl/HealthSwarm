<?php
namespace addons\shop\controller\api\v1;
use addons\shop\library\v5\AftersaleService;
use addons\shop\library\v5\IdempotencyService;
class CommerceAftersale extends Base
{
    public function forOrder($order_sn = null)
    {
        $order_sn = $order_sn ?? $this->request->route('order_sn');
        return $this->execute(function () use ($order_sn) {
            $uid = $this->userId();
            $order = \think\Db::name('shop_order')->where('order_sn', $order_sn)->where('user_id', $uid)->find();
            if (!$order) throw new \addons\shop\library\v5\DomainException('订单不存在', 40409, 404);
            return ['items' => \think\Db::name('shop_order_aftersales')->where('order_id', $order['id'])->where('user_id', $uid)->order('id', 'desc')->select()];
        });
    }
    public function index(){return $this->execute(function(){return(new AftersaleService())->listRows($this->userId(),$this->request->get('page',1),$this->request->get('page_size',20));});}
    public function eligibility($order_sn=null){
        $order_sn = $order_sn ?? $this->request->route('order_sn');return $this->execute(function()use($order_sn){return(new AftersaleService())->eligibility($this->userId(),$order_sn);});}
    public function create(){return $this->execute(function(){$p=$this->input();$uid=$this->userId();return(new IdempotencyService())->run('commerce.aftersale.create','miniapp:'.$uid,$this->request->header('idempotency-key'),$p,function()use($uid,$p){return(new AftersaleService())->create($uid,$p,$this->requestId);});});}
    public function detail($id=null){
        $id = $id ?? $this->request->route('id');return $this->execute(function()use($id){return(new AftersaleService())->detail($this->userId(),$id);});}
    public function cancel($id=null){
        $id = $id ?? $this->request->route('id');return $this->execute(function()use($id){$this->requireMethod('POST');$p=$this->input();$uid=$this->userId();return(new IdempotencyService())->run('commerce.aftersale.cancel','miniapp:'.$uid,$this->request->header('idempotency-key'),['aftersale_id'=>$id]+$p,function()use($uid,$id){return(new AftersaleService())->cancel($uid,$id);});});}
    public function confirm($id=null){
        $id = $id ?? $this->request->route('id');return $this->execute(function()use($id){$this->requireMethod('POST');$p=$this->input();$uid=$this->userId();return(new IdempotencyService())->run('commerce.aftersale.confirm','miniapp:'.$uid,$this->request->header('idempotency-key'),['aftersale_id'=>$id]+$p,function()use($uid,$id){return(new AftersaleService())->confirmResult($uid,$id);});});}
    public function timeline($id=null){
        $id = $id ?? $this->request->route('id');return $this->execute(function()use($id){return(new AftersaleService())->timeline($this->userId(),$id);});}
}
