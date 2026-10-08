<?php

namespace addons\shop\library\message;

use addons\shop\library\message\Mini;
use addons\shop\library\message\Mp;
use addons\shop\library\message\Email;
use addons\shop\library\message\Mobile;

class Service
{

    //分发数据
    //根据组装的数据发送
    public static function send($type, $data)
    {
        switch ($type) {
            case 1:
                $obj = new Mp();
                break;
            case 2:
                $obj = new Mini();
                break;
            case 3:
                $obj = new Email();
                break;
            case 4:
                $obj = new Mobile();
                break;
            default:
                throw new \Exception('类型不存在');
        }
        //异步并发发送
        $obj->send($data);
    }
}
