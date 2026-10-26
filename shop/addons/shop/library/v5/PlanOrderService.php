<?php

namespace addons\shop\library\v5;

use think\Db;

class PlanOrderService
{
    /** 付款发起前复核购买来源、预约与累计供货；金额保留已确认快照。 */
    public function assertPayable(array $order)
    {
        $plan=Db::name('shop_service_plan_order')->where('order_id',$order['id'])->lock(true)->find();
        if (!$plan || $plan['status']!=='pending_payment') throw new DomainException('计划订单已变化',40906,409);
        $version=Db::name('shop_service_plan_version')->where('id',$plan['plan_version_id'])->find();
        $source=Db::name('shop_service_plan')->where('id',$plan['plan_id'])->find();
        (new AgentMealSourceService())->assertSource($order['user_id'],'service_plan',$source['plan_sn'],$version['version_no']);
        $batches=Db::name('shop_plan_delivery_batch')->where('plan_order_id',$plan['id'])->order('batch_no','asc')->select();
        $saved=Json::decode($plan['policy_snapshot_json'],[]);$current=(new PlanPolicyService())->current();
        if (!$saved || $saved['version']!==$current['version']) throw new DomainException('配送或收费规则已更新，请重新确认',40906,409);
        $address=Json::decode($batches[0]['address_snapshot_json'],[]);
        $delivery=(new DeliveryService())->validateAddress($order['user_id'],$address['address_id'],$batches[0]['delivery_slot_id']);
        if (Json::canonical($address)!==Json::canonical($delivery['snapshot'])) throw new DomainException('配送地址已变化，请重新下单',40906,409);
        (new PlanScheduleService())->preview($current,$delivery,$batches[0]['delivery_date'],count($batches),false,$plan['id']);
        $quantities=[];
        foreach ($batches as $batch) foreach (Db::name('shop_plan_delivery_batch_item')->where('batch_id',$batch['id'])->select() as $item) {
            $sku=(new CatalogService())->getSku($item['sku_id'],false);
            AgentMealSourceService::assertComposition(Json::decode($item['sku_snapshot_json'],[]),$sku);
            $quantities[$item['sku_id']]=($quantities[$item['sku_id']] ?? 0)+(int)$item['quantity'];
            if ($quantities[$item['sku_id']]>(int)$sku['available_quantity']) throw new DomainException('计划累计供货不足，请重新确认',40904,409);
        }
    }

    public function completeBatchFromLogistics($batchId, $occurredAt)
    {
        Db::startTrans();
        try {
            $initial=Db::name('shop_plan_delivery_batch')->where('id',(int)$batchId)->find();
            if(!$initial){Db::commit();return false;}
            $owner=Db::name('shop_service_plan_order')->where('id',$initial['plan_order_id'])->find();
            $planOrder=$this->lockedOrder($owner['user_id'],$owner['order_sn']);
            $batch=Db::name('shop_plan_delivery_batch')->where('id',$batchId)->lock(true)->find();
            if (!in_array($batch['status'],['shipped','delivering','delivered'],true)) throw new DomainException('批次尚未发货或已经取消',40910,409);
            $deliveredAt=$occurredAt?(int)$occurredAt:time();
            if($batch['status']!=='delivered')Db::name('shop_plan_delivery_batch')->where('id',$batch['id'])->update(['status'=>'delivered','fulfillment_status'=>'delivered','delivered_at'=>$deliveredAt,'row_version'=>(int)$batch['row_version']+1,'updatetime'=>time()]);
            $this->reconcileCompletion($planOrder['order_sn']);
            Db::commit();return true;
        }catch(\Exception $e){Db::rollback();throw $e;}
    }

    public function changeBatchAddress($userId, $orderSn, $batchNo, $baseVersion, $addressId, $slotId, $requestId)
    {
        Db::startTrans();
        try {
            $planOrder = $this->lockedOrder($userId, $orderSn);
            $batch = Db::name('shop_plan_delivery_batch')->where('plan_order_id',$planOrder['id'])->where('batch_no',(int)$batchNo)->lock(true)->find();
            if (!$batch) throw new DomainException('配送批次不存在',40410,404);
            if ((int)$batch['row_version'] !== (int)$baseVersion) throw new DomainException('批次版本冲突',40906,409,['current_version'=>(int)$batch['row_version']]);
            if (!in_array($planOrder['status'],['active','paused'],true) || !PlanScheduleService::changeable($batch)) throw new DomainException('批次已过截单时间或状态不可修改',40909,409);
            $delivery=(new DeliveryService())->validateAddress($userId,$addressId,$slotId);
            if ((int)$batch['delivery_area_id']!==(int)$delivery['area']['id'] || (int)$batch['delivery_slot_id']!==(int)$slotId) throw new DomainException('跨区域或时段变更需暂停后重新预约，费用变化由服务人员核对',40962,409);
            Db::name('shop_plan_delivery_batch')->where('id',$batch['id'])->where('row_version',$baseVersion)->update([
                'address_snapshot_json'=>Json::encode($delivery['snapshot']),'delivery_slot_id'=>$slotId,
                'row_version'=>$baseVersion+1,'updatetime'=>time(),
            ]);
            Db::name('shop_plan_change_request')->insert([
                'change_request_sn'=>Identifiers::make('change'),'plan_order_id'=>$planOrder['id'],'request_type'=>'batch_address',
                'target_batch_ids_json'=>Json::encode([$batch['id']]),'base_version'=>$baseVersion,
                'request_payload_json'=>Json::encode(['address_id'=>$addressId,'slot_id'=>$slotId]),'request_user_id'=>$userId,
                'status'=>'processed','processed_at'=>time(),'request_id'=>$requestId,'createtime'=>time(),'updatetime'=>time(),
            ]);
            Db::commit();
            return ['batch_no'=>(int)$batchNo,'status'=>$batch['status'],'version'=>$baseVersion+1,'address'=>$delivery['snapshot']];
        } catch (\Exception $e) { Db::rollback(); throw $e; }
    }

    public function receiptBatch($userId, $orderSn, $batchNo, $baseVersion, $requestId)
    {
        Db::startTrans();
        try {
            $planOrder=$this->lockedOrder($userId,$orderSn);
            $batch=Db::name('shop_plan_delivery_batch')->where('plan_order_id',$planOrder['id'])->where('batch_no',(int)$batchNo)->lock(true)->find();
            if(!$batch) throw new DomainException('配送批次不存在',40410,404);
            if($batch['status']==='delivered'){Db::commit();return ['batch_no'=>(int)$batchNo,'status'=>'delivered','plan_status'=>$planOrder['status']];}
            if((int)$batch['row_version']!==(int)$baseVersion) throw new DomainException('批次版本冲突',40906,409,['current_version'=>(int)$batch['row_version']]);
            if(!in_array($batch['status'],['shipped','delivering'],true)) throw new DomainException('当前批次不可确认收货',40910,409);
            $now=time();
            Db::name('shop_plan_delivery_batch')->where('id',$batch['id'])->update(['status'=>'delivered','fulfillment_status'=>'delivered','delivered_at'=>$now,'row_version'=>$baseVersion+1,'updatetime'=>$now]);
            $settled=$this->reconcileCompletion($orderSn);
            $completed=$settled['completed_batches'];$planStatus=$settled['status'];
            (new OutboxService())->append('plan.batch.delivered','plan_order',$orderSn,(int)$planOrder['row_version']+1,'agent',['order_sn'=>$orderSn,'batch_no'=>(int)$batchNo,'request_id'=>$requestId]);
            Db::commit();
            return ['batch_no'=>(int)$batchNo,'status'=>'delivered','completed_batches'=>$completed,'plan_status'=>$planStatus];
        } catch (\Exception $e) { Db::rollback(); throw $e; }
    }

    public function pause($userId, $orderSn, $baseVersion, $requestId)
    {
        Db::startTrans();
        try {
            $planOrder = $this->lockedOrder($userId, $orderSn);
            if ($planOrder['status'] !== 'active' || (int)$planOrder['row_version'] !== (int)$baseVersion) {
                throw new DomainException('计划状态或版本不允许暂停', 40926, 409);
            }
            StateMachine::assertTransition('plan_order', 'active', 'paused');
            $changeSn = Identifiers::make('change');
            $batches=Db::name('shop_plan_delivery_batch')->where('plan_order_id',$planOrder['id'])->order('batch_no','asc')->lock(true)->select();
            $futureIds=array_column(array_filter($batches,[PlanScheduleService::class,'changeable']),'id');
            if (!$futureIds) throw new DomainException('没有可以暂停的未截单批次',40926,409);
            Db::name('shop_plan_change_request')->insert([
                'change_request_sn' => $changeSn, 'plan_order_id' => $planOrder['id'], 'request_type' => 'pause',
                'target_batch_ids_json' => Json::encode($futureIds), 'base_version' => $baseVersion,
                'request_payload_json' => '{}', 'request_user_id' => $userId, 'status' => 'processed',
                'processed_at' => time(), 'request_id' => $requestId, 'createtime' => time(), 'updatetime' => time(),
            ]);
            Db::name('shop_service_plan_order')->where('id', $planOrder['id'])->update([
                'status' => 'paused', 'pause_started_at' => time(), 'row_version' => $baseVersion + 1, 'updatetime' => time(),
            ]);
            if ($futureIds) {
                foreach ($batches as $batch) if (in_array($batch['id'],$futureIds)) Db::name('shop_plan_delivery_batch')->where('id',$batch['id'])->update(['status'=>'paused','row_version'=>(int)$batch['row_version']+1,'updatetime'=>time()]);
            }
            (new OutboxService())->append('service_plan.paused', 'plan_order', $orderSn, $baseVersion + 1, 'agent', ['order_sn' => $orderSn, 'change_request_sn' => $changeSn]);
            Db::commit();
            return ['change_request_sn' => $changeSn, 'status' => 'paused', 'version' => $baseVersion + 1];
        } catch (\Exception $e) {
            Db::rollback();
            throw $e;
        }
    }

    public function requestResume($userId, $orderSn, $baseVersion, $requestId)
    {
        Db::startTrans();
        try {
            $planOrder = $this->lockedOrder($userId, $orderSn);
            if ($planOrder['status'] !== 'paused' || (int)$planOrder['row_version'] !== (int)$baseVersion) {
                throw new DomainException('计划状态或版本不允许恢复', 40927, 409);
            }
            $existing = Db::name('shop_plan_change_request')->where('plan_order_id', $planOrder['id'])
                ->where('request_type', 'resume')->where('status', 'evaluation_pending')->find();
            if ($existing) {
                Db::commit();
                return ['change_request_sn' => $existing['change_request_sn'], 'status' => 'evaluation_pending'];
            }
            $changeSn = Identifiers::make('change');
            Db::name('shop_plan_change_request')->insert([
                'change_request_sn' => $changeSn, 'plan_order_id' => $planOrder['id'], 'request_type' => 'resume',
                'target_batch_ids_json' => '[]', 'base_version' => $baseVersion,
                'request_payload_json' => '{}', 'request_user_id' => $userId,
                'status' => 'evaluation_pending', 'request_id' => $requestId,
                'createtime' => time(), 'updatetime' => time(),
            ]);
            (new OutboxService())->append('service_plan.resume_evaluation_requested', 'plan_order', $orderSn, $baseVersion, 'agent', [
                'order_sn' => $orderSn, 'change_request_sn' => $changeSn,
            ]);
            Db::commit();
            return ['change_request_sn' => $changeSn, 'status' => 'evaluation_pending'];
        } catch (\Exception $e) {
            Db::rollback();
            throw $e;
        }
    }

    public function applyResumeValidation($clientId, $orderSn, array $payload, $requestId)
    {
        foreach (['change_request_sn', 'plan_sn', 'plan_version', 'status', 'validation_id', 'rules_version', 'validated_at', 'valid_until'] as $field) {
            if (empty($payload[$field])) {
                throw new DomainException('缺少必填字段: ' . $field, 40001, 400);
            }
        }
        Db::startTrans();
        try {
            $planOrder = Db::name('shop_service_plan_order')->where('order_sn', $orderSn)->lock(true)->find();
            if (!$planOrder || $planOrder['status'] !== 'paused') {
                throw new DomainException('计划订单不存在或未暂停', 40927, 409);
            }
            $plan = Db::name('shop_service_plan')->where('id', $planOrder['plan_id'])->find();
            if (!$plan || $plan['agent_client_id'] !== $clientId || $plan['plan_sn'] !== $payload['plan_sn'] || (int)$plan['current_version'] !== (int)$payload['plan_version']) {
                throw new DomainException('Agent重评与支付计划快照不匹配', 40928, 409);
            }
            $change = Db::name('shop_plan_change_request')->where('change_request_sn', $payload['change_request_sn'])
                ->where('plan_order_id', $planOrder['id'])->where('request_type', 'resume')->lock(true)->find();
            if (!$change || $change['status'] !== 'evaluation_pending') {
                throw new DomainException('恢复申请不存在或已处理', 40929, 409);
            }
            if ($payload['status'] !== 'passed' || strtotime($payload['valid_until']) <= time()) {
                Db::name('shop_plan_change_request')->where('id', $change['id'])->update([
                    'agent_revalidation_ref' => $payload['validation_id'], 'status' => 'rejected',
                    'processed_at' => time(), 'failure_code' => 'agent_revalidation_failed',
                    'failure_message' => isset($payload['summary']) ? $payload['summary'] : '', 'updatetime' => time(),
                ]);
                Db::commit();
                return ['status' => 'paused', 'validation_status' => $payload['status']];
            }
            // 旧 Agent 回调只记录复核结论；用户仍须选择日期并确认新排程。
            Db::name('shop_plan_change_request')->where('id',$change['id'])->update([
                'agent_revalidation_ref'=>$payload['validation_id'],'status'=>'awaiting_schedule',
                'expires_at'=>strtotime($payload['valid_until']),'updatetime'=>time(),
            ]);
            Db::commit();
            return ['status'=>'paused','validation_status'=>'passed','requires_schedule_confirmation'=>true];
        } catch (\Exception $e) {
            Db::rollback();
            throw $e;
        }
    }

    /** 收货、物流、退款、补偿任务共用终态，混合退款与送达也能闭合。 */
    public function reconcileCompletion($orderSn)
    {
        Db::startTrans();
        try {
            $commerce=Db::name('shop_order')->where('order_sn',$orderSn)->lock(true)->find();
            $plan=Db::name('shop_service_plan_order')->where('order_sn',$orderSn)->lock(true)->find();
            if (!$commerce || !$plan) throw new DomainException('计划订单不存在',40410,404);
            $batches=Db::name('shop_plan_delivery_batch')->where('plan_order_id',$plan['id'])->order('batch_no','asc')->lock(true)->select();
            $delivered=0;$fulfilled=0;$closed=0;
            foreach ($batches as $batch) {
                if ($batch['status']==='delivered') {$delivered++;$fulfilled+=(int)$batch['allocated_pay_amount_cent'];}
                if (in_array($batch['status'],['delivered','refunded','cancelled'],true)) $closed++;
            }
            $terminal=count($batches)===(int)$plan['total_batches'] && $closed===count($batches);
            $status=$terminal?($delivered?'completed':'cancelled'):$plan['status'];
            if ($status!==$plan['status'] || $delivered!==(int)$plan['completed_batches'] || $fulfilled!==(int)$plan['fulfilled_amount_cent']) {
                Db::name('shop_service_plan_order')->where('id',$plan['id'])->update(['completed_batches'=>$delivered,'fulfilled_amount_cent'=>$fulfilled,'status'=>$status,'row_version'=>(int)$plan['row_version']+1,'updatetime'=>time()]);
            }
            if ($terminal) {
                Db::name('shop_order')->where('id',$commerce['id'])->update(['orderstate'=>$delivered?3:1,'shippingstate'=>$delivered?2:0,'updatetime'=>time()]);
                Db::name('shop_order_ext')->where('order_id',$commerce['id'])->update(['business_status'=>$status,'fulfillment_status'=>$delivered?'completed':'closed','updatetime'=>time()]);
            }
            Db::commit();return ['status'=>$status,'completed_batches'=>$delivered];
        } catch (\Throwable $error) {Db::rollback();throw $error;}
    }

    protected function lockedOrder($userId, $orderSn)
    {
        Db::name('shop_order')->where('order_sn',$orderSn)->where('user_id',$userId)->lock(true)->find();
        $row = Db::name('shop_service_plan_order')->where('order_sn', $orderSn)->where('user_id', $userId)->lock(true)->find();
        if (!$row) {
            throw new DomainException('计划订单不存在', 40410, 404);
        }
        return $row;
    }
}
