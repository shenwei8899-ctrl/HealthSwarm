<?php

namespace addons\shop\library\v5;

use think\Db;

/** Stores verified access metadata; never stores bearer tokens or family profiles. */
class MiniappUserAccessService
{
    public function record($client, array $identity, $userId)
    {
        $where = ['client_id' => $client, 'external_user_ref' => $identity['ref'], 'user_id' => (int)$userId];
        $mapping = Db::name('shop_external_identity')->where($where)->lock(true)->find();
        if (!$mapping || $mapping['status'] !== 'normal') throw new DomainException('小程序账号关联不可用', 40941, 409);
        if ($mapping['external_account_id'] !== '' && $mapping['external_account_id'] !== (string)$identity['id']) {
            throw new DomainException('小程序账号标识发生冲突，请核对后重试', 40943, 409);
        }
        $channel = $identity['login_channel'] ?? 'unknown';
        if (!in_array($channel, ['wechat', 'other', 'unknown'], true)) throw new DomainException('登录来源无效', 50202, 502);
        $data = ['external_account_id' => (string)$identity['id'], 'last_login_channel' => $channel,
            'last_seen_at' => max(time(), (int)$mapping['last_seen_at'])];
        if (isset($identity['name']) && $identity['name'] !== '') $data['external_account_name'] = $identity['name'];
        // Historical bindings and payment OpenIDs are not evidence of a verified login.
        if ($channel === 'wechat') $data['last_wechat_verified_at'] = $data['last_seen_at'];
        Db::name('shop_external_identity')->where('id', $mapping['id'])->update($data);
    }

    public function decorateUsers(array &$users)
    {
        if (!$users) return;
        $ids = array_map('intval', array_column($users, 'id'));
        $maps = [];
        foreach (Db::name('shop_external_identity')->where('user_id', 'in', $ids)->order('last_seen_at', 'desc')->order('id', 'desc')->select() as $map) {
            $maps[(int)$map['user_id']][] = $map;
        }
        $appid = trim((string)getenv('SHOP_WECHAT_APP_ID'));
        $paymentUsers = $appid === '' ? [] : Db::name('shop_miniapp_identity')->where('app_id', $appid)->where('user_id', 'in', $ids)->column('user_id');
        $paymentUsers = array_map('intval', $paymentUsers);
        foreach ($users as &$user) {
            $links = $maps[(int)$user['id']] ?? [];
            $latest = $links ? $links[0] : [];
            $active = array_filter($links, function ($link) { return $link['status'] === 'normal'; });
            $first = array_filter(array_column($links, 'createtime'));
            $wechat = $links ? max(array_column($links, 'last_wechat_verified_at')) : 0;
            $bound = in_array((int)$user['id'], $paymentUsers, true);
            $user['account_source'] = $links ? '小程序用户' : ($bound ? '商城微信用户' : '商城账号');
            $user['linked_account'] = $latest['external_user_ref'] ?? '';
            $user['external_account_name'] = $latest['external_account_name'] ?? '';
            $user['binding_status'] = $active ? '已关联' : ($links ? '关联停用' : '未关联');
            $user['last_login_channel'] = $latest['last_login_channel'] ?? 'unknown';
            $user['login_method'] = ['wechat' => '微信登录', 'other' => '其他登录', 'unknown' => '尚未记录'][$user['last_login_channel']] ?? '尚未记录';
            $user['first_connected_at'] = $first ? (int)min($first) : 0;
            $user['last_connected_at'] = $links ? (int)max(array_column($links, 'last_seen_at')) : 0;
            $user['last_wechat_verified_at'] = (int)$wechat;
            $user['wechat_login_status'] = $wechat ? '有微信登录验证记录' : '尚无微信登录验证记录';
            $user['wechat_payment_status'] = $appid === '' ? '未配置商城小程序 AppID' : ($bound ? '支付 OpenID 已绑定' : '支付 OpenID 未绑定');
            $user['payment_identity_bound'] = $bound;
            $user['external_login'] = (bool)$links;
            $user['identity_links'] = array_map(function ($link) {
                return array_intersect_key($link, array_flip(['client_id','external_user_ref','external_account_id','external_account_name','status','createtime','last_seen_at','last_login_channel','last_wechat_verified_at']));
            }, $links);
        }
        unset($user);
    }
}
