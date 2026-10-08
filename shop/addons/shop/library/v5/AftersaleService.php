<?php

namespace addons\shop\library\v5;

use think\Db;

class AftersaleService
{
    public function listRows($userId,$page=1,$size=20)
    {
        $query=Db::name('shop_order_aftersales')->where('user_id',(int)$userId);$total=$query->count();$items=$query->order('id','desc')->page(max(1,(int)$page),min(100,max(1,(int)$size)))->select();return ['items'=>$items,'total'=>$total,'page'=>(int)$page,'page_size'=>(int)$size];
    }

    public function eligibility($userId, $orderSn)
    {
        $order=Db::name('shop_order')->where('order_sn',$orderSn)->where('user_id',(int)$userId)->find();
        if(!$order)throw new DomainException('订单不存在',40409,404);
        $items=Db::name('shop_order_goods')->where('order_sn',$order['order_sn'])->select();
        $isPlan=$order['order_type']==='plan';
        foreach($items as &$item){$ext=Db::name('shop_order_goods_ext')->where('order_goods_id',$item['id'])->find();$item['delivery_batch_id']=$ext?(string)$ext['plan_batch_id']:null;$item['eligible']=(int)$order['paystate']===1 && in_array((int)$item['salestate'],[0,6],true);}
        return ['order_sn'=>$orderSn,'order_type'=>$order['order_type'],'items'=>$items,
            'allowed_reason_codes'=>$isPlan?['platform_non_delivery','wrong_item','missing_item','quality_issue','legal_mandatory']:['not_received','wrong_item','missing_item','quality_issue','damaged','other'],
            'plan_non_refundable_after_payment'=>$isPlan];
    }

    public function create($userId,array $payload,$requestId)
    {
        foreach(['order_sn','order_item_id','type','quantity','reason_code'] as $f)if(empty($payload[$f]))throw new DomainException('缺少必填字段: '.$f,40001,400);
        $order=Db::name('shop_order')->where('order_sn',$payload['order_sn'])->where('user_id',(int)$userId)->find();
        $item=$order?Db::name('shop_order_goods')->where('id',(int)$payload['order_item_id'])->where('order_sn',$order['order_sn'])->find():null;
        if(!$order||!$item)throw new DomainException('订单商品不存在',40409,404);
        if((int)$order['paystate']!==1||!in_array((int)$item['salestate'],[0,6],true))throw new DomainException('当前商品不可申请售后',40910,409);
        $policy=(new AftersalePolicyService())->assertUserApplicationAllowed($order['order_sn'],$item['id'],$payload['reason_code']);
        if($order['order_type']==='plan' && !empty($payload['batch_no'])){
            $po=Db::name('shop_service_plan_order')->where('order_id',$order['id'])->find();
            $batch=Db::name('shop_plan_delivery_batch')->where('plan_order_id',$po['id'])->where('batch_no',(int)$payload['batch_no'])->find();
            if(!$batch || (int)$batch['id']!==(int)$policy['batch_id'])throw new DomainException('售后商品与配送批次不匹配',40931,409);
        }
        $qty=min((int)$item['nums'],max(1,(int)$payload['quantity']));
        $ext=Db::name('shop_order_goods_ext')->where('order_goods_id',$item['id'])->find();
        $lineCent=$ext?(int)$ext['line_amount_cent']:(int)round((float)$item['realprice']*100);
        $refundCent=(int)floor($lineCent*$qty/max(1,(int)$item['nums']));
        $typeMap=['refund_only'=>1,'return_refund'=>2,'reship'=>3];
        if(!isset($typeMap[$payload['type']]))throw new DomainException('售后类型无效',40001,400);
        $sn=Identifiers::make('aftersale');$now=time();
        Db::startTrans();
        try{
            $id=Db::name('shop_order_aftersales')->insertGetId([
                'aftersale_sn'=>$sn,'user_id'=>$userId,'order_id'=>$order['id'],'order_goods_id'=>$item['id'],'type'=>$typeMap[$payload['type']],
                'nums'=>$qty,'realprice'=>number_format($refundCent/100,2,'.',''),'shippingfee'=>0,'refund'=>number_format($refundCent/100,2,'.',''),
                'reason'=>isset($payload['description'])?$payload['description']:$payload['reason_code'],'images'=>isset($payload['evidence_urls'])?implode(',',$payload['evidence_urls']):'',
                'status'=>1,'source_type'=>$policy['source_type'],'batch_id'=>$policy['batch_id'],'reason_code'=>$payload['reason_code'],'request_id'=>$requestId,'row_version'=>1,'createtime'=>$now,'updatetime'=>$now,
            ]);
            Db::name('shop_order_goods')->where('id',$item['id'])->update(['salestate'=>in_array($typeMap[$payload['type']],[2,3],true)?1:2]);
            Db::name('shop_order')->where('id',$order['id'])->update(['orderstate'=>4,'updatetime'=>$now]);
            if($policy['batch_id'])Db::name('shop_plan_delivery_batch')->where('id',$policy['batch_id'])->update(['aftersale_status'=>'pending','updatetime'=>$now]);
            (new OutboxService())->append('aftersale.created','aftersale',$sn,1,'operations',['aftersale_sn'=>$sn,'order_sn'=>$order['order_sn'],'request_id'=>$requestId]);
            Db::commit();
        }catch(\Exception $e){Db::rollback();throw $e;}
        return $this->detail($userId,$sn);
    }

    public function detail($userId,$sn)
    {
        $row=Db::name('shop_order_aftersales')->where(function($q)use($sn){$q->where('aftersale_sn',$sn);if(is_numeric($sn))$q->whereOr('id',(int)$sn);})->where('user_id',(int)$userId)->find();
        if(!$row)throw new DomainException('售后单不存在',40413,404);
        $row['evidence_urls']=$row['images']?explode(',',$row['images']):[];unset($row['images']);return $row;
    }

    public function cancel($userId,$sn)
    {
        $row=$this->detail($userId,$sn);if((int)$row['status']!==1)throw new DomainException('当前售后单不可撤销',40910,409);
        Db::startTrans();try{Db::name('shop_order_aftersales')->where('id',$row['id'])->update(['status'=>4,'cancelled_at'=>time(),'row_version'=>(int)$row['row_version']+1,'updatetime'=>time()]);Db::name('shop_order_goods')->where('id',$row['order_goods_id'])->update(['salestate'=>0]);$pending=Db::name('shop_order_aftersales')->where('order_id',$row['order_id'])->where('status','in',[1,2])->count();if(!$pending)Db::name('shop_order')->where('id',$row['order_id'])->update(['orderstate'=>0,'updatetime'=>time()]);Db::commit();}catch(\Exception $e){Db::rollback();throw $e;}return $this->detail($userId,$sn);
    }

    public function confirmResult($userId,$sn)
    {
        $row=$this->detail($userId,$sn);if(!in_array((int)$row['status'],[2,5],true))throw new DomainException('售后尚未处理完成',40910,409);Db::name('shop_order_aftersales')->where('id',$row['id'])->update(['result_confirmed_at'=>time(),'updatetime'=>time()]);return $this->detail($userId,$sn);
    }

    public function timeline($userId,$sn)
    {
        $row=$this->detail($userId,$sn);$events=[['type'=>'created','at'=>(int)$row['createtime'],'description'=>'售后申请已提交']];
        if((int)$row['status']===2)$events[]=['type'=>'approved','at'=>(int)$row['updatetime'],'description'=>'售后审核通过'];
        if((int)$row['status']===3)$events[]=['type'=>'rejected','at'=>(int)$row['updatetime'],'description'=>'售后审核拒绝'];
        if(!empty($row['cancelled_at']))$events[]=['type'=>'cancelled','at'=>(int)$row['cancelled_at'],'description'=>'用户已撤销售后'];
        $refund=Db::name('shop_refund_record')->where('aftersale_id',$row['id'])->order('id','desc')->find();
        if($refund)$events[]=['type'=>'refund_'.$refund['status'],'at'=>(int)($refund['success_at']?:$refund['updatetime']),'description'=>'退款状态：'.$refund['status']];
        return ['aftersale'=>$row,'events'=>$events];
    }
}
