<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\DomainException;
use addons\shop\library\v5\IdempotencyService;
use addons\shop\library\v5\Json;
use addons\shop\library\v5\OutboxService;
use addons\shop\library\v5\PlanOrderService;
use think\Db;

class IntegrationLogistics extends IntegrationBase
{
    protected $expectedClientType = 'logistics';

    public function callback()
    {
        return $this->execute(function () {
            $payload = $this->input();
            return (new IdempotencyService())->run('logistics.callback', $this->clientId(), $this->request->header('idempotency-key'), $payload, function () use ($payload) {
                foreach (['event_id', 'tracking_no', 'status', 'occurred_at'] as $field) {
                    if (empty($payload[$field])) {
                        throw new DomainException('缺少必填字段: ' . $field, 40001, 400);
                    }
                }
                $supplierOrder = !empty($payload['supplier_order_sn']) ? Db::name('shop_supplier_order')->where('supplier_order_sn', $payload['supplier_order_sn'])->find() : null;
                $existingEvent=Db::name('shop_fulfillment_event')->where('source_type','logistics')->where('event_id',$payload['event_id'])->find();
                if($existingEvent)return ['accepted'=>true,'duplicate'=>true];
                Db::name('shop_fulfillment_event')->insert([
                    'event_id' => $payload['event_id'], 'source_type' => 'logistics', 'source_ref' => $this->clientId(),
                    'platform_order_sn' => $supplierOrder ? $supplierOrder['platform_order_sn'] : (isset($payload['order_sn']) ? $payload['order_sn'] : ''),
                    'plan_batch_id' => $supplierOrder ? $supplierOrder['plan_batch_id'] : 0,
                    'supplier_order_id' => $supplierOrder ? $supplierOrder['id'] : 0,
                    'carrier_code' => isset($payload['carrier_code']) ? $payload['carrier_code'] : $this->clientId(),
                    'tracking_no' => $payload['tracking_no'], 'source_status' => isset($payload['source_status']) ? $payload['source_status'] : $payload['status'],
                    'normalized_status' => $payload['status'], 'occurred_at' => strtotime($payload['occurred_at']),
                    'location' => isset($payload['location']) ? $payload['location'] : '',
                    'description' => isset($payload['description']) ? $payload['description'] : '',
                    'payload_json' => Json::encode($payload), 'createtime' => time(),
                ]);
                if ($supplierOrder && $supplierOrder['plan_batch_id']) {
                    $batchStatus = ['picked_up' => 'shipped', 'in_transit' => 'shipped', 'delivered' => 'delivered'];
                    if (isset($batchStatus[$payload['status']])) {
                        $update = ['fulfillment_status' => $payload['status'], 'status' => $batchStatus[$payload['status']], 'updatetime' => time()];
                        if ($payload['status'] === 'delivered') {
                            $update['delivered_at'] = strtotime($payload['occurred_at']);
                        } else {
                            $update['shipped_at'] = strtotime($payload['occurred_at']);
                        }
                        Db::name('shop_plan_delivery_batch')->where('id', $supplierOrder['plan_batch_id'])->update($update);
                        if ($payload['status'] === 'delivered') {
                            (new PlanOrderService())->completeBatchFromLogistics($supplierOrder['plan_batch_id'], strtotime($payload['occurred_at']));
                        }
                    }
                }
                (new OutboxService())->append('fulfillment.status.changed', 'order', $supplierOrder ? $supplierOrder['platform_order_sn'] : $payload['tracking_no'], 1, 'miniapp', $payload);
                return ['accepted' => true];
            });
        }, $this->integrationLog('logistics_callback', 'fulfillment'));
    }
}
