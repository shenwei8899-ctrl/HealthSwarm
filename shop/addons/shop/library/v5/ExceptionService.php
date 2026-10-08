<?php

namespace addons\shop\library\v5;

use think\Db;

class ExceptionService
{
    public function open($dedupeKey, $module, $type, $summary, array $refs = [], array $details = [], $severity = 'medium')
    {
        $existing = Db::name('shop_exception_order')->where('dedupe_key', $dedupeKey)->find();
        if ($existing) {
            $update = ['summary' => $summary, 'detail_json' => Json::encode($details), 'severity' => $severity, 'updatetime' => time()];
            $reopened = false;
            if (in_array($existing['status'], ['resolved', 'closed'], true)) {
                $update += ['status' => 'open', 'resolved_at' => 0, 'resolution' => '', 'assignee_admin_id' => 0];
                $reopened = true;
            }
            Db::name('shop_exception_order')->where('id', $existing['id'])->update($update);
            if ($reopened && in_array($severity, ['high', 'critical'], true)) {
                AlertService::notify('business_exception_reopened', $summary, ['module' => $module, 'type' => $type, 'resource_ref' => isset($refs['resource_ref']) ? $refs['resource_ref'] : '']);
            }
            return $existing['exception_sn'];
        }
        $sn = Identifiers::make('exception');
        Db::name('shop_exception_order')->insert([
            'exception_sn' => $sn, 'dedupe_key' => $dedupeKey, 'severity' => $severity,
            'module' => $module, 'exception_type' => $type,
            'resource_type' => isset($refs['resource_type']) ? $refs['resource_type'] : '',
            'resource_ref' => isset($refs['resource_ref']) ? $refs['resource_ref'] : '',
            'order_sn' => isset($refs['order_sn']) ? $refs['order_sn'] : '',
            'batch_id' => isset($refs['batch_id']) ? (int)$refs['batch_id'] : 0,
            'supplier_order_id' => isset($refs['supplier_order_id']) ? (int)$refs['supplier_order_id'] : 0,
            'summary' => $summary, 'detail_json' => Json::encode($details), 'status' => 'open',
            'createtime' => time(), 'updatetime' => time(),
        ]);
        if (in_array($severity, ['high', 'critical'], true)) {
            AlertService::notify('business_exception_opened', $summary, ['module' => $module, 'type' => $type, 'resource_ref' => isset($refs['resource_ref']) ? $refs['resource_ref'] : '', 'exception_sn' => $sn]);
        }
        return $sn;
    }
}
