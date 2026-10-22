<?php

namespace addons\shop\library\v5;

use think\Db;

class AgentWechatPaymentIdentityService
{
    public function bind($userId, $authorization, array $payload)
    {
        if (array_keys($payload) !== ['code'] || !is_string($payload['code']) || $payload['code'] === '' || strlen($payload['code']) > 256) {
            throw new DomainException('微信身份验证仅接受临时 code', 40001, 400);
        }
        $appid = trim((string)getenv('SHOP_WECHAT_APP_ID'));
        $client = trim((string)getenv('SHOP_AGENT_CLIENT_ID'));
        if (!preg_match('/^wx[0-9a-f]{16}$/iD', $appid) || $client === '' || strlen($client) > 64) {
            throw new DomainException('商城微信身份配置尚未完成', 50301, 503);
        }
        $identity = (new AgentSessionVerifier())->verifyPaymentIdentity($authorization, $payload['code']);
        if ($identity['appid'] !== $appid) throw new DomainException('小程序 AppID 与商城配置不一致', 40943, 409);
        Db::startTrans();
        try {
            if (config('database.type') === 'pgsql') Db::query('SELECT pg_advisory_xact_lock(hashtext(:identity))', ['identity' => 'wechat-payment:' . $appid . ':' . $identity['openid']]);
            $user = Db::name('user')->where('id', (int)$userId)->lock(true)->find();
            if (!$user || $user['status'] !== 'normal') throw new DomainException('商城账号不可使用', 40301, 403);
            $mapping = Db::name('shop_external_identity')->where(['client_id' => $client, 'external_user_ref' => $identity['ref']])->lock(true)->find();
            if (!$mapping || $mapping['status'] !== 'normal' || (int)$mapping['user_id'] !== (int)$userId) {
                throw new DomainException('小程序账号与当前商城会员不一致', 40943, 409);
            }
            $existing = Db::name('shop_miniapp_identity')->where(['app_id' => $appid, 'openid' => $identity['openid']])->lock(true)->find();
            $other = Db::name('shop_miniapp_identity')->where(['app_id' => $appid, 'user_id' => (int)$userId])->where('openid', '<>', $identity['openid'])->find();
            if (($existing && (int)$existing['user_id'] !== (int)$userId) || $other) {
                throw new DomainException('微信支付身份已有关联，请核对后重试', 40942, 409);
            }
            if (!$existing) Db::name('shop_miniapp_identity')->insert(['app_id' => $appid, 'openid' => $identity['openid'], 'user_id' => (int)$userId, 'createtime' => time()]);
            Db::commit();
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
        return ['linked' => true, 'app_id' => $appid];
    }
}
