<?php

namespace addons\shop\controller\api;

use addons\shop\library\service\OrderQueryService;
use addons\shop\library\service\OrderService;
use addons\shop\library\service\OrderSubstitutionService;

class CommerceOrder extends Base
{
    public function collection()
    {
        if ($this->request->isGet()) {
            try {
                $result = OrderQueryService::listOrders($this->auth->id, [
                    'page' => $this->request->get('page/d', 1),
                    'page_size' => $this->request->get('page_size/d', 20),
                    'biz_status' => $this->request->get('biz_status', ''),
                    'orderstate' => $this->request->get('orderstate', null),
                    'shippingstate' => $this->request->get('shippingstate', null),
                ]);
            } catch (\Throwable $e) {
                $this->fail($e, 'SHOP_ORDER_QUERY_FAILED');
            }
            $this->success('获取成功', $result);
        }
        if (!$this->request->isPost()) {
            $this->error('请求方式错误', ['error_code' => 'SHOP_METHOD_NOT_ALLOWED'], 405);
        }
        $cartIds = $this->request->post('cart_ids/a', $this->request->post('ids/a', []));
        $idempotencyKey = $this->request->server('HTTP_IDEMPOTENCY_KEY', $this->request->post('idempotency_key', ''));
        if (!$idempotencyKey) {
            $this->error('缺少下单幂等键', ['error_code' => 'SHOP_IDEMPOTENCY_KEY_REQUIRED'], 422);
        }
        try {
            $order = OrderService::createFromCart(
                $this->request->post('address_id/d'),
                $this->auth->id,
                $cartIds,
                $this->request->post('user_coupon_id/d', 0),
                $this->request->post('memo', ''),
                $idempotencyKey,
                $this->request->post('shopping_list_id/d', 0),
                $this->request->post('shopping_list_version/d', 0),
                $this->request->server('HTTP_X_TRACE_ID', ''),
                $this->request->post('checkout_token', '')
            );
            $result = OrderQueryService::detail($order->order_sn, $this->auth->id);
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_ORDER_CREATE_FAILED');
        }
        $this->success('下单成功', $result);
    }

    public function detail()
    {
        try {
            $result = OrderQueryService::detail($this->request->param('order_sn'), $this->auth->id);
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_ORDER_NOT_FOUND');
        }
        $this->success('获取成功', $result);
    }

    public function cancel()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误', ['error_code' => 'SHOP_METHOD_NOT_ALLOWED'], 405);
        }
        try {
            $order = OrderService::cancelUnpaid($this->request->param('order_sn'), $this->auth->id);
            $result = OrderQueryService::detail($order->order_sn, $this->auth->id);
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_ORDER_CANCEL_FAILED');
        }
        $this->success('订单已取消', $result);
    }

    public function shipments()
    {
        try {
            $result = OrderQueryService::shipments($this->request->param('order_sn'), $this->auth->id);
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_SHIPMENT_QUERY_FAILED');
        }
        $this->success('获取成功', ['items' => $result]);
    }

    public function paymentStatus()
    {
        try {
            $result = OrderQueryService::paymentStatus($this->request->param('order_sn'), $this->auth->id);
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_PAYMENT_STATUS_UNKNOWN');
        }
        $this->success('获取成功', $result);
    }

    public function confirmSubstitution()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误', ['error_code' => 'SHOP_METHOD_NOT_ALLOWED'], 405);
        }
        try {
            $result = OrderSubstitutionService::confirm(
                $this->request->param('order_sn'),
                $this->request->param('id/d'),
                $this->auth->id
            );
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_SUBSTITUTION_CONFIRM_FAILED');
        }
        $this->success('替代商品已确认', $result);
    }

    public function rejectSubstitution()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误', ['error_code' => 'SHOP_METHOD_NOT_ALLOWED'], 405);
        }
        try {
            $result = OrderSubstitutionService::reject(
                $this->request->param('order_sn'),
                $this->request->param('id/d'),
                $this->auth->id
            );
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_SUBSTITUTION_REJECT_FAILED');
        }
        $message = !empty($result['order_cancelled']) ? '已拒绝替换并取消订单' : '已拒绝替换并提交退款申请';
        $this->success($message, $result);
    }

    private function fail(\Throwable $e, $errorCode)
    {
        $code = in_array((int)$e->getCode(), [403, 404, 409, 422], true) ? (int)$e->getCode() : 422;
        $this->error($e->getMessage(), ['error_code' => $errorCode], $code);
    }
}
