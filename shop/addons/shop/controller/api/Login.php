<?php

namespace addons\shop\controller\api;

use addons\third\model\Third;
use app\common\library\Auth;
use app\common\library\Sms;
use app\common\library\Ems;
use fast\Random;
use think\Validate;
use fast\Http;
use addons\third\library\Service;
use think\Config;
use think\Session;

class Login extends Base
{

    protected $noNeedLogin = ['*'];

    public function _initialize()
    {
        parent::_initialize();
        if (!$this->request->isPost()) {
            $this->error('请求错误');
        }

        Auth::instance()->setAllowFields(array_merge(['username'], $this->allowFields));
    }

    /**
     * 会员登录
     *
     * @param string $account  账号
     * @param string $password 密码
     */
    public function login()
    {
        $account = $this->request->post('account', '');
        $password = $this->request->post('password', '');

        if (!$account || !$password) {
            $this->error(__('Invalid parameters'));
        }

        $ret = $this->auth->login($account, $password);
        if ($ret) {
            $user = $this->auth->getUserinfo();
            $user['avatar'] = cdnurl($user['avatar'], true);
            $this->success(__('Logged in successful'), [
                'token' => $this->auth->getToken(),
                'user'  => $user
            ]);
        } else {
            $this->error($this->auth->getError());
        }
    }

    /**
     * 重置密码
     *
     * @param string $mobile      手机号
     * @param string $newpassword 新密码
     * @param string $captcha     验证码
     */
    public function resetpwd()
    {
        $type = $this->request->param("type");
        $mobile = $this->request->param("mobile");
        $email = $this->request->param("email");
        $newpassword = $this->request->param("newpassword");
        $captcha = $this->request->param("captcha");
        if (!$newpassword || !$captcha) {
            $this->error(__('Invalid parameters'));
        }

        if ($type == 'mobile') {
            if (!Validate::regex($mobile, "^1\d{10}$")) {
                $this->error(__('Mobile is incorrect'));
            }
            $user = \app\common\model\User::getByMobile($mobile);
            if (!$user) {
                $this->error(__('User not found'));
            }
            $ret = Sms::check($mobile, $captcha, 'resetpwd');
            if (!$ret) {
                $this->error(__('Captcha is incorrect'));
            }
            Sms::flush($mobile, 'resetpwd');
        } else {
            if (!Validate::is($email, "email")) {
                $this->error(__('Email is incorrect'));
            }
            $user = \app\common\model\User::getByEmail($email);
            if (!$user) {
                $this->error(__('User not found'));
            }
            $ret = Ems::check($email, $captcha, 'resetpwd');
            if (!$ret) {
                $this->error(__('Captcha is incorrect'));
            }
            Ems::flush($email, 'resetpwd');
        }
        //模拟一次登录
        $this->auth->direct($user->id);
        $ret = $this->auth->changepwd($newpassword, '', true);
        if ($ret) {
            $this->success(__('Reset password successful'));
        } else {
            $this->error($this->auth->getError());
        }
    }

    /**
     * 手机验证码登录
     *
     * @param string $mobile  手机号
     * @param string $captcha 验证码
     */
    public function mobilelogin()
    {
        $mobile = $this->request->post('mobile');
        $captcha = $this->request->post('captcha');
        $invite_id = $this->request->post('invite_id');
        if ($invite_id) {
            \think\Cookie::set('inviter', $invite_id);
        }
        if (!$mobile || !$captcha) {
            $this->error(__('Invalid parameters'));
        }
        if (!Validate::regex($mobile, "^1\d{10}$")) {
            $this->error(__('Mobile is incorrect'));
        }
        if (!Sms::check($mobile, $captcha, 'mobilelogin')) {
            $this->error(__('Captcha is incorrect'));
        }
        $user = \app\common\model\User::getByMobile($mobile);
        if ($user) {
            if ($user->status != 'normal') {
                $this->error(__('Account is locked'));
            }
            //如果已经有账号则直接登录
            $ret = $this->auth->direct($user->id);
        } else {
            $username = method_exists('\fast\Random', 'username')
                ? Random::username()
                : 'user_' . bin2hex(random_bytes(8)) . substr(uniqid(), -8);
            $ret = $this->auth->register($username, Random::alnum(16), '', $mobile, ['nickname' => '用户' . mb_substr($mobile, -4)]);
        }
        if ($ret) {
            Sms::flush($mobile, 'mobilelogin');
            $user = $this->auth->getUserinfo();
            $user['avatar'] = cdnurl($user['avatar'], true);
            $data = ['token' => $this->auth->getToken(), 'user' => $user];
            $this->success(__('Logged in successful'), $data);
        } else {
            $this->error($this->auth->getError());
        }
    }

    /**
     * 注册会员
     *
     * @param string $username 用户名
     * @param string $password 密码
     * @param string $email    邮箱
     * @param string $mobile   手机号
     * @param string $code     验证码
     */
    public function register()
    {
        $username = $this->request->post('username');
        $password = $this->request->post('password');
        $mobile = $this->request->post('mobile');
        $code = $this->request->post('code');
        $invite_id = $this->request->post('invite_id');
        if ($invite_id) {
            \think\Cookie::set('inviter', $invite_id);
        }
        if (!$username || !$password) {
            $this->error(__('Invalid parameters'));
        }
        if ($mobile && !Validate::regex($mobile, "^1\d{10}$")) {
            $this->error(__('Mobile is incorrect'));
        }
        if (Validate::regex($username, '/^1\d{10}$/')) {
            $this->error(__('Username can not be mobile'));
        }
        $ret = Sms::check($mobile, $code, 'register');
        if (!$ret) {
            $this->error(__('Captcha is incorrect'));
        }

        $ret = $this->auth->register($username, $password, '', $mobile, []);
        if ($ret) {
            $user = $this->auth->getUserinfo();
            $user['avatar'] = cdnurl($user['avatar'], true);
            $this->success(__('Sign up successful'), [
                'token' => $this->auth->getToken(),
                'user'  => $user
            ]);
        } else {
            $this->error($this->auth->getError());
        }
    }

    /**
     * 第三方登录[绑定] 小程序
     */
    public function wxLogin()
    {
        $code = $this->request->post("code");
        $rawData = $this->request->post("rawData/a", '', 'trim');
        if (!$code) {
            $this->error("参数不正确");
        }
        $rawData = $rawData ?: ['nickName' => '微信用户'];
        $third = get_addon_info('third');
        if (!$third || !$third['state']) {
            $this->error("请在后台插件管理安装第三方登录插件并启用");
        }

        if (!config('shop.wx_appid') || !config('shop.wx_app_secret')) {
            $this->error("请在后台配置微信小程序参数");
        }

        $json = (new \addons\shop\library\Wechat\Service())->getWechatSession($code);
        if (isset($json['openid'])) {
            $userinfo = [
                'platform'      => 'wechat',
                'apptype'       => 'miniapp',
                'openid'        => $json['openid'],
                'userinfo'      => [
                    'nickname' => $rawData['nickName'] ?? '',
                    'avatar'   => $rawData['avatarUrl'] ?? ''
                ],
                'openname'      => $rawData['nickName'] ?? '',
                'access_token'  => $json['session_key'],
                'refresh_token' => '',
                'expires_in'    => $json['expires_in'] ?? 0,
                'unionid'       => $json['unionid'] ?? ''
            ];

            $third = [
                'nickname' => $rawData['nickName'] ?? '',
                'avatar'   => $rawData['avatarUrl'] ?? ''
            ];
            $user = null;

            if ($this->auth->isLogin() || Service::isBindThird($userinfo['platform'], $userinfo['openid'])) {
                Service::connect($userinfo['platform'], $userinfo);
            } else {
                // 是否自动创建账号
                if (config('shop.wechatautocreate')) {
                    Service::connect($userinfo['platform'], $userinfo);
                } else {
                    Session::set('third-userinfo', $userinfo);
                    $this->success('授权成功!', ['third' => $third, 'openid' => $json['openid'], 'bind' => true]);
                }
            }

            $user = $this->auth->getUserinfo();
            $this->success('授权成功!', ['user' => $user, 'third' => $third, 'openid' => $json['openid']]);
        }
        $this->error("授权失败," . ($json['errmsg'] ?? "未知错误"));
    }

    /**
     * 微信手机号授权登录
     */
    public function wechatMobileLogin()
    {
        $code = $this->request->post("code");
        $logincode = $this->request->post("logincode");
        $bind = $this->request->post("bind");
        $data = (new \addons\shop\library\Wechat\Service())->getWechatMobile($code);
        if ($data) {
            $mobile = $data['phoneNumber'];
            //获取openid和unionid
            $json = (new \addons\shop\library\Wechat\Service())->getWechatSession($logincode);
            $openid = $json['openid'] ?? '';
            $unionid = $json['unionid'] ?? '';

            $user = \app\common\model\User::getByMobile($mobile);
            if ($user) {
                if ($user->status != 'normal') {
                    $this->error(__('Account is locked'));
                }
                //如果已经有账号则直接登录
                $ret = $this->auth->direct($user->id);
            } else {
                $username = method_exists('\fast\Random', 'username')
                    ? Random::username()
                    : 'user_' . bin2hex(random_bytes(8)) . substr(uniqid(), -8);
                $nickname = '用户' . mb_substr($mobile, -4);
                $ret = $this->auth->register($username, Random::alnum(16), '', $mobile, ['nickname' => $nickname]);
            }

            //判断是否绑定模式，openid是否有关联，没有关联的情况下手动进行关联
            if ($bind && $openid) {
                if (Service::isBindThird('wechat', $openid)) {
                    $this->error("手机号已经绑定其它账号");
                }

                // 在第三方登录表中创建关联
                $values = ['user_id' => $this->auth->id, 'platform' => 'wechat', 'openid' => $openid, 'unionid' => $unionid, 'openname' => '微信用户', 'apptype' => 'miniapp'];
                Third::create($values, true);
            }

            if ($ret) {
                $data = ['user' => $this->auth->getUserinfo(), 'token' => $this->auth->getToken(), 'openid' => $openid];
                $this->success('授权成功！', $data);
            } else {
                $this->error($this->auth->getError());
            }
        } else {
            $this->error("授权失败，请重试");
        }
    }

    /**
     * APP登录
     */
    public function appLogin()
    {
        $code = $this->request->post("code");
        $scope = $this->request->post("scope");
        if (!$code) {
            $this->error("参数不正确");
        }
        $third = get_addon_info('third');
        if (!$third || !$third['state']) {
            $this->error("请在后台插件管理安装第三方登录插件并启用");
        }
        Session::set('state', $code);
        $config = [
            'app_id'     => Config::get('shop.app_id'),
            'app_secret' => Config::get('shop.app_secret'),
            'scope'      => $scope
        ];
        if (!$config['app_id'] || !$config['app_secret']) {
            $this->error("请在后台配置移动端APP参数");
        }
        $wechat = new \addons\third\library\Wechat($config);
        $userinfo = $wechat->getUserInfo(['code' => $code, 'state' => $code]);
        if (!$userinfo) {
            $this->error(__('操作失败'));
        }
        //判断是否需要绑定
        $userinfo['apptype'] = 'native';
        $userinfo['platform'] = 'wechat';

        $third = [
            'avatar'   => $userinfo['userinfo']['avatar'],
            'nickname' => $userinfo['userinfo']['nickname']
        ];
        $user = null;
        if ($this->auth->isLogin() || Service::isBindThird($userinfo['platform'], $userinfo['openid'], $userinfo['apptype'], $userinfo['unionid'])) {
            Service::connect($userinfo['platform'], $userinfo);
            $user = $this->auth->getUserinfo();
        } else {
            Session::set('third-userinfo', $userinfo);
        }
        $this->success('授权成功!', ['user' => $user, 'third' => $third]);
    }

    /**
     * 获取Openid(仅用于微信小程序)
     */
    public function getWechatOpenid()
    {
        $code = $this->request->post("logincode");
        $json = (new \addons\shop\library\Wechat\Service())->getWechatSession($code);
        $this->success('获取成功!', ['openid' => $json['openid'] ?? '']);
    }

}
