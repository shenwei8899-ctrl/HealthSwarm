<?php

namespace addons\shop\library\v5;

use think\Db;

/** 剩余批次变更先保存预览，确认时重新加锁校验，不改购买快照。 */
class PlanChangeService
{
    public function preview($userId, $orderSn, $type, array $payload, $requestId)
    {
        if (!in_array($type,['resume','cancel_remaining'],true)) throw new DomainException('计划变更类型无效',40001,400);
        Db::startTrans();
        try {
            $order=$this->lockOrder($userId,$orderSn);
            if ((int)$order['row_version']!==(int)($payload['version'] ?? 0)) throw new DomainException('计划订单已变化，请刷新',40906,409);
            $preview=$this->calculate($userId,$order,$type,$payload);
            $sn=Identifiers::make('change');$now=time();
            Db::name('shop_plan_change_request')->insert([
                'change_request_sn'=>$sn,'plan_order_id'=>$order['id'],'request_type'=>$type,
                'target_batch_ids_json'=>Json::encode(array_column($preview['batches'],'id')),'base_version'=>$order['row_version'],
                'request_payload_json'=>Json::encode($payload),'request_user_id'=>$userId,'status'=>'awaiting_confirmation',
                'preview_json'=>Json::encode($preview),'expires_at'=>$now+300,
                'request_id'=>$requestId,'createtime'=>$now,'updatetime'=>$now,
            ]);
            Db::commit();
            return ['change_request_sn'=>$sn,'expires_at'=>$now+300,'version'=>(int)$order['row_version']]+$preview;
        } catch (\Throwable $error) { Db::rollback();throw $error; }
    }

    public function confirm($userId, $orderSn, $changeSn, $requestId)
    {
        Db::startTrans();
        try {
            $order=$this->lockOrder($userId,$orderSn);
            $change=Db::name('shop_plan_change_request')->where('plan_order_id',$order['id'])->where('change_request_sn',$changeSn)->lock(true)->find();
            if (!$change) throw new DomainException('变更预览不存在',40410,404);
            if ($change['status']==='processed') { Db::commit();return Json::decode($change['preview_json'],[]); }
            if ($change['status']!=='awaiting_confirmation' || (int)$change['expires_at']<=time() || (int)$change['base_version']!==(int)$order['row_version']) throw new DomainException('变更预览已过期，请重新查看',40906,409);
            (new PlanScheduleService())->lockCapacity();
            $payload=Json::decode($change['request_payload_json'],[]);
            $preview=$this->calculate($userId,$order,$change['request_type'],$payload);
            if (Json::canonical($preview)!==Json::canonical(Json::decode($change['preview_json'],[]))) throw new DomainException('批次状态、供货或配送条件已变化，请重新预览',40906,409);
            $result=$change['request_type']==='resume' ? $this->resume($order,$preview) : $this->cancel($order,$preview,$requestId);
            $result['change_request_sn']=$changeSn;
            Db::name('shop_plan_change_request')->where('id',$change['id'])->update(['status'=>'processed','processed_at'=>time(),'preview_json'=>Json::encode($result),'updatetime'=>time()]);
            (new OutboxService())->append('service_plan.'.$change['request_type'],'plan_order',$orderSn,(int)$order['row_version']+1,'agent',$result);
            Db::commit();return $result;
        } catch (\Throwable $error) { Db::rollback();throw $error; }
    }

    public function resumeDates($userId,$orderSn,$addressId,$slotId)
    {
        $order=Db::name('shop_service_plan_order')->where('order_sn',$orderSn)->where('user_id',$userId)->find();
        if (!$order || $order['status']!=='paused') throw new DomainException('计划订单未暂停',40927,409);
        $count=(int)Db::name('shop_plan_delivery_batch')->where('plan_order_id',$order['id'])->where('status','paused')->count();
        if (!$count) return ['items'=>[]];
        $delivery=(new DeliveryService())->validateAddress($userId,$addressId,$slotId);
        return (new PlanScheduleService())->availableDates((new PlanPolicyService())->current(),$delivery,$count,true,$order['id']);
    }

    protected function calculate($userId,array $order,$type,array $payload)
    {
        if (!in_array($order['status'],['active','paused'],true)) throw new DomainException('当前计划状态不能变更剩余批次',40927,409);
        $batches=Db::name('shop_plan_delivery_batch')->where('plan_order_id',$order['id'])->order('batch_no','asc')->lock(true)->select();
        $eligible=array_values(array_filter($batches,[PlanScheduleService::class,'changeable']));
        if ($type==='resume') $eligible=array_values(array_filter($eligible,function ($batch) {return $batch['status']==='paused';}));
        if (!$eligible) throw new DomainException('没有可变更的剩余批次',40927,409);
        $result=['type'=>$type,'order_sn'=>$order['order_sn'],'batches'=>[]];
        if ($type==='cancel_remaining') {
            $result+=['goods_amount_cent'=>0,'shipping_fee_cent'=>0,'service_fee_cent'=>0,'discount_amount_cent'=>0,'refund_amount_cent'=>0];
            foreach ($eligible as $batch) {
                $amount=(int)$batch['allocated_pay_amount_cent']-(int)$batch['exception_refunded_amount_cent'];
                if ($amount<0) throw new DomainException('批次退款金额需要复核',40935,409);
                $result['batches'][]=['id'=>(int)$batch['id'],'batch_no'=>(int)$batch['batch_no'],'version'=>(int)$batch['row_version'],'refund_amount_cent'=>$amount];
                foreach (['goods_amount_cent','shipping_fee_cent','service_fee_cent','discount_amount_cent'] as $field) $result[$field]+=(int)$batch[$field];
                $result['refund_amount_cent']+=$amount;
            }
            return $result;
        }
        if ($order['status']!=='paused') throw new DomainException('当前计划未暂停',40927,409);
        $purchased=Json::decode($order['policy_snapshot_json'],[]);
        if (!$purchased || time()>(int)$order['pause_started_at']+$purchased['config']['delivery']['pause_max_days']*86400) throw new DomainException('暂停时间已超出可预约范围，请联系服务人员复核或取消剩余批次',40927,409);
        $version=Db::name('shop_service_plan_version')->where('id',$order['plan_version_id'])->find();
        (new AgentMealSourceService())->validateProof(Json::decode($version['agent_source_proof_json'],[]));
        $delivery=(new DeliveryService())->validateAddress($userId,$payload['address_id'] ?? 0,$payload['delivery_slot_id'] ?? 0);
        $policy=(new PlanPolicyService())->current();
        $schedule=(new PlanScheduleService())->preview($policy,$delivery,$payload['first_delivery_date'] ?? '',count($eligible),true,$order['id']);
        $quantities=[];
        foreach ($eligible as $index=>$batch) {
            // 订单金额保持购买快照；新地区的运费若不同须走人工差额处理，不能静默收费。
            if ((int)$batch['shipping_fee_cent']!==$schedule['items'][$index]['shipping_fee_cent']) throw new DomainException('新配送条件涉及费用变化，请联系服务人员处理差额',40962,409);
            foreach (Db::name('shop_plan_delivery_batch_item')->where('batch_id',$batch['id'])->select() as $item) {
                $sku=(new CatalogService())->getSku($item['sku_id'],false);
                AgentMealSourceService::assertComposition(Json::decode($item['sku_snapshot_json'],[]),$sku);
                $quantities[$item['sku_id']]=($quantities[$item['sku_id']] ?? 0)+(int)$item['quantity'];
                if ($quantities[$item['sku_id']]>(int)$sku['available_quantity']) throw new DomainException('恢复批次供货不足，请选择其他日期或联系服务人员',40904,409);
            }
            $result['batches'][]=['id'=>(int)$batch['id'],'batch_no'=>(int)$batch['batch_no'],'version'=>(int)$batch['row_version'],
                'schedule'=>$schedule['items'][$index],'address'=>$delivery['snapshot'],'delivery_slot_id'=>(int)($delivery['slot']['id'] ?? 0)];
        }
        $result['policy_version']=$policy['version'];
        return $result;
    }

    protected function resume(array $order,array $preview)
    {
        foreach ($preview['batches'] as $batch) {
            $s=$batch['schedule'];
            Db::name('shop_plan_delivery_batch')->where('id',$batch['id'])->update([
                'delivery_date'=>$s['delivery_date'],'meal_date'=>$s['meal_date'],'cutoff_at'=>$s['cutoff_at'],'inventory_lock_at'=>$s['inventory_lock_at'],
                'delivery_area_id'=>$s['delivery_area_id'],'delivery_slot_id'=>$batch['delivery_slot_id'],'address_snapshot_json'=>Json::encode($batch['address']),
                'status'=>'scheduled','schedule_version'=>(int)$order['schedule_version']+1,'row_version'=>$batch['version']+1,'updatetime'=>time(),
            ]);
        }
        Db::name('shop_service_plan_order')->where('id',$order['id'])->update(['status'=>'active','pause_started_at'=>0,
            'schedule_version'=>(int)$order['schedule_version']+1,'row_version'=>(int)$order['row_version']+1,'updatetime'=>time()]);
        return ['order_sn'=>$order['order_sn'],'status'=>'active','version'=>(int)$order['row_version']+1,'batches'=>$preview['batches']];
    }

    protected function cancel(array $order,array $preview,$requestId)
    {
        if ($preview['refund_amount_cent']===0) {
            foreach ($preview['batches'] as $batch) {
                Db::name('shop_plan_delivery_batch')->where('id',$batch['id'])->update(['status'=>'cancelled','row_version'=>$batch['version']+1,'updatetime'=>time()]);
                Db::name('shop_plan_delivery_batch_item')->where('batch_id',$batch['id'])->update(['status'=>'cancelled','updatetime'=>time()]);
            }
            Db::name('shop_service_plan_order')->where('id',$order['id'])->setInc('row_version');
            $settled=(new PlanOrderService())->reconcileCompletion($order['order_sn']);
            return ['order_sn'=>$order['order_sn'],'status'=>$settled['status'],'refund_amount_cent'=>0,'refund_status'=>'not_required'];
        }
        $payment=Db::name('shop_payment_record')->where('order_sn',$order['order_sn'])->where('status','paid')->order('id','desc')->find();
        if (!$payment || $payment['channel']!=='wechat') throw new DomainException('缺少真实微信付款记录，未发起退款',40935,409);
        $reserved=(int)Db::name('shop_refund_record')->where('order_sn',$order['order_sn'])->where('status','not in',['closed','cancelled'])->sum('refund_amount_cent');
        $amount=$preview['refund_amount_cent'];
        if ($amount<=0 || $amount>(int)$payment['amount_cent']-$reserved) throw new DomainException('剩余可退金额需要复核',40935,409);
        $sn=Identifiers::make('refund');$now=time();
        $refundId=Db::name('shop_refund_record')->insertGetId(['refund_sn'=>$sn,'order_sn'=>$order['order_sn'],'payment_id'=>$payment['id'],
            'aftersale_id'=>0,'refund_amount_cent'=>$amount,'currency'=>'CNY','reason'=>'取消未执行的剩余计划批次','status'=>'created',
            'requested_at'=>$now,'request_id'=>$requestId,'createtime'=>$now,'updatetime'=>$now]);
        foreach ($preview['batches'] as $batch) {
            Db::name('shop_refund_allocation')->insert(['refund_id'=>$refundId,'allocation_type'=>'plan_remaining','batch_id'=>$batch['id'],
                'order_goods_id'=>0,'original_amount_cent'=>$batch['refund_amount_cent'],'fulfilled_amount_cent'=>0,
                'refundable_amount_cent'=>$batch['refund_amount_cent'],'refund_amount_cent'=>$batch['refund_amount_cent'],
                'formula_version'=>'purchased-batch-allocation-v1','calculation_json'=>Json::encode($batch),'exception_reason_code'=>'user_cancel_remaining','createtime'=>$now]);
            Db::name('shop_plan_delivery_batch')->where('id',$batch['id'])->update(['status'=>'refund_pending','cancellation_refund_sn'=>$sn,
                'row_version'=>$batch['version']+1,'updatetime'=>$now]);
            Db::name('shop_plan_delivery_batch_item')->where('batch_id',$batch['id'])->update(['status'=>'cancelled','updatetime'=>$now]);
        }
        $continuing=(int)Db::name('shop_plan_delivery_batch')->where('plan_order_id',$order['id'])->where('status','not in',['refund_pending','refunded','cancelled','delivered'])->count();
        $paused=(int)Db::name('shop_plan_delivery_batch')->where('plan_order_id',$order['id'])->where('status','paused')->count();
        $status=$paused?'paused':($continuing?'active':'cancelling');
        Db::name('shop_service_plan_order')->where('id',$order['id'])->update(['status'=>$status,'row_version'=>(int)$order['row_version']+1,'updatetime'=>$now]);
        // 已提交记录由既有补偿任务提交微信退款，重试使用相同 refund_sn。
        return ['order_sn'=>$order['order_sn'],'status'=>$status,'refund_sn'=>$sn,'refund_status'=>'created','refund_amount_cent'=>$amount,'version'=>(int)$order['row_version']+1];
    }

    protected function lockOrder($userId,$orderSn)
    {
        $paid=Db::name('shop_order')->where('order_sn',$orderSn)->where('user_id',$userId)->lock(true)->find();
        if (!$paid || (int)$paid['paystate']!==1) throw new DomainException('计划订单不存在或尚未支付',40410,404);
        $order=Db::name('shop_service_plan_order')->where('order_id',$paid['id'])->where('user_id',$userId)->lock(true)->find();
        if (!$order || empty($order['user_cancellable'])) throw new DomainException('该历史计划需由服务人员处理',40927,409);
        return $order;
    }
}
