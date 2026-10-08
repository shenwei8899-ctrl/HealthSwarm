<?php

namespace addons\shop\library\v5;

use think\Db;

class PlanOrderService
{
    public function completeBatchFromLogistics($batchId, $occurredAt)
    {
        Db::startTrans();
        try {
            $batch=Db::name('shop_plan_delivery_batch')->where('id',(int)$batchId)->lock(true)->find();
            if(!$batch){Db::commit();return false;}
            $planOrder=Db::name('shop_service_plan_order')->where('id',$batch['plan_order_id'])->lock(true)->find();
            $deliveredAt=$occurredAt?(int)$occurredAt:time();
            if($batch['status']!=='delivered')Db::name('shop_plan_delivery_batch')->where('id',$batch['id'])->update(['status'=>'delivered','fulfillment_status'=>'delivered','delivered_at'=>$deliveredAt,'row_version'=>(int)$batch['row_version']+1,'updatetime'=>time()]);
            $completed=(int)Db::name('shop_plan_delivery_batch')->where('plan_order_id',$planOrder['id'])->where('status','delivered')->count();
            $fulfilled=(int)Db::name('shop_plan_delivery_batch')->where('plan_order_id',$planOrder['id'])->where('status','delivered')->sum('allocated_pay_amount_cent');
            $status=$completed>=(int)$planOrder['total_batches']?'completed':$planOrder['status'];
            Db::name('shop_service_plan_order')->where('id',$planOrder['id'])->update(['completed_batches'=>$completed,'fulfilled_amount_cent'=>$fulfilled,'status'=>$status,'row_version'=>(int)$planOrder['row_version']+1,'updatetime'=>time()]);
            if($status==='completed'){
                Db::name('shop_order')->where('id',$planOrder['order_id'])->update(['shippingstate'=>2,'orderstate'=>3,'receivetime'=>$deliveredAt,'updatetime'=>time()]);
                Db::name('shop_order_ext')->where('order_id',$planOrder['order_id'])->update(['business_status'=>'completed','fulfillment_status'=>'completed','updatetime'=>time()]);
            }
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
            if (!in_array($batch['status'],['scheduled','paused'],true) || (int)$batch['cutoff_at'] <= time()) throw new DomainException('批次已过截单时间或状态不可修改',40909,409);
            $delivery=(new DeliveryService())->validateAddress($userId,$addressId,$slotId);
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
            $completed=(int)Db::name('shop_plan_delivery_batch')->where('plan_order_id',$planOrder['id'])->where('status','delivered')->count();
            $fulfilled=(int)Db::name('shop_plan_delivery_batch')->where('plan_order_id',$planOrder['id'])->where('status','delivered')->sum('allocated_pay_amount_cent');
            $planStatus=$completed >= (int)$planOrder['total_batches'] ? 'completed' : $planOrder['status'];
            Db::name('shop_service_plan_order')->where('id',$planOrder['id'])->update(['completed_batches'=>$completed,'fulfilled_amount_cent'=>$fulfilled,'status'=>$planStatus,'row_version'=>(int)$planOrder['row_version']+1,'updatetime'=>$now]);
            if($planStatus==='completed'){
                Db::name('shop_order')->where('id',$planOrder['order_id'])->update(['shippingstate'=>2,'orderstate'=>3,'receivetime'=>$now,'updatetime'=>$now]);
                Db::name('shop_order_ext')->where('order_id',$planOrder['order_id'])->update(['business_status'=>'completed','fulfillment_status'=>'completed','updatetime'=>$now]);
            }
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
            $futureIds = Db::name('shop_plan_delivery_batch')->where('plan_order_id', $planOrder['id'])
                ->where('status', 'in', ['scheduled'])->where('delivery_date', '>=', date('Y-m-d'))->column('id');
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
                Db::name('shop_plan_delivery_batch')->where('id', 'in', $futureIds)->update(['status' => 'paused', 'updatetime' => time()]);
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
            $pauseDays = max(1, (int)ceil((time() - (int)$planOrder['pause_started_at']) / 86400));
            $batches = Db::name('shop_plan_delivery_batch')->where('plan_order_id', $planOrder['id'])->where('status', 'paused')->order('batch_no', 'asc')->select();
            foreach ($batches as $batch) {
                $delivery = strtotime('+' . $pauseDays . ' day', strtotime($batch['delivery_date']));
                Db::name('shop_plan_delivery_batch')->where('id', $batch['id'])->update([
                    'schedule_version' => (int)$batch['schedule_version'] + 1,
                    'delivery_date' => date('Y-m-d', $delivery), 'meal_date' => date('Y-m-d', strtotime('+1 day', $delivery)),
                    'inventory_lock_at' => strtotime('-3 day', $delivery), 'cutoff_at' => strtotime('-3 day', $delivery),
                    'status' => 'scheduled', 'row_version' => (int)$batch['row_version'] + 1, 'updatetime' => time(),
                ]);
            }
            StateMachine::assertTransition('plan_order', 'paused', 'active');
            Db::name('shop_service_plan_order')->where('id', $planOrder['id'])->update([
                'status' => 'active', 'schedule_version' => (int)$planOrder['schedule_version'] + 1,
                'resume_agent_validation_ref' => $payload['validation_id'], 'pause_started_at' => 0,
                'row_version' => (int)$planOrder['row_version'] + 1, 'updatetime' => time(),
            ]);
            Db::name('shop_plan_change_request')->where('id', $change['id'])->update([
                'agent_revalidation_ref' => $payload['validation_id'], 'status' => 'processed',
                'processed_at' => time(), 'updatetime' => time(),
            ]);
            (new OutboxService())->append('service_plan.resumed', 'plan_order', $orderSn, (int)$planOrder['row_version'] + 1, 'miniapp', [
                'order_sn' => $orderSn, 'change_request_sn' => $change['change_request_sn'], 'request_id' => $requestId,
            ]);
            Db::commit();
            return ['status' => 'active', 'schedule_version' => (int)$planOrder['schedule_version'] + 1, 'extended_days' => $pauseDays];
        } catch (\Exception $e) {
            Db::rollback();
            throw $e;
        }
    }

    protected function lockedOrder($userId, $orderSn)
    {
        $row = Db::name('shop_service_plan_order')->where('order_sn', $orderSn)->where('user_id', $userId)->lock(true)->find();
        if (!$row) {
            throw new DomainException('计划订单不存在', 40410, 404);
        }
        return $row;
    }
}
