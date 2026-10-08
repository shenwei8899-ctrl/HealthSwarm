<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\DomainException;
use addons\shop\library\v5\IdempotencyService;
use addons\shop\library\v5\SupplierOrderService;
use think\Db;

class IntegrationSupplier extends IntegrationBase
{
    protected $expectedClientType = 'supplier';

    public function callback($supplier_code = null)
    {
        return $this->execute(function () use ($supplier_code) {
            $this->requireMethod('POST');
            $payload = $this->input();
            if ($supplier_code !== null && $supplier_code !== $this->clientId()) {
                throw new DomainException('供应商路径与签名调用方不一致', 40106, 401);
            }
            $supplier = Db::name('shop_supplier')->where('supplier_code', $this->clientId())->where('status', 'normal')->find();
            if (!$supplier) {
                throw new DomainException('供应商档案未绑定调用方', 40106, 401);
            }
            return (new IdempotencyService())->run('supplier.callback', $this->clientId(), $this->request->header('idempotency-key'), $payload, function () use ($supplier, $payload) {
                return (new SupplierOrderService())->applyCallback($supplier['id'], $payload);
            });
        }, $this->integrationLog('supplier_order_callback', 'supplier_order'));
    }
}
