<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\DomainException;
use fast\Http;
use think\Db;

class CommerceSession extends Base
{
    protected $noNeedLogin = ['wechat', 'login'];

    private function sessionData()
    {
        $namespace = getenv('SHOP_IDENTITY_NAMESPACE') ?: hash('sha256', implode(':', [config('database.type'),config('database.hostname'),config('database.database'),config('database.prefix')]));
        return ['user'=>$this->auth->getUserinfo(), 'identity_namespace'=>$namespace, 'local_test_payment'=>LocalTestPayment::enabled()];
    }

    public function login()
    {
        return $this->execute(function () {
            $p = $this->input();
            if (!$this->auth->login(isset($p['account']) ? $p['account'] : '', isset($p['password']) ? $p['password'] : '')) {
                throw new DomainException('账号或密码错误，或账号暂不可登录', 40100, 401);
            }
            return $this->sessionData();
        });
    }

    public function wechat()
    {
        return $this->execute(function () {
            $p = $this->input();
            $appId = trim((string)getenv('SHOP_WECHAT_APP_ID'));
            $secret = trim((string)getenv('SHOP_WECHAT_APP_SECRET'));
            if (!$appId || !$secret) throw new DomainException('微信登录尚未配置', 50301, 503);
            if (empty($p['code'])) throw new DomainException('缺少微信登录凭证', 40001, 400);
            $body = Http::get('https://api.weixin.qq.com/sns/jscode2session', [
                'appid' => $appId, 'secret' => $secret, 'js_code' => $p['code'], 'grant_type' => 'authorization_code',
            ], [CURLOPT_SSL_VERIFYPEER => true, CURLOPT_SSL_VERIFYHOST => 2]);
            $result = json_decode($body, true);
            if (!is_array($result) || empty($result['openid']) || !empty($result['errcode'])) {
                throw new DomainException('微信登录校验失败，请重新登录', 40101, 401);
            }
            $openid = $result['openid'];
            Db::startTrans();
            try {
                $identity = Db::name('shop_miniapp_identity')->where(['app_id' => $appId, 'openid' => $openid])->find();
                if (!$identity) {
                    $username = 'wx_' . substr(hash('sha256', $appId . ':' . $openid), 0, 24);
                    if (!$this->auth->register($username, bin2hex(random_bytes(24)))) {
                        throw new DomainException('微信账号创建失败，请重试', 40901, 409);
                    }
                    $uid = $this->auth->id;
                    Db::name('shop_miniapp_identity')->insert(['app_id' => $appId, 'openid' => $openid, 'user_id' => $uid, 'createtime' => time()]);
                } else {
                    $user = Db::name('user')->where('id', $identity['user_id'])->find();
                    if (!$user || $user['status'] !== 'normal' || !$this->auth->direct($identity['user_id'])) {
                        throw new DomainException('账号不可登录', 40301, 403);
                    }
                }
                Db::commit();
            } catch (\Exception $e) {
                Db::rollback();
                throw $e;
            }
            return $this->sessionData();
        });
    }

    public function detail()
    {
        return $this->execute(function () { $this->userId(); return $this->sessionData(); });
    }

    public function logout()
    {
        return $this->execute(function () { $this->userId(); $this->auth->logout(); return ['logged_out' => true]; });
    }
}
