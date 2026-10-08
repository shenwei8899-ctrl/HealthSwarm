<?php

namespace addons\shop\controller\api;

use app\common\controller\Api;
use app\common\library\Auth;
use think\Config;
use think\Lang;

class Base extends Api
{
    protected $noNeedLogin = [];
    protected $noNeedRight = ['*'];
    //设置返回的会员字段
    protected $allowFields = ['id', 'username', 'nickname', 'mobile', 'avatar', 'score', 'level', 'bio', 'balance', 'money', 'gender'];

    public function _initialize()
    {

        if (isset($_SERVER['HTTP_ORIGIN'])) {
            header('Access-Control-Expose-Headers: __token__');//跨域让客户端获取到
        }
        //跨域检测
        check_cors_request();

        if (!isset($_COOKIE['PHPSESSID'])) {
            Config::set('session.id', $this->request->server("HTTP_SID"));
        }
        parent::_initialize();
        $config = get_addon_config('shop');

        Config::set('shop', $config);
        Config::set('default_return_type', 'json');
        Auth::instance()->setAllowFields($this->allowFields);

        //判断站点状态
        if (isset($config['openedsite']) && !in_array('uniapp', explode(',', $config['openedsite']))) {
            $this->error('站点已关闭');
        }

        //这里手动载入语言包
        Lang::load(ROOT_PATH . '/addons/shop/lang/zh-cn.php');
        Lang::load(APP_PATH . '/index/lang/zh-cn/user.php');
        //加载当前控制器的语言包
        $controllername = strtolower($this->request->controller());
        $lang = $this->request->langset();
        $lang = preg_match("/^([a-zA-Z\-_]{2,10})\$/i", $lang) ? $lang : 'zh-cn';
        Lang::load(ADDON_PATH . 'shop/lang/' . $lang . '/' . str_replace('.', '/', $controllername) . '.php');
    }

}
