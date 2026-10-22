<?php

namespace addons\shop\library\v5;

use think\Db;

class AgentMemberService
{
    public function exchange($authorization, array $payload, $auth)
    {
        $identity = (new AgentSessionVerifier())->verify($authorization);
        $client = trim((string)getenv('SHOP_AGENT_CLIENT_ID'));
        if ($client === '' || strlen($client) > 64) throw new DomainException('商城身份来源尚未配置', 50301, 503);
        $allowed = ['account', 'password', 'create_member'];
        if (array_diff(array_keys($payload), $allowed)) throw new DomainException('账号关联参数无效', 40001, 400);
        $binding = array_key_exists('account', $payload) || array_key_exists('password', $payload);
        if (array_key_exists('create_member', $payload) && !is_bool($payload['create_member'])) {
            throw new DomainException('账号关联参数无效', 40001, 400);
        }
        // A verified first-party login establishes one commerce identity automatically.
        // Never merge by a client-supplied username or phone; existing bindings win.
        $create = $payload === [] || ($payload['create_member'] ?? false) === true;
        if (($binding && $create) || ($binding && (!is_string($payload['account'] ?? null) || !is_string($payload['password'] ?? null) ||
            $payload['account'] === '' || strlen($payload['account']) > 100 || $payload['password'] === '' || strlen($payload['password']) > 128))) {
            throw new DomainException('请输入原商城用户账号和密码', 40001, 400);
        }
        $lookup = ['client_id' => $client, 'external_user_ref' => $identity['ref']];
        $mapping = Db::name('shop_external_identity')->where($lookup)->find();
        if (!$mapping && !$binding && !$create) throw new DomainException('请关联原商城用户，或确认创建新用户', 40940, 409);

        // Password verification keeps the existing member login lockout and credentials unchanged.
        if ($binding && !$auth->login($payload['account'], $payload['password'])) {
            throw new DomainException('商城用户账号或密码错误，或账号暂不可登录', 40100, 401);
        }
        $boundUser = $binding ? (int)$auth->id : null;
        Db::startTrans();
        try {
            // The deployed PostgreSQL backend serializes first-time exchanges before a row exists.
            if (config('database.type') === 'pgsql') Db::query('SELECT pg_advisory_xact_lock(hashtext(:identity))', ['identity' => $client . ':' . $identity['ref']]);
            if ($boundUser) {
                $user = Db::name('user')->where('id', $boundUser)->lock(true)->find();
                if (!$user || $user['status'] !== 'normal') throw new DomainException('商城账号不可登录', 40301, 403);
                $other = Db::name('shop_external_identity')->where(['client_id' => $client, 'user_id' => $boundUser])->find();
                if ($other && ($other['external_user_ref'] !== $identity['ref'] || $other['status'] !== 'normal')) {
                    throw new DomainException('该商城用户已关联其他账号，请核对后重试', 40941, 409);
                }
            }
            $mapping = Db::name('shop_external_identity')->where($lookup)->lock(true)->find();
            if ($mapping) {
                $user = Db::name('user')->where('id', $mapping['user_id'])->lock(true)->find();
                if ($boundUser && $boundUser !== (int)$mapping['user_id']) throw new DomainException('小程序账号已关联其他用户', 40941, 409);
                if ($mapping['status'] !== 'normal' || !$user || $user['status'] !== 'normal' || !$auth->direct($user['id'])) {
                    throw new DomainException('商城账号不可登录', 40301, 403);
                }
            } else {
                if (!$boundUser) {
                    $username = 'agent_' . substr(hash('sha256', $client . ':' . $identity['ref']), 0, 24);
                    if (!$auth->register($username, bin2hex(random_bytes(24)))) throw new DomainException('用户创建结果待确认，请重新进入商城', 40901, 409);
                }
                Db::name('shop_external_identity')->insert(array_merge($lookup, [
                    'user_id' => (int)$auth->id, 'status' => 'normal', 'createtime' => time(), 'updatetime' => time(),
                ]));
            }
            Db::commit();
        } catch (\Throwable $e) {
            Db::rollback();
            $auth->logout();
            throw $e;
        }
        return $identity['id'];
    }
}
