<?php
namespace addons\shop\controller\api\v1;
use addons\shop\library\v5\AftersaleService;
use addons\shop\library\v5\IdempotencyService;
class CommerceAftersale extends Base
{
    public function index(){return $this->execute(function(){return(new AftersaleService())->listRows($this->userId(),$this->request->get('page',1),$this->request->get('page_size',20));});}
    public function eligibility($order_sn=null){return $this->execute(function()use($order_sn){return(new AftersaleService())->eligibility($this->userId(),$order_sn);});}
    public function create(){return $this->execute(function(){$p=$this->input();$uid=$this->userId();return(new IdempotencyService())->run('commerce.aftersale.create','miniapp:'.$uid,$this->request->header('idempotency-key'),$p,function()use($uid,$p){return(new AftersaleService())->create($uid,$p,$this->requestId);});});}
    public function detail($id=null){return $this->execute(function()use($id){return(new AftersaleService())->detail($this->userId(),$id);});}
    public function cancel($id=null){return $this->execute(function()use($id){$this->requireMethod('POST');$p=$this->input();$uid=$this->userId();return(new IdempotencyService())->run('commerce.aftersale.cancel','miniapp:'.$uid,$this->request->header('idempotency-key'),['aftersale_id'=>$id]+$p,function()use($uid,$id){return(new AftersaleService())->cancel($uid,$id);});});}
    public function confirm($id=null){return $this->execute(function()use($id){$this->requireMethod('POST');$p=$this->input();$uid=$this->userId();return(new IdempotencyService())->run('commerce.aftersale.confirm','miniapp:'.$uid,$this->request->header('idempotency-key'),['aftersale_id'=>$id]+$p,function()use($uid,$id){return(new AftersaleService())->confirmResult($uid,$id);});});}
    public function timeline($id=null){return $this->execute(function()use($id){return(new AftersaleService())->timeline($this->userId(),$id);});}
}
