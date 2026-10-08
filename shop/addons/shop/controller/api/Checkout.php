<?php

namespace addons\shop\controller\api;

use addons\shop\library\service\OrderService;

class Checkout extends Base
{
    public function preview()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误', ['error_code' => 'SHOP_METHOD_NOT_ALLOWED'], 405);
        }
        try {
            $result = OrderService::previewCart(
                $this->request->post('address_id/d'),
                $this->auth->id,
                $this->request->post('cart_ids/a', $this->request->post('ids/a', [])),
                $this->request->post('user_coupon_id/d', 0),
                $this->request->post('shopping_list_id/d', 0),
                $this->request->post('shopping_list_version/d', 0)
            );
        } catch (\Throwable $e) {
            $code = in_array((int)$e->getCode(), [404, 409, 422], true) ? (int)$e->getCode() : 422;
            $this->error($e->getMessage(), ['error_code' => 'SHOP_CHECKOUT_INVALID'], $code);
        }
        $this->success('结算校验通过', $result);
    }
}
