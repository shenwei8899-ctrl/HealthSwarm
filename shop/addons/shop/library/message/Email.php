<?php

namespace addons\shop\library\message;

use app\common\library\Email as EmailBin;

class Email
{

    //发送邮箱通知
    public function send($data)
    {
        $email = new EmailBin();
        $email->subject($data['title'])
            ->to($data['email'])
            ->message($data['message'])
            ->send();       
    }
}
