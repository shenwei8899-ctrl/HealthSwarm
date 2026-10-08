<?php

namespace addons\shop\controller\api;

use addons\shop\library\service\WechatPayService;
use think\Response;

class CommercePayment extends Base
{
    protected $noNeedLogin = ['notify'];

    public function create()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误', ['error_code' => 'SHOP_METHOD_NOT_ALLOWED'], 405);
        }
        try {
            $notifyUrl = getenv('SHOP_WECHAT_NOTIFY_URL') ?: $this->request->domain() . '/index.php/api/v1/shop/payments/wechat/notify';
            $result = WechatPayService::createMiniProgramPayment(
                $this->request->param('order_sn'),
                $this->auth->id,
                $this->request->post('openid', ''),
                $notifyUrl
            );
        } catch (\Throwable $e) {
            $code = in_array((int)$e->getCode(), [404, 409, 422, 502, 503], true) ? (int)$e->getCode() : 422;
            $this->error($e->getMessage(), ['error_code' => 'SHOP_PAYMENT_CREATE_FAILED'], $code);
        }
        $this->success('微信支付参数创建成功', $result);
    }

    public function notify()
    {
        try {
            $response = WechatPayService::handlePaidNotify((string)getenv('SHOP_WECHAT_NOTIFY_URL'));
            return Response::create($response->getContent(), 'html', $response->getStatusCode(), $response->headers->all());
        } catch (\Throwable $e) {
            return Response::create('<xml><return_code><![CDATA[FAIL]]></return_code><return_msg><![CDATA[' . htmlspecialchars($e->getMessage(), ENT_XML1) . ']]></return_msg></xml>', 'html', 500);
        }
    }
}
