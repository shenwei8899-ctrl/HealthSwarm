<?php

namespace addons\shop\library\message;

use think\Hook;

class Mobile
{

    public function send($param)
    {
        $params = [
            'mobile'   => $param['mobile'],
            'template' => $param['template_id'],
            'msg'      => $param['data'],
        ];
        Hook::listen('sms_notice', $params, null, true);
    }
}
