<?php

namespace addons\shop\library\v5;

use think\Db;

class JobRunner
{
    protected $owner;

    public function __construct()
    {
        $this->owner = php_uname('n') . ':' . getmypid();
    }

    public function runAll()
    {
        $jobs = [
            'expire_recommendations' => [$this, 'expireRecommendations'],
            'close_unpaid_v5_orders' => [$this, 'closeUnpaidOrders'],
            'expire_reservations' => [$this, 'expireReservations'],
            'reconcile_paid_orders' => [$this, 'reconcilePaidOrders'],
            'scan_future_batch_stock' => [$this, 'scanFutureBatchStock'],
            'prepare_plan_batches' => [$this, 'preparePlanBatches'],
            'push_supplier_orders' => [$this, 'pushSupplierOrders'],
            'reconcile_plan_delivery' => [$this, 'reconcilePlanDelivery'],
            'compensate_refunds' => [$this, 'compensateRefunds'],
            'dispatch_outbox' => [$this, 'dispatchOutbox'],
            'cleanup_integration_state' => [$this, 'cleanupIntegrationState'],
            'aggregate_daily_metrics' => [$this, 'aggregateDailyMetrics'],
        ];
        $results = [];
        foreach ($jobs as $name => $handler) {
            $results[$name] = $this->run($name, $handler);
        }
        return $results;
    }

    public function run($name, callable $handler)
    {
        if (!$this->acquire($name, 300)) {
            return ['status' => 'skipped', 'reason' => 'locked'];
        }
        $runId = Identifiers::make('job');
        $runPk = Db::name('shop_job_run')->insertGetId([
            'run_id' => $runId, 'job_name' => $name, 'owner' => $this->owner,
            'status' => 'running', 'started_at' => time(),
        ]);
        try {
            $count = (int)call_user_func($handler);
            Db::name('shop_job_run')->where('id', $runPk)->update([
                'status' => 'success', 'processed_count' => $count, 'success_count' => $count, 'finished_at' => time(),
            ]);
            $this->release($name);
            return ['status' => 'success', 'processed' => $count];
        } catch (\Exception $e) {
            Db::name('shop_job_run')->where('id', $runPk)->update([
                'status' => 'failed', 'failure_count' => 1, 'last_error' => mb_substr($e->getMessage(), 0, 1000), 'finished_at' => time(),
            ]);
            AlertService::notify('scheduled_job_failed', $e->getMessage(), ['job_name' => $name, 'run_id' => $runId, 'owner' => $this->owner]);
            $this->release($name);
            return ['status' => 'failed', 'error' => $e->getMessage()];
        }
    }

    public function expireRecommendations()
    {
        return Db::name('shop_recommendation_package')->where('status', 'in', ['draft', 'validated', 'available', 'blocked'])
            ->where('expires_at', '>', 0)->where('expires_at', '<=', time())->update(['status' => 'expired', 'updatetime' => time()]);
    }

    public function closeUnpaidOrders()
    {
        $orders = Db::name('shop_order')->where('request_id', '<>', '')->where('paystate', 0)
            ->where('orderstate', 0)->where('expiretime', '<=', time())->limit(100)->select();
        foreach ($orders as $order) {
            Db::name('shop_order')->where('id', $order['id'])->update(['orderstate' => 2, 'updatetime' => time()]);
            $ext = Db::name('shop_order_ext')->where('order_sn', $order['order_sn'])->find();
            if ($ext) {
                Db::name('shop_order_ext')->where('id', $ext['id'])->update(['business_status' => 'closed', 'payment_status' => 'closed', 'updatetime' => time()]);
                $reservations = Db::name('shop_inventory_reservation')->where('source_type', 'checkout')->where('source_ref', $ext['checkout_token_hash'])->where('status', 'active')->select();
                foreach ($reservations as $reservation) {
                    (new InventoryService())->release($reservation['reservation_sn'], 'unpaid_order_closed', $ext['request_id']);
                }
            }
            Db::name('shop_service_plan_order')->where('order_sn', $order['order_sn'])->where('status', 'pending_payment')->update(['status' => 'payment_closed', 'updatetime' => time()]);
        }
        return count($orders);
    }

    public function expireReservations()
    {
        $rows = Db::name('shop_inventory_reservation')->where('status', 'active')->where('expires_at', '<=', time())->limit(200)->select();
        foreach ($rows as $row) {
            (new InventoryService())->release($row['reservation_sn'], 'reservation_expired', $row['request_id']);
        }
        return count($rows);
    }

    public function reconcilePaidOrders()
    {
        $rows = Db::name('shop_order')->alias('o')->join('shop_order_ext e','e.order_id=o.id')
            ->join('shop_service_plan_order po','po.order_id=o.id','LEFT')
            ->where('o.request_id','<>','')->where('o.paystate',1)
            ->where(function($query){
                $query->where('e.payment_status','<>','paid')
                    ->whereOr(function($normal){
                        $normal->where('o.order_type','normal')->where('e.fulfillment_status','pending');
                    })
                    ->whereOr('po.status','pending_payment');
            })->field('o.order_sn,o.saleamount,o.transactionid')->limit(100)->select();
        foreach($rows as $row){
            try{
                (new PaymentService())->onPaid($row['order_sn'],(int)round((float)$row['saleamount']*100),$row['transactionid']);
            }catch(\Exception $e){
                (new ExceptionService())->open('payment_sync:'.$row['order_sn'],'payment','paid_order_sync_failed',$e->getMessage(),[
                    'resource_type'=>'order','resource_ref'=>$row['order_sn'],'order_sn'=>$row['order_sn'],
                ],[],'high');
            }
        }
        return count($rows);
    }

    public function scanFutureBatchStock()
    {
        $endDate = date('Y-m-d', strtotime('+7 days'));
        $rows = Db::name('shop_plan_delivery_batch')->alias('b')
            ->join('shop_service_plan_order po', 'po.id=b.plan_order_id')
            ->where('po.status', 'active')->where('b.status', 'scheduled')
            ->where('b.delivery_date', 'between', [date('Y-m-d'), $endDate])
            ->field('b.id,b.batch_sn,b.delivery_date,po.order_sn')->limit(100)->select();
        $checked = 0;
        foreach ($rows as $batch) {
            $items = Db::name('shop_plan_delivery_batch_item')->where('batch_id', $batch['id'])->select();
            foreach ($items as $item) {
                $checked++;
                $sku = Db::name('shop_goods_sku')->where('id', $item['sku_id'])->find();
                $available = $sku ? max(0, (int)$sku['stocks'] - (int)$sku['reserved_stock'] - (int)$sku['safety_stock']) : 0;
                $supplier = Db::name('shop_supplier_sku')->where('sku_id', $item['sku_id'])->where('status', 'normal')
                    ->where('stock_status', '<>', 'out')->order('priority', 'desc')->find();
                $problems = [];
                if (!$sku || $available < (int)$item['quantity']) {
                    $problems[] = '平台可用库存不足';
                }
                if (!$supplier) {
                    $problems[] = '没有可用供应商商品';
                } elseif ($supplier['stock_status'] !== 'unknown' && (int)$supplier['stock_quantity'] < (int)$item['quantity']) {
                    $problems[] = '供应商库存不足';
                }
                $dedupeKey = 'future_stock:' . $batch['id'] . ':' . $item['sku_id'];
                if ($problems) {
                    $days = (int)floor((strtotime($batch['delivery_date']) - strtotime(date('Y-m-d'))) / 86400);
                    (new ExceptionService())->open($dedupeKey, 'supply_chain', 'future_stock_risk', implode('；', $problems), [
                        'resource_type' => 'plan_batch', 'resource_ref' => $batch['batch_sn'],
                        'order_sn' => $batch['order_sn'], 'batch_id' => $batch['id'],
                    ], [
                        'sku_id' => (int)$item['sku_id'], 'required_quantity' => (int)$item['quantity'],
                        'platform_available' => $available, 'delivery_date' => $batch['delivery_date'],
                    ], $days <= 3 ? 'high' : 'medium');
                } else {
                    Db::name('shop_exception_order')->where('dedupe_key', $dedupeKey)
                        ->where('status', 'in', ['open', 'processing'])->update([
                            'status' => 'resolved', 'resolved_at' => time(),
                            'resolution' => '自动复查：库存与供应商能力已恢复', 'updatetime' => time(),
                        ]);
                }
            }
        }
        return $checked;
    }

    public function preparePlanBatches()
    {
        $rows = Db::name('shop_plan_delivery_batch')->alias('b')->join('shop_service_plan_order po', 'po.id=b.plan_order_id')
            ->where('po.status', 'active')->where('b.status', 'scheduled')->where('b.inventory_lock_at', '<=', time())
            ->field('b.id')->limit(50)->select();
        foreach ($rows as $row) {
            try {
                (new SupplierOrderService())->createForBatch($row['id'], Identifiers::requestId());
            } catch (\Exception $e) {
            }
        }
        return count($rows);
    }

    public function pushSupplierOrders()
    {
        $rows = Db::name('shop_supplier_order')->where('push_status', 'in', ['pending', 'failed'])
            ->where('next_retry_at', '<=', time())->limit(50)->select();
        foreach ($rows as $row) {
            try {
                (new SupplierOrderService())->push($row['id']);
            } catch (\Exception $e) {
            }
        }
        return count($rows);
    }

    public function reconcilePlanDelivery()
    {
        $orders = Db::name('shop_service_plan_order')->where('status', 'in', ['active', 'paused', 'exception_handling', 'completed'])
            ->limit(100)->select();
        $changed = 0;
        foreach ($orders as $planOrder) {
            $completed = (int)Db::name('shop_plan_delivery_batch')->where('plan_order_id', $planOrder['id'])->where('status', 'delivered')->count();
            $fulfilled = (int)Db::name('shop_plan_delivery_batch')->where('plan_order_id', $planOrder['id'])->where('status', 'delivered')->sum('allocated_pay_amount_cent');
            $isComplete = $completed >= (int)$planOrder['total_batches'];
            if ($completed === (int)$planOrder['completed_batches'] && $fulfilled === (int)$planOrder['fulfilled_amount_cent'] && (!$isComplete || $planOrder['status'] === 'completed')) {
                continue;
            }
            $update = [
                'completed_batches' => $completed, 'fulfilled_amount_cent' => $fulfilled,
                'row_version' => (int)$planOrder['row_version'] + 1, 'updatetime' => time(),
            ];
            if ($isComplete) {
                $update['status'] = 'completed';
            }
            Db::name('shop_service_plan_order')->where('id', $planOrder['id'])->update($update);
            if ($isComplete) {
                Db::name('shop_order')->where('id', $planOrder['order_id'])->update([
                    'shippingstate' => 2, 'orderstate' => 3, 'receivetime' => time(), 'updatetime' => time(),
                ]);
                Db::name('shop_order_ext')->where('order_id', $planOrder['order_id'])->update([
                    'business_status' => 'completed', 'fulfillment_status' => 'completed', 'updatetime' => time(),
                ]);
            }
            $changed++;
        }
        return $changed;
    }

    public function compensateRefunds()
    {
        $rows = Db::name('shop_refund_record')->where(function ($query) {
            $query->where('status', 'created')
                ->whereOr(function ($retry) {
                    $retry->where('status', 'failed')->where('failure_code', 'submit_failed')->where('updatetime', '<=', time() - 300);
                })
                ->whereOr(function ($pending) {
                    $pending->where('status', 'processing')->where('updatetime', '<=', time() - 300);
                });
        })->limit(50)->select();
        foreach ($rows as $row) {
            try {
                if ($row['status'] === 'processing') {
                    (new RefundService())->queryWechat($row['refund_sn']);
                } else {
                    (new RefundService())->submitWechat($row['refund_sn']);
                }
            } catch (\Exception $e) {
                (new ExceptionService())->open('refund_compensate:' . $row['refund_sn'], 'payment', 'refund_compensation_failed', $e->getMessage(), [
                    'resource_type' => 'refund', 'resource_ref' => $row['refund_sn'], 'order_sn' => $row['order_sn'],
                ], [], 'high');
            }
        }
        return count($rows);
    }

    public function dispatchOutbox()
    {
        return (new OutboxDispatcher())->dispatch(100);
    }

    public function cleanupIntegrationState()
    {
        // PostgreSQL does not support DELETE ... LIMIT. Select a bounded set
        // of IDs first, then delete by primary key for portable batching.
        $nonces = $this->deleteBatch('shop_integration_nonce', [
            ['expires_at', '<', time()],
        ]);
        $idempotency = $this->deleteBatch('shop_idempotency_record', [
            ['expires_at', '<', time()], ['status', '<>', 'processing'],
        ]);
        $sessions = Db::name('shop_checkout_session')->where('expires_at', '<', time())->where('status', 'active')->update(['status' => 'expired', 'updatetime' => time()]);
        $jobRuns = $this->deleteBatch('shop_job_run', [
            ['finished_at', '>', 0], ['finished_at', '<', time() - 90 * 86400],
        ]);
        return (int)$nonces + (int)$idempotency + (int)$sessions + (int)$jobRuns;
    }

    protected function deleteBatch($table, array $conditions, $limit = 1000)
    {
        $query = Db::name($table);
        foreach ($conditions as $condition) {
            $query->where($condition[0], $condition[1], $condition[2]);
        }
        $ids = $query->field('id')->limit($limit)->select();
        $ids = array_values(array_filter(array_map('intval', array_column($ids ?: [], 'id'))));
        return $ids ? Db::name($table)->where('id', 'in', $ids)->delete() : 0;
    }

    public function aggregateDailyMetrics()
    {
        $date = date('Y-m-d');
        $start = strtotime($date . ' 00:00:00');
        $end = strtotime($date . ' 23:59:59');
        $metrics = [
            'paid_order_count' => Db::name('shop_order')->where('paytime', 'between', [$start, $end])->where('paystate', 1)->count(),
            'paid_amount_cent' => (int)round((float)Db::name('shop_order')->where('paytime', 'between', [$start, $end])->where('paystate', 1)->sum('payamount') * 100),
            'plan_order_count' => Db::name('shop_order')->where('paytime', 'between', [$start, $end])->where('paystate', 1)->where('order_type', 'plan')->count(),
            'open_exception_count' => Db::name('shop_exception_order')->where('status', 'in', ['open', 'processing'])->count(),
        ];
        foreach ($metrics as $key => $value) {
            $row = Db::name('shop_metric_daily')->where(['metric_date' => $date, 'metric_group' => 'commerce', 'metric_key' => $key, 'dimension_key' => ''])->find();
            $data = ['metric_value' => $value, 'calculated_at' => time(), 'updatetime' => time()];
            if ($row) {
                Db::name('shop_metric_daily')->where('id', $row['id'])->update($data);
            } else {
                $data += ['metric_date' => $date, 'metric_group' => 'commerce', 'metric_key' => $key, 'dimension_key' => ''];
                Db::name('shop_metric_daily')->insert($data);
            }
        }
        return count($metrics);
    }

    protected function acquire($name, $ttl)
    {
        $row = Db::name('shop_job_lock')->where('job_name', $name)->find();
        if (!$row) {
            try {
                Db::name('shop_job_lock')->insert(['job_name' => $name, 'owner' => $this->owner, 'locked_until' => time() + $ttl, 'updatetime' => time()]);
                return true;
            } catch (\Exception $e) {
                return false;
            }
        }
        if ((int)$row['locked_until'] > time() && $row['owner'] !== $this->owner) {
            return false;
        }
        return (bool)Db::name('shop_job_lock')->where('id', $row['id'])->where('version', $row['version'])->update([
            'owner' => $this->owner, 'locked_until' => time() + $ttl, 'version' => (int)$row['version'] + 1, 'updatetime' => time(),
        ]);
    }

    protected function release($name)
    {
        Db::name('shop_job_lock')->where('job_name', $name)->where('owner', $this->owner)->update(['locked_until' => 0, 'owner' => '', 'updatetime' => time()]);
    }
}
