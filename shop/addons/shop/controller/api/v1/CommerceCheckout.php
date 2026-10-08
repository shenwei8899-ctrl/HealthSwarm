<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\CheckoutService;
use addons\shop\library\v5\IdempotencyService;

class CommerceCheckout extends Base
{
    public function preview()
    {
        return $this->execute(function () {
            $this->requireMethod('POST');
            $payload = $this->input();
            $userId=$this->userId();
            return (new IdempotencyService())->run('commerce.checkout.preview','miniapp:'.$userId,$this->request->header('idempotency-key'),$payload,function()use($userId,$payload){
                return (new CheckoutService())->preview($userId, $payload, [
                    'request_id' => $this->requestId, 'ip' => $this->request->ip(),
                    'device_id' => $this->request->header('x-device-id'),
                    'displayed_at' => !empty($payload['policy_displayed_at']) ? strtotime($payload['policy_displayed_at']) : time(),
                ]);
            },900);
        });
    }

    public function refresh()
    {
        return $this->preview();
    }
}
