<?php
namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\WechatPhoneGateway;
use addons\shop\library\v5\WechatPhoneBindingService;

class CommercePhone extends Base
{
    public function config()
    {
        header('Cache-Control: no-store');
        return $this->execute(function () { $this->userId(); return (new WechatPhoneGateway())->config(); });
    }

    public function detail()
    {
        header('Cache-Control: no-store');
        return $this->execute(function () { return (new WechatPhoneBindingService())->detail($this->userId()); });
    }

    public function bind()
    {
        header('Cache-Control: no-store');
        return $this->execute(function () {
            $this->requireMethod('POST');
            return (new WechatPhoneBindingService())->bind($this->userId(), $this->input(),
                (string)$this->request->header('idempotency-key'));
        });
    }
}
