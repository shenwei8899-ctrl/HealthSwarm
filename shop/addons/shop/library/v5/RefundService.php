<?php

namespace addons\shop\library\v5;

use think\Db;

class RefundService
{
    public function approveAftersale($aftersaleId, $adminId, $comment, $requestId)
    {
        Db::startTrans();
        try {
            $after=Db::name('shop_order_aftersales')->where('id',(int)$aftersaleId)->lock(true)->find();
            if(!$after || (int)$after['status']!==1)throw new DomainException('售后单不存在或已处理',40910,409);
            $order=Db::name('shop_order')->where('id',$after['order_id'])->find();
            (new AftersalePolicyService())->assertAdminRefundAllowed($order['order_sn'],$after);
            if ((int)$after['type'] === 3) {
                Db::name('shop_order_aftersales')->where('id',$after['id'])->update(['status'=>2,'mark'=>$comment,'row_version'=>(int)$after['row_version']+1,'updatetime'=>time()]);
                if($after['batch_id'])Db::name('shop_plan_delivery_batch')->where('id',$after['batch_id'])->update(['aftersale_status'=>'reship_pending','updatetime'=>time()]);
                (new OutboxService())->append('aftersale.reship.approved','aftersale',$after['aftersale_sn']?:('id:'.$after['id']),(int)$after['row_version']+1,'operations',['order_sn'=>$order['order_sn'],'batch_id'=>(int)$after['batch_id']]);
                Db::commit();
                return ['aftersale_sn'=>$after['aftersale_sn'],'status'=>'approved','resolution'=>'reship'];
            }
            $amountCent=(int)round((float)$after['refund']*100);
            $payment=Db::name('shop_payment_record')->where('order_sn',$order['order_sn'])->where('status','paid')->order('id','desc')->find();
            $refundSn=Identifiers::make('refund');$now=time();
            $refundId=Db::name('shop_refund_record')->insertGetId([
                'refund_sn'=>$refundSn,'order_sn'=>$order['order_sn'],'payment_id'=>$payment?$payment['id']:0,'aftersale_id'=>$after['id'],
                'refund_amount_cent'=>$amountCent,'currency'=>'CNY','reason'=>$after['reason'],'status'=>'created','requested_at'=>$now,
                'request_id'=>$requestId,'createtime'=>$now,'updatetime'=>$now,
            ]);
            Db::name('shop_refund_allocation')->insert([
                'refund_id'=>$refundId,'allocation_type'=>$after['source_type']==='plan_exception'?'plan_batch':'order_item',
                'batch_id'=>(int)$after['batch_id'],'order_goods_id'=>(int)$after['order_goods_id'],'original_amount_cent'=>$amountCent,
                'fulfilled_amount_cent'=>$after['source_type']==='plan_exception'?$amountCent:0,'refundable_amount_cent'=>$amountCent,'refund_amount_cent'=>$amountCent,
                'formula_version'=>'v5-line-prorata-1','calculation_json'=>Json::encode(['quantity'=>(int)$after['nums']]),
                'exception_reason_code'=>$after['reason_code'],'createtime'=>$now,
            ]);
            Db::name('shop_order_aftersales')->where('id',$after['id'])->update(['status'=>2,'mark'=>$comment,'row_version'=>(int)$after['row_version']+1,'updatetime'=>$now]);
            if($after['batch_id'])Db::name('shop_plan_delivery_batch')->where('id',$after['batch_id'])->update(['aftersale_status'=>'approved','updatetime'=>$now]);
            Db::commit();
        }catch(\Exception $e){Db::rollback();throw $e;}

        try {
            $this->submitWechat($refundSn);
        } catch (\Exception $e) {
            Db::name('shop_refund_record')->where('refund_sn',$refundSn)->update(['status'=>'failed','failure_code'=>'submit_failed','failure_message'=>mb_substr($e->getMessage(),0,500),'updatetime'=>time()]);
            (new ExceptionService())->open('refund_submit:'.$refundSn,'payment','refund_submit_failed',$e->getMessage(),['resource_type'=>'refund','resource_ref'=>$refundSn,'order_sn'=>$order['order_sn']],[],'high');
        }
        return Db::name('shop_refund_record')->where('refund_sn',$refundSn)->find();
    }

    public function rejectAftersale($aftersaleId,$adminId,$comment)
    {
        $after=Db::name('shop_order_aftersales')->where('id',(int)$aftersaleId)->where('status',1)->find();
        if(!$after)throw new DomainException('售后单不存在或已处理',40910,409);
        Db::name('shop_order_aftersales')->where('id',$after['id'])->update(['status'=>3,'mark'=>$comment,'row_version'=>(int)$after['row_version']+1,'updatetime'=>time()]);
        Db::name('shop_order_goods')->where('id',$after['order_goods_id'])->update(['salestate'=>6]);
        if($after['batch_id'])Db::name('shop_plan_delivery_batch')->where('id',$after['batch_id'])->update(['aftersale_status'=>'rejected','updatetime'=>time()]);
        return Db::name('shop_order_aftersales')->where('id',$after['id'])->find();
    }

    public function submitWechat($refundSn)
    {
        $refund=Db::name('shop_refund_record')->where('refund_sn',$refundSn)->find();
        $order=$refund?Db::name('shop_order')->where('order_sn',$refund['order_sn'])->find():null;
        if(!$refund||!$order)throw new DomainException('退款记录不存在',40414,404);
        if(in_array($refund['status'],['submitted','processing','success'],true))return $refund;
        $result=\addons\shop\library\service\WechatPayService::refund([
            'order_id'=>(int)$order['id'],
            'refund_sn'=>$refund['refund_sn'],
            'amount'=>number_format((int)$refund['refund_amount_cent']/100,2,'.',''),
        ]);
        Db::name('shop_refund_record')->where('id',$refund['id'])->update([
            'status'=>'processing','channel_refund_id'=>$result['gateway_refund_id']?:null,'updatetime'=>time()
        ]);
        Db::name('shop_order_ext')->where('order_sn',$order['order_sn'])->update(['payment_status'=>'refunding','updatetime'=>time()]);
        return Db::name('shop_refund_record')->where('id',$refund['id'])->find();
    }

    public function queryWechat($refundSn)
    {
        $refund=Db::name('shop_refund_record')->where('refund_sn',$refundSn)->find();
        $order=$refund?Db::name('shop_order')->where('order_sn',$refund['order_sn'])->find():null;
        if(!$refund||!$order)throw new DomainException('退款记录不存在',40414,404);
        if($refund['status']==='success')return $refund;
        $response=\addons\shop\library\service\WechatPayService::queryRefund($refund['refund_sn']);
        $status='';
        if(isset($response['refund_status_0']))$status=strtoupper((string)$response['refund_status_0']);
        elseif(isset($response['refund_status']))$status=strtoupper((string)$response['refund_status']);
        $channelId=isset($response['refund_id_0'])?(string)$response['refund_id_0']:(isset($response['refund_id'])?(string)$response['refund_id']:'');
        Db::name('shop_refund_record')->where('id',$refund['id'])->update(['last_query_at'=>time(),'updatetime'=>time()]);
        if($status==='SUCCESS')return $this->onWechatResult($refundSn,'SUCCESS',$channelId);
        if(in_array($status,['REFUNDCLOSE','CHANGE'],true))return $this->onWechatResult($refundSn,$status,$channelId);
        return Db::name('shop_refund_record')->where('id',$refund['id'])->find();
    }

    public function onWechatResult($refundSn,$status,$channelRefundId,$notifyId='')
    {
        Db::startTrans();
        try{
            $refund=Db::name('shop_refund_record')->where('refund_sn',$refundSn)->lock(true)->find();
            if(!$refund)throw new DomainException('退款记录不存在',40414,404);
            $success=strtoupper($status)==='SUCCESS';
            if($refund['status']==='success'){Db::commit();return $refund;}
            Db::name('shop_refund_record')->where('id',$refund['id'])->update(['status'=>$success?'success':'failed','channel_refund_id'=>$channelRefundId?:null,'notify_id'=>$notifyId,'success_at'=>$success?time():0,'updatetime'=>time()]);
            if($success){
                $after=Db::name('shop_order_aftersales')->where('id',$refund['aftersale_id'])->find();
                Db::name('shop_order_goods')->where('id',$after['order_goods_id'])->update(['salestate'=>5]);
                if($after['batch_id']){
                    Db::name('shop_plan_delivery_batch')->where('id',$after['batch_id'])->setInc('exception_refunded_amount_cent',$refund['refund_amount_cent']);
                    $batch=Db::name('shop_plan_delivery_batch')->where('id',$after['batch_id'])->find();
                    Db::name('shop_service_plan_order')->where('id',$batch['plan_order_id'])->setInc('exception_refunded_amount_cent',$refund['refund_amount_cent']);
                }
                Db::name('shop_order_ext')->where('order_sn',$refund['order_sn'])->update(['payment_status'=>'partially_refunded','updatetime'=>time()]);
            }
            Db::commit();return Db::name('shop_refund_record')->where('id',$refund['id'])->find();
        }catch(\Exception $e){Db::rollback();throw $e;}
    }
}
