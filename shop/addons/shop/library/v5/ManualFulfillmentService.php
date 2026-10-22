<?php
namespace addons\shop\library\v5;
use think\Db;

class ManualFulfillmentService
{
    /** 后台操作员安排普通订单整体发货，锁定状态并保存物流审计。 */
    public function ship($sn, $carrier, $tracking, $adminId)
    {
        $carrier=trim((string)$carrier); $tracking=trim((string)$tracking);
        if ($adminId<=0 || $carrier==='' || $tracking==='' || strlen($carrier)>50 || strlen($tracking)>100) throw new DomainException('请填写物流公司和运单号',40001,400);
        Db::startTrans();
        try {
            $order=Db::name('shop_order')->where('order_sn',$sn)->lock(true)->find();
            if (!$order || $order['order_type']!=='normal') throw new DomainException('普通订单不存在',40409,404);
            $event=Db::name('shop_fulfillment_event')->where('event_id','manual_ship:'.$sn)->find();
            if ($event) {
                if ($event['carrier_code']!==$carrier || $event['tracking_no']!==$tracking) throw new DomainException('订单已发货，运单不同请走物流更正流程',40906,409);
                Db::commit(); return ['order_sn'=>$sn,'status'=>'shipped'];
            }
            if ((int)$order['paystate']!==1 || (int)$order['orderstate']!==0 || (int)$order['shippingstate']!==0) throw new DomainException('当前订单不可安排发货',40910,409);
            $ext=Db::name('shop_order_ext')->where('order_sn',$sn)->find();
            if (($ext && in_array($ext['payment_status'], ['refunding','partially_refunded','refunded'], true)) || Db::name('shop_order_aftersales')->where('order_id',$order['id'])->where('status','in',[1,2])->count()) throw new DomainException('订单存在售后或退款，不能安排发货',40910,409);
            Db::name('shop_order')->where('id',$order['id'])->update(['expressname'=>$carrier,'expressno'=>$tracking,'row_version'=>(int)$order['row_version']+1,'shippingstate'=>1,'shippingtime'=>time(),'updatetime'=>time()]);
            Db::name('shop_order_ext')->where('order_sn',$sn)->update(['business_status'=>'fulfilling','fulfillment_status'=>'shipped','updatetime'=>time()]);
            Db::name('shop_supplier_order')->where('platform_order_sn',$sn)->where('plan_batch_id',0)->where('status','in',['created','pushing','accepted','preparing'])->update(['status'=>'shipped','shipped_at'=>time(),'updatetime'=>time()]);
            Db::name('shop_fulfillment_event')->insert(['event_id'=>'manual_ship:'.$sn,'source_type'=>'admin','source_ref'=>(string)$adminId,'platform_order_sn'=>$sn,'carrier_code'=>$carrier,'tracking_no'=>$tracking,'source_status'=>'shipped','normalized_status'=>'shipped','occurred_at'=>time(),'description'=>'商家已安排发货','payload_json'=>Json::encode(['admin_id'=>$adminId]),'createtime'=>time()]);
            (new OutboxService())->append('order.shipped','order',$sn,1,'miniapp',['order_sn'=>$sn]);
            Db::commit(); return ['order_sn'=>$sn,'status'=>'shipped'];
        } catch (\Throwable $e) { Db::rollback(); throw $e; }
    }
}
