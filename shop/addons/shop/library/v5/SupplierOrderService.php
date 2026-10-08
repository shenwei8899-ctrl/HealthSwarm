<?php

namespace addons\shop\library\v5;

use think\Db;

class SupplierOrderService
{
    public function createForNormalOrder($orderSn, $requestId)
    {
        $order=Db::name('shop_order')->where('order_sn',$orderSn)->find();
        if(!$order||$order['order_type']!=='normal'||(int)$order['paystate']!==1)return [];
        $ext=Db::name('shop_order_ext')->where('order_id',$order['id'])->find();
        $items=Db::name('shop_order_goods')->where('order_sn',$orderSn)->select();$groups=[];
        foreach($items as $item){
            $supplierSku=Db::name('shop_supplier_sku')->alias('ss')->join('shop_supplier s','s.id=ss.supplier_id')
                ->where('ss.sku_id',$item['goods_sku_id'])->where('ss.status','normal')->where('s.status','normal')->where('ss.stock_status','not in',['out','suspended'])->order('ss.priority','desc')->field('ss.*')->find();
            if(!$supplierSku){(new ExceptionService())->open('normal_supplier:'.$item['id'],'supply_chain','supplier_missing','普通订单商品没有可用供应商',['resource_type'=>'order_item','resource_ref'=>(string)$item['id'],'order_sn'=>$orderSn],['sku_id'=>$item['goods_sku_id']],'high');continue;}
            $groups[$supplierSku['supplier_id']][]=['item'=>$item,'supplier_sku'=>$supplierSku];
        }
        $ids=[];
        foreach($groups as $supplierId=>$entries){
            $existing=Db::name('shop_supplier_order')->where('supplier_id',$supplierId)->where('platform_order_sn',$orderSn)->where('plan_batch_id',0)->find();
            if($existing){$ids[]=$existing['id'];continue;}
            Db::startTrans();
            try{
                $sn=Identifiers::make('supplierorder');$id=Db::name('shop_supplier_order')->insertGetId([
                    'supplier_order_sn'=>$sn,'supplier_id'=>$supplierId,'platform_order_sn'=>$orderSn,'plan_batch_id'=>0,'status'=>'created','push_status'=>'pending','next_retry_at'=>time(),
                    'address_snapshot_json'=>$ext?$ext['address_snapshot_json']:'{}','row_version'=>1,'createtime'=>time(),'updatetime'=>time(),
                ]);
                foreach($entries as $entry){$item=$entry['item'];$ss=$entry['supplier_sku'];$itemExt=Db::name('shop_order_goods_ext')->where('order_goods_id',$item['id'])->find();Db::name('shop_supplier_order_item')->insert([
                    'supplier_order_id'=>$id,'order_goods_id'=>$item['id'],'supplier_sku_id'=>$ss['id'],'quantity'=>$item['nums'],'purchase_price_cent'=>$ss['purchase_price_cent'],
                    'status'=>'created','item_snapshot_json'=>$itemExt?$itemExt['sku_snapshot_json']:'{}','createtime'=>time(),'updatetime'=>time(),
                ]);}
                (new OutboxService())->append('supplier.order.ready','supplier_order',$sn,1,'supplier:'.$supplierId,['supplier_order_sn'=>$sn,'order_sn'=>$orderSn,'request_id'=>$requestId]);
                Db::commit();$ids[]=$id;
            }catch(\Exception $e){Db::rollback();throw $e;}
        }
        return $ids;
    }

    public function createForBatch($batchId, $requestId)
    {
        $batch = Db::name('shop_plan_delivery_batch')->where('id', (int)$batchId)->find();
        if (!$batch || !in_array($batch['status'], ['scheduled', 'exception'], true)) {
            return [];
        }
        $planOrder = Db::name('shop_service_plan_order')->where('id', $batch['plan_order_id'])->find();
        if (!$planOrder || $planOrder['status'] !== 'active') {
            return [];
        }
        $items = Db::name('shop_plan_delivery_batch_item')->where('batch_id', $batch['id'])->where('status', 'scheduled')->select();
        $groups = [];
        $reservations = [];
        try {
            foreach ($items as $item) {
                $supplierSku = Db::name('shop_supplier_sku')->alias('ss')->join('shop_supplier s', 's.id=ss.supplier_id')
                    ->where('ss.sku_id', $item['sku_id'])->where('ss.status', 'normal')->where('s.status', 'normal')
                    ->where('ss.stock_status', 'not in', ['out', 'suspended'])->order('ss.priority', 'desc')->field('ss.*,s.name as supplier_name')->find();
                if (!$supplierSku) {
                    throw new DomainException('SKU没有可用供应商', 40932, 409, ['sku_id' => (string)$item['sku_id']]);
                }
                $reservation = (new InventoryService())->reserve(
                    $item['sku_id'], $item['quantity'], 'plan_batch', $batch['batch_sn'], $item['id'], $requestId,
                    max(time() + 3600, strtotime($batch['delivery_date'] . ' 23:59:59'))
                );
                $reservations[$item['id']] = $reservation;
                $groups[$supplierSku['supplier_id']][] = ['batch_item' => $item, 'supplier_sku' => $supplierSku];
            }
        } catch (\Exception $e) {
            foreach ($reservations as $reservation) {
                try {
                    (new InventoryService())->release($reservation['reservation_sn'], 'batch_prepare_failed', $requestId);
                } catch (\Exception $ignored) {
                }
            }
            Db::name('shop_plan_delivery_batch')->where('id', $batch['id'])->update([
                'inventory_status' => 'failed', 'supplier_status' => 'blocked', 'status' => 'exception', 'updatetime' => time(),
            ]);
            (new ExceptionService())->open('batch_prepare:' . $batch['id'], 'supply_chain', 'batch_prepare_failed', $e->getMessage(), [
                'resource_type' => 'plan_batch', 'resource_ref' => $batch['batch_sn'],
                'order_sn' => $planOrder['order_sn'], 'batch_id' => $batch['id'],
            ], $e instanceof DomainException ? $e->getDetails() : [], 'high');
            throw $e;
        }

        Db::startTrans();
        try {
            $orderIds = [];
            foreach ($groups as $supplierId => $groupItems) {
                $existing = Db::name('shop_supplier_order')->where('supplier_id', $supplierId)->where('plan_batch_id', $batch['id'])->find();
                if ($existing) {
                    $orderIds[] = $existing['id'];
                    continue;
                }
                $supplierOrderSn = Identifiers::make('supplierorder');
                $supplierOrderId = Db::name('shop_supplier_order')->insertGetId([
                    'supplier_order_sn' => $supplierOrderSn, 'supplier_id' => $supplierId,
                    'platform_order_sn' => $planOrder['order_sn'], 'plan_batch_id' => $batch['id'],
                    'external_order_no' => null, 'status' => 'created', 'push_status' => 'pending',
                    'next_retry_at' => time(), 'address_snapshot_json' => $batch['address_snapshot_json'],
                    'row_version' => 1, 'createtime' => time(), 'updatetime' => time(),
                ]);
                foreach ($groupItems as $entry) {
                    $item = $entry['batch_item'];
                    $supplierSku = $entry['supplier_sku'];
                    $supplierOrderItemId = Db::name('shop_supplier_order_item')->insertGetId([
                        'supplier_order_id' => $supplierOrderId, 'plan_batch_item_id' => $item['id'],
                        'supplier_sku_id' => $supplierSku['id'], 'quantity' => $item['quantity'],
                        'purchase_price_cent' => $supplierSku['purchase_price_cent'], 'status' => 'created',
                        'item_snapshot_json' => $item['sku_snapshot_json'], 'createtime' => time(), 'updatetime' => time(),
                    ]);
                    Db::name('shop_plan_delivery_batch_item')->where('id', $item['id'])->update([
                        'inventory_reservation_id' => $reservations[$item['id']]['id'],
                        'supplier_order_item_id' => $supplierOrderItemId, 'status' => 'reserved', 'updatetime' => time(),
                    ]);
                }
                (new OutboxService())->append('supplier.order.ready', 'supplier_order', $supplierOrderSn, 1, 'supplier:' . $supplierId, [
                    'supplier_order_sn' => $supplierOrderSn, 'batch_sn' => $batch['batch_sn'],
                ]);
                $orderIds[] = $supplierOrderId;
            }
            Db::name('shop_plan_delivery_batch')->where('id', $batch['id'])->update([
                'inventory_status' => 'reserved', 'supplier_status' => 'pending', 'status' => 'supplier_pending',
                'prepared_at' => time(), 'row_version' => (int)$batch['row_version'] + 1, 'updatetime' => time(),
            ]);
            Db::commit();
            return $orderIds;
        } catch (\Exception $e) {
            Db::rollback();
            throw $e;
        }
    }

    public function push($supplierOrderId)
    {
        $order = Db::name('shop_supplier_order')->where('id', (int)$supplierOrderId)->find();
        if (!$order || !in_array($order['push_status'], ['pending', 'failed'], true)) {
            return $order;
        }
        $supplier = Db::name('shop_supplier')->where('id', $order['supplier_id'])->where('status', 'normal')->find();
        if (!$supplier) {
            $this->recordPushFailure($order, '供应商已停用', 1);
            throw new DomainException('供应商已停用', 40933, 409);
        }
        if ($supplier['interface_type'] === 'manual') {
            Db::name('shop_supplier_order')->where('id', $order['id'])->update(['push_status' => 'manual', 'updatetime' => time()]);
            return Db::name('shop_supplier_order')->where('id', $order['id'])->find();
        }
        if (!$supplier['endpoint_url'] || !$supplier['secret_ciphertext']) {
            $this->recordPushFailure($order, '供应商接口配置不完整', 1);
            throw new DomainException('供应商接口配置不完整', 50302, 503);
        }
        $items = Db::name('shop_supplier_order_item')->alias('oi')->join('shop_supplier_sku ss', 'ss.id=oi.supplier_sku_id')
            ->where('oi.supplier_order_id', $order['id'])->field('oi.quantity,oi.purchase_price_cent,ss.supplier_sku_code,ss.supplier_sku_name')->select();
        $payload = [
            'supplier_order_sn' => $order['supplier_order_sn'], 'platform_order_sn' => $order['platform_order_sn'],
            'address' => Json::decode($order['address_snapshot_json'], []), 'items' => $items,
        ];
        $timestamp = time();
        $nonce = bin2hex(random_bytes(16));
        $body = Json::encode($payload);
        try {
            $secret = SecretCipher::decrypt($supplier['secret_ciphertext']);
        } catch (\Exception $e) {
            $this->recordPushFailure($order, $e->getMessage(), 1);
            throw $e;
        }
        $signature = SignatureService::sign('POST', parse_url($supplier['endpoint_url'], PHP_URL_PATH), $timestamp, $nonce, $body, $secret);
        try {
            $result = (new HttpClient())->postJson($supplier['endpoint_url'], $payload, [
                'X-Client-Id' => 'shop', 'X-Timestamp' => $timestamp, 'X-Nonce' => $nonce,
                'X-Signature' => $signature, 'Idempotency-Key' => $order['supplier_order_sn'],
            ]);
            Db::name('shop_supplier_order')->where('id', $order['id'])->update([
                'status' => 'pushing', 'push_status' => 'success', 'push_attempts' => (int)$order['push_attempts'] + 1,
                'response_snapshot_json' => Json::encode($result['body']), 'row_version' => (int)$order['row_version'] + 1,
                'updatetime' => time(),
            ]);
            IntegrationLogger::write([
                'request_id' => Identifiers::requestId(), 'partner_type' => 'supplier', 'partner_code' => $supplier['supplier_code'],
                'direction' => 'outbound', 'interface_name' => 'supplier_order_push', 'method' => 'POST',
                'url_path' => parse_url($supplier['endpoint_url'], PHP_URL_PATH), 'business_type' => 'supplier_order',
                'business_ref' => $order['supplier_order_sn'], 'request_body_masked' => $payload,
                'response_body_masked' => $result['body'], 'http_status' => $result['status'],
                'duration_ms' => $result['duration_ms'], 'success' => 1,
            ]);
        } catch (\Exception $e) {
            $attempts = (int)$order['push_attempts'] + 1;
            Db::name('shop_supplier_order')->where('id', $order['id'])->update([
                'push_status' => 'failed', 'push_attempts' => $attempts,
                'next_retry_at' => time() + min(3600, (int)pow(2, min($attempts, 10)) * 30),
                'response_snapshot_json' => Json::encode(['error' => $e->getMessage()]), 'updatetime' => time(),
            ]);
            (new ExceptionService())->open('supplier_push:' . $order['id'], 'supplier', 'push_failed', $e->getMessage(), [
                'resource_type' => 'supplier_order', 'resource_ref' => $order['supplier_order_sn'],
                'order_sn' => $order['platform_order_sn'], 'supplier_order_id' => $order['id'],
            ], [], $attempts >= 3 ? 'high' : 'medium');
            throw $e;
        }
        return Db::name('shop_supplier_order')->where('id', $order['id'])->find();
    }

    public function applyCallback($supplierId, array $payload)
    {
        if (empty($payload['status']) && !empty($payload['event_type'])) {
            $payload['status'] = $payload['event_type'];
        }
        if (empty($payload['supplier_order_sn']) || empty($payload['event_id']) || empty($payload['status'])) {
            throw new DomainException('供应商回调字段不完整', 40001, 400);
        }
        if ($payload['status'] === 'delivered') $payload['status'] = 'completed';
        $progress = ['created'=>0,'pushing'=>1,'accepted'=>2,'preparing'=>3,'shipped'=>4,'completed'=>5];
        $allowed = $progress + ['rejected'=>-1,'exception'=>-1,'partially_unavailable'=>-1];
        if (!isset($allowed[$payload['status']])) throw new DomainException('供应商状态无效',40001,400);
        Db::startTrans();
        try {
            $order = Db::name('shop_supplier_order')->where('supplier_id', $supplierId)
                ->where('supplier_order_sn', $payload['supplier_order_sn'])->lock(true)->find();
            if (!$order) throw new DomainException('供应商订单不存在',40411,404);
            if (Db::name('shop_fulfillment_event')->where('source_type','supplier')->where('event_id',$payload['event_id'])->find()) {
                Db::commit();
                return $order;
            }
            if ($payload['status'] === 'partially_unavailable') {
                if (isset($progress[$order['status']]) && $progress[$order['status']] >= $progress['shipped']) {
                    $this->recordSupplierEvent($supplierId,$order,$payload,'exception','迟到的缺货事件，未回退订单状态');
                    Db::commit();
                    return $order;
                }
                foreach ((array)(isset($payload['items']) ? $payload['items'] : []) as $item) {
                    if (empty($item['supplier_sku_code'])) continue;
                    $supplierSkuId = Db::name('shop_supplier_sku')->where('supplier_id',$supplierId)->where('supplier_sku_code',$item['supplier_sku_code'])->value('id');
                    if ($supplierSkuId) Db::name('shop_supplier_order_item')->where('supplier_order_id',$order['id'])->where('supplier_sku_id',$supplierSkuId)->update([
                        'unavailable_quantity'=>max(0,(int)(isset($item['unavailable_quantity'])?$item['unavailable_quantity']:$item['quantity'])),
                        'reason_code'=>isset($item['reason_code'])?$item['reason_code']:'supplier_out_of_stock','status'=>'unavailable','updatetime'=>time(),
                    ]);
                }
                Db::name('shop_supplier_order')->where('id',$order['id'])->update(['status'=>'exception','row_version'=>(int)$order['row_version']+1,'updatetime'=>time()]);
                if ($order['plan_batch_id']) Db::name('shop_plan_delivery_batch')->where('id',$order['plan_batch_id'])->update(['supplier_status'=>'partially_unavailable','status'=>'exception','updatetime'=>time()]);
                $this->recordSupplierEvent($supplierId,$order,$payload,'exception','供应商部分缺货');
                (new ExceptionService())->open('supplier_partial:'.$order['id'],'supplier','partially_unavailable','供应商部分缺货，需要替代或例外履约',[
                    'resource_type'=>'supplier_order','resource_ref'=>$order['supplier_order_sn'],'order_sn'=>$order['platform_order_sn'],'batch_id'=>$order['plan_batch_id'],'supplier_order_id'=>$order['id'],
                ],$payload,'high');
                Db::commit();
                return Db::name('shop_supplier_order')->where('id',$order['id'])->find();
            }
            if (isset($progress[$order['status']]) && isset($progress[$payload['status']]) && $progress[$payload['status']] < $progress[$order['status']]) {
                $this->recordSupplierEvent($supplierId,$order,$payload,$payload['status'],'迟到事件，未回退订单状态');
                Db::commit();
                return $order;
            }
            if (isset($progress[$order['status']]) && $progress[$order['status']] >= $progress['shipped'] && !isset($progress[$payload['status']])) {
                $this->recordSupplierEvent($supplierId,$order,$payload,$payload['status'],'迟到的异常事件，未回退订单状态');
                Db::commit();
                return $order;
            }
            if ($order['status'] !== $payload['status']) {
                StateMachine::assertTransition('supplier_order',$order['status'],$payload['status']);
                $update=['status'=>$payload['status'],'row_version'=>(int)$order['row_version']+1,'updatetime'=>time()];
                if (!empty($payload['supplier_external_order_no'])) $update['external_order_no']=$payload['supplier_external_order_no'];
                if ($payload['status']==='accepted') $update['accepted_at']=time();
                elseif ($payload['status']==='shipped') $update['shipped_at']=time();
                elseif ($payload['status']==='completed') $update['completed_at']=time();
                elseif ($payload['status']==='rejected') $update['reject_code']=isset($payload['reason_code'])?$payload['reason_code']:'';
                Db::name('shop_supplier_order')->where('id',$order['id'])->update($update);
            }
            $this->recordSupplierEvent($supplierId,$order,$payload,$payload['status']);
            if ($order['plan_batch_id']) {
                $batchUpdate=['supplier_status'=>$payload['status'],'updatetime'=>time()];
                if ($payload['status']==='shipped') $batchUpdate += ['status'=>'shipped','fulfillment_status'=>'shipped','shipped_at'=>time()];
                Db::name('shop_plan_delivery_batch')->where('id',$order['plan_batch_id'])->update($batchUpdate);
            } elseif ($payload['status']==='shipped') {
                Db::name('shop_order')->where('order_sn',$order['platform_order_sn'])->update(['shippingstate'=>1,'shippingtime'=>time(),'updatetime'=>time()]);
                Db::name('shop_order_ext')->where('order_sn',$order['platform_order_sn'])->update(['business_status'=>'fulfilling','fulfillment_status'=>'shipped','updatetime'=>time()]);
            } elseif ($payload['status']==='completed') {
                $remaining=Db::name('shop_supplier_order')->where('platform_order_sn',$order['platform_order_sn'])->where('plan_batch_id',0)->where('id','<>',$order['id'])->where('status','<>','completed')->count();
                if(!$remaining){Db::name('shop_order')->where('order_sn',$order['platform_order_sn'])->update(['shippingstate'=>2,'orderstate'=>3,'receivetime'=>time(),'updatetime'=>time()]);Db::name('shop_order_ext')->where('order_sn',$order['platform_order_sn'])->update(['business_status'=>'completed','fulfillment_status'=>'completed','updatetime'=>time()]);}
            }
            if ($payload['status']==='rejected') (new ExceptionService())->open('supplier_reject:'.$order['id'],'supplier','supplier_rejected','供应商拒绝接单',[
                'resource_type'=>'supplier_order','resource_ref'=>$order['supplier_order_sn'],'order_sn'=>$order['platform_order_sn'],'batch_id'=>$order['plan_batch_id'],'supplier_order_id'=>$order['id'],
            ],$payload,'high');
            Db::commit();
            return Db::name('shop_supplier_order')->where('id',$order['id'])->find();
        } catch (\Exception $e) {
            Db::rollback();
            throw $e;
        }
    }

    protected function recordSupplierEvent($supplierId,array $order,array $payload,$normalizedStatus,$description='')
    {
        Db::name('shop_fulfillment_event')->insert([
            'event_id'=>$payload['event_id'],'source_type'=>'supplier','source_ref'=>(string)$supplierId,
            'platform_order_sn'=>$order['platform_order_sn'],'plan_batch_id'=>$order['plan_batch_id'],'supplier_order_id'=>$order['id'],
            'carrier_code'=>isset($payload['carrier_code'])?$payload['carrier_code']:'','tracking_no'=>isset($payload['tracking_no'])?$payload['tracking_no']:'',
            'source_status'=>isset($payload['event_type'])?$payload['event_type']:$payload['status'],'normalized_status'=>$normalizedStatus,
            'occurred_at'=>!empty($payload['event_time'])?strtotime($payload['event_time']):time(),'location'=>isset($payload['location'])?$payload['location']:'',
            'description'=>$description?: (isset($payload['reason_code'])?$payload['reason_code']:''),'payload_json'=>Json::encode($payload),'createtime'=>time(),
        ]);
    }

    protected function recordPushFailure(array $order, $message, $minimumAttempts = 0)
    {
        $attempts = max((int)$minimumAttempts, (int)$order['push_attempts'] + 1);
        Db::name('shop_supplier_order')->where('id', $order['id'])->update([
            'push_status' => 'failed', 'push_attempts' => $attempts,
            'next_retry_at' => time() + min(3600, (int)pow(2, min($attempts, 10)) * 30),
            'response_snapshot_json' => Json::encode(['error' => $message]), 'updatetime' => time(),
        ]);
        (new ExceptionService())->open('supplier_push:' . $order['id'], 'supplier', 'push_failed', $message, [
            'resource_type' => 'supplier_order', 'resource_ref' => $order['supplier_order_sn'],
            'order_sn' => $order['platform_order_sn'], 'supplier_order_id' => $order['id'],
        ], [], 'high');
    }
}
