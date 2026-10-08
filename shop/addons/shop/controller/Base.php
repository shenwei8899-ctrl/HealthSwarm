<?php

namespace addons\shop\controller;

use addons\shop\model\Carts;
use think\Validate;

/**
 * 商城控制器基类
 */
class Base extends \think\addons\Controller
{

    // 初始化
    public function __construct()
    {
        parent::__construct();

        $config = get_addon_config('shop');
        // 设定主题模板目录
        $this->view->engine->config('view_path', $this->view->engine->config('view_path') . $config['theme'] . DS);
        // 加载自定义标签库
        $this->view->engine->config('taglib_pre_load', 'addons\shop\taglib\Shop');
        // 默认渲染栏目为空
        $this->view->assign('__CHANNEL__', null);
        $this->view->assign('isWechat', strpos($this->request->server('HTTP_USER_AGENT'), 'MicroMessenger') !== false);
        // 定义SHOP首页的URL
        $config['indexurl'] = addon_url('shop/index/index', [], false);
        $config['cartnums'] = $this->auth->id ? Carts::where('user_id', $this->auth->id)->where('sceneval', 1)->count() : 0;
        \think\Config::set('shop', $config);

        //判断站点状态
        if (isset($config['openedsite']) && !in_array('pc', explode(',', $config['openedsite']))) {
            if ($this->controller != 'order' && $this->action != 'epay') {
                $this->error('站点已关闭');
            }
        }
    }

    public function _initialize()
    {
        parent::_initialize();

        // 如果请求参数action的值为一个方法名,则直接调用
        $action = $this->request->post("action");
        if ($action && $this->request->isPost()) {
            return $this->$action();
        }
    }

    protected function token()
    {
        $token = $this->request->post('__token__');

        //验证Token
        if (!Validate::make()->check(['__token__' => $token], ['__token__' => 'require|token'])) {
            $this->error("Token验证错误，请重试！", '', ['__token__' => $this->request->token()]);
        }

        //刷新Token
        $this->request->token();
    }

    // 判断是否跳转移动H5
    protected function checkredirect($type, $params = [])
    {
        $config = get_addon_config('shop');
        //自动跳转H5
        if (($config['autoredirectmobile'] ?? false) && ($config['mobileurl'] ?? '') && $this->request->isMobile()) {
            $pageArr = [
                'cart'            => "/pages/cart/cart",
                'goods/goods'     => "/pages/goods/goods",
                'goods/detail'    => "/pages/goods/detail",
                'coupon/list'     => "/pages/coupon/coupon",
                'coupon/detail'   => "/pages/coupon/detail",
                'exchange/list'   => "/pages/score/exchange",
            ];
            $pageUrl = $pageArr[$type] ?? '';
            $params = array_filter($params);
            $this->redirect($config['mobileurl'] . "#" . $pageUrl . ($params ? '?' . http_build_query($params) : ''));
        } else {
            return;
        }
    }

}
