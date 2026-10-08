<?php

namespace addons\shop\controller\api;

use addons\shop\library\service\AfterSalesApplicationService;
use addons\shop\library\service\OrderQueryService;

class AftersalesV1 extends Base
{
    public function create()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误', ['error_code' => 'SHOP_METHOD_NOT_ALLOWED'], 405);
        }
        try {
            $result = AfterSalesApplicationService::create(
                $this->request->post('order_goods_id/d'),
                $this->auth->id,
                $this->request->post('type/d'),
                $this->request->post('quantity/d'),
                $this->request->post('reason', ''),
                $this->request->post('images', '')
            );
            $result = OrderQueryService::aftersalesDetail($result['aftersales_id'], $this->auth->id);
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_AFTERSALE_CREATE_FAILED');
        }
        $this->success('售后申请已提交', $result);
    }

    public function detail()
    {
        try {
            $result = OrderQueryService::aftersalesDetail($this->request->param('id/d'), $this->auth->id);
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_AFTERSALE_NOT_FOUND');
        }
        $this->success('获取成功', $result);
    }

    public function returnShipment()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误', ['error_code' => 'SHOP_METHOD_NOT_ALLOWED'], 405);
        }
        try {
            $result = OrderQueryService::saveReturnShipment(
                $this->request->param('id/d'),
                $this->auth->id,
                $this->request->post('express_name', ''),
                $this->request->post('express_no', '')
            );
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_RETURN_SHIPMENT_FAILED');
        }
        $this->success('退货物流已提交', $result);
    }

    private function fail(\Throwable $e, $errorCode)
    {
        $code = in_array((int)$e->getCode(), [403, 404, 409, 422], true) ? (int)$e->getCode() : 422;
        $this->error($e->getMessage(), ['error_code' => $errorCode], $code);
    }
}
