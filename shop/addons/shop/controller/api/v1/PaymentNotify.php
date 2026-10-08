<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\service\WechatPayService;
use think\Response;

class PaymentNotify extends Base
{
    protected $noNeedLogin=['*'];

    public function wechat()
    {
        try{
            $response=WechatPayService::handlePaidNotify((string)getenv('SHOP_WECHAT_NOTIFY_URL'));
            return Response::create($response->getContent(),'html',$response->getStatusCode(),$response->headers->all());
        }catch(\Throwable $e){\think\Log::write('[shop][v5][wechat-notify]'.$e->getMessage(),'error');return Response::create('<xml><return_code><![CDATA[FAIL]]></return_code><return_msg><![CDATA['.htmlspecialchars($e->getMessage(),ENT_XML1).']]></return_msg></xml>','html',500);}
    }

    public function refund()
    {
        try{
            $response=WechatPayService::handleRefundedNotify((string)getenv('SHOP_WECHAT_NOTIFY_URL'));
            return Response::create($response->getContent(),'html',$response->getStatusCode(),$response->headers->all());
        }catch(\Throwable $e){\think\Log::write('[shop][v5][refund-notify]'.$e->getMessage(),'error');return Response::create('<xml><return_code><![CDATA[FAIL]]></return_code><return_msg><![CDATA['.htmlspecialchars($e->getMessage(),ENT_XML1).']]></return_msg></xml>','html',500);}
    }
}
