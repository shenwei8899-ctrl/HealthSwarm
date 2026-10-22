<?php

namespace addons\shop\library\v5;

class AgentSessionVerifier
{
    public function verify($authorization)
    {
        return $this->account($this->request($authorization));
    }

    public function verifyPaymentIdentity($authorization, $code)
    {
        $claims = $this->request($authorization, $code);
        $account = $this->account($claims);
        if (!is_string($claims['appid'] ?? null) || !preg_match('/^wx[0-9a-f]{16}$/iD', $claims['appid']) ||
            !is_string($claims['openid'] ?? null) || !preg_match('/^[A-Za-z0-9_-]{1,128}$/D', $claims['openid'])) {
            throw new DomainException('微信支付身份验证返回无效数据', 50202, 502);
        }
        return $account + ['appid' => $claims['appid'], 'openid' => $claims['openid']];
    }

    protected function request($authorization, $code = null)
    {
        $url = trim((string)getenv('SHOP_AGENT_SESSION_URL'));
        $parts = parse_url($url);
        // Docker Desktop's host alias is needed only for explicitly enabled local linking.
        $hosts = ['127.0.0.1', 'localhost'];
        if (getenv('SHOP_AGENT_ALLOW_DOCKER_HOST') === '1') $hosts[] = 'host.docker.internal';
        $local = $parts && in_array($parts['host'] ?? '', $hosts, true);
        if (!$parts || !empty($parts['user']) || !empty($parts['pass']) || !empty($parts['query']) || !empty($parts['fragment']) ||
            (($parts['scheme'] ?? '') !== 'https' && !(($parts['scheme'] ?? '') === 'http' && $local))) {
            throw new DomainException('商城账号关联服务尚未配置', 50301, 503);
        }
        if (!preg_match('/^Bearer [A-Za-z0-9._~-]{1,8192}$/D', $authorization)) {
            throw new DomainException('请先登录小程序账号', 40100, 401);
        }
        if ($code !== null) {
            // Both endpoints stay on the same configured, trusted Agent origin.
            if (!preg_match('~/auth/wechat/session$~D', $url)) throw new DomainException('商城支付身份服务地址尚未配置', 50301, 503);
            $url = substr($url, 0, -strlen('/session')) . '/payment-identity';
        }
        $curl = curl_init($url);
        curl_setopt_array($curl, [CURLOPT_RETURNTRANSFER => true, CURLOPT_FOLLOWLOCATION => false,
            CURLOPT_CONNECTTIMEOUT => 3, CURLOPT_TIMEOUT => 10, CURLOPT_SSL_VERIFYPEER => true,
            CURLOPT_SSL_VERIFYHOST => 2, CURLOPT_HTTPHEADER => ['Authorization: ' . $authorization, 'Accept: application/json']]);
        if ($code !== null) curl_setopt_array($curl, [CURLOPT_POST => true, CURLOPT_POSTFIELDS => json_encode(['code' => $code]),
            CURLOPT_HTTPHEADER => ['Authorization: ' . $authorization, 'Accept: application/json', 'Content-Type: application/json']]);
        $body = curl_exec($curl);
        $status = (int)curl_getinfo($curl, CURLINFO_HTTP_CODE);
        curl_close($curl);
        $claims = json_decode((string)$body, true);
        if ($status === 401 && ($claims['detail']['code'] ?? '') === 'WECHAT_CODE_INVALID') throw new DomainException('微信凭证已失效，请重新验证', 40012, 400);
        if ($status === 401) throw new DomainException('小程序登录已过期，请重新登录', 40100, 401);
        if (in_array($status, [403, 423], true)) throw new DomainException('小程序账号当前不可使用商城', 40301, 403);
        if ($status === 409) throw new DomainException('当前微信未关联这个小程序账号，请核对后重试', 40943, 409);
        if ($status === 429) throw new DomainException('微信身份验证过于频繁，请稍后再试', 42900, 429);
        if ($status === 503) throw new DomainException('微信身份服务尚未配置完成', 50301, 503);
        if ($body === false || $status !== 200) throw new DomainException('小程序账号验证暂不可用，请稍后重试', 50302, 503);
        return $claims;
    }

    public function account($claims)
    {
        if (($claims['wechat_authenticated'] ?? false) !== true) {
            throw new DomainException('请使用微信登录小程序后继续采购', 40100, 401);
        }
        $id = $claims['account']['id'] ?? null;
        $uid = $claims['account']['uid'] ?? null;
        if (!is_int($id) || $id <= 0 || !is_string($uid) || !preg_match('/^[A-Za-z0-9_-]{1,96}$/D', $uid)) {
            throw new DomainException('小程序账号验证返回无效身份', 50202, 502);
        }
        return ['id' => (string)$id, 'ref' => 'uid:' . $uid];
    }
}
