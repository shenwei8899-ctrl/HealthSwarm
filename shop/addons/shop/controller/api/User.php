<?php

namespace addons\shop\controller\api;

use addons\shop\model\Order;
use think\Config;


/**
 * 会员
 */
class User extends Base
{
    protected $noNeedLogin = ['getSigned'];

    public function _initialize()
    {
        parent::_initialize();

        if (!Config::get('fastadmin.usercenter')) {
            $this->error(__('User center already closed'));
        }
    }

    /**
     * 个人中心
     */
    public function index()
    {
        $apptype = $this->request->param('apptype');
        $platform = $this->request->param('platform');
        $logincode = $this->request->param('logincode');

        $info = $this->auth->getUserInfo();
        $info['order'] = [
            'created'  => Order::where('user_id', $this->auth->id)->where('orderstate', 0)->where('paystate', 0)->count(),
            'paid'     => Order::where('user_id', $this->auth->id)->where('orderstate', 0)->where('paystate', 1)->where('shippingstate', 0)->count(),
            'evaluate' => Order::where('user_id', $this->auth->id)->where('orderstate', 0)->where('paystate', 1)->where('shippingstate', 2)->count()
        ];
        $info['avatar'] = cdnurl($info['avatar'], true);
        $signin = get_addon_info('signin');
        $info['is_install_signin'] = ($signin && $signin['state']);

        $firstlogin = $this->auth->jointime === $this->auth->logintime;

        //判断是否显示昵称更新提示
        $profilePrompt = false;
        $config = get_addon_config('shop');
        if ($config['porfilePrompt'] === 'firstlogin') {
            $profilePrompt = $this->auth->jointime === $this->auth->logintime;
        } elseif ($config['porfilePrompt'] === 'everylogin') {
            $profilePrompt = true;
        } elseif ($config['porfilePrompt'] === 'disabled') {
            $profilePrompt = false;
        }
        $showProfilePrompt = false;
        if ($profilePrompt) {
            $showProfilePrompt = !$info['nickname'] || stripos($info['nickname'], '微信用户') !== false || preg_match("/^\d{3}\*{4}\d{4}$/", $info['nickname']);
        }

        $openid = '';
        //如果有传登录code，则获取openid
        if ($logincode) {
            $json = (new \addons\shop\library\Wechat\Service())->getWechatSession($logincode);
            $openid = $json['openid'] ?? '';
        }
        $data['openid'] = $openid;

        $this->success('', [
            'userInfo' => $info,
            'openid'            => $openid,
            'showProfilePrompt' => $showProfilePrompt
        ]);
    }


    /**
     * 个人资料
     */
    public function profile()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $user = $this->auth->getUser();
        $username = $this->request->post('username');
        $nickname = $this->request->post('nickname');
        $bio = $this->request->post('bio');
        $avatar = $this->request->post('avatar');
        if (!$username || !$nickname) {
            $this->error("用户名和昵称不能为空");
        }
        if (strlen($bio) > 100) {
            $this->error("签名太长了！");
        }
        $exists = \app\common\model\User::where('username', $username)->where('id', '<>', $this->auth->id)->find();
        if ($exists) {
            $this->error(__('Username already exists'));
        }

        $avatar = str_replace(cdnurl('', true), '', $avatar);

        $user->username = $username;
        $user->nickname = $nickname;
        $user->bio = $bio;
        $user->avatar = $avatar;
        $user->save();

        $this->success('修改成功！');
    }

    /**
     * 保存头像
     */
    public function avatar()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $user = $this->auth->getUser();
        $avatar = $this->request->post('avatar');
        if (!$avatar) {
            $this->error("头像不能为空");
        }

        $avatar = str_replace(cdnurl('', true), '', $avatar);
        $user->avatar = $avatar;
        $user->save();
        $this->success('修改成功！');
    }

    /**
     * 注销登录
     */
    public function logout()
    {
        if (!$this->request->isPost()) {
            $this->error('请求错误');
        }
        $this->auth->logout();
        $this->success(__('Logout successful'), ['__token__' => $this->request->token()]);
    }

    /**
     * 分享配置参数
     */
    public function getSigned()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $url = $this->request->param('url', '', 'trim');
        $js_sdk = new \addons\shop\library\Jssdk();
        $data = $js_sdk->getSignedPackage($url);
        $this->success('', $data);
    }
}
