<?php

namespace app\index\controller;

class Captcha
{
    public function index($id = '')
    {
        return (new \app\common\library\CaptchaImage((array)config('captcha')))->entry($id);
    }
}
