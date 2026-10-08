<?php

namespace addons\shop\library\v5;

use think\Db;

class SignatureService
{
    public function authenticate($request, $expectedType = '')
    {
        $clientId = trim((string)$request->header('x-client-id'));
        $timestamp = (int)$request->header('x-timestamp');
        $nonce = trim((string)$request->header('x-nonce'));
        $signature = trim((string)$request->header('x-signature'));

        if ($clientId === '' || !$timestamp || $nonce === '' || $signature === '') {
            throw new DomainException('服务签名请求头不完整', 40101, 401);
        }
        if (strlen($nonce) < 32 || strlen($nonce) > 64) {
            throw new DomainException('Nonce格式错误', 40102, 401);
        }

        $client = Db::name('shop_integration_client')->where('client_id', $clientId)->where('status', 'normal')->find();
        if (!$client || ($expectedType !== '' && $client['client_type'] !== $expectedType)) {
            throw new DomainException('调用方未授权', 40103, 401);
        }
        $allowedIps = Json::decode($client['allowed_ip_json'], []);
        if ($allowedIps && !in_array((string)$request->ip(), $allowedIps, true)) {
            throw new DomainException('调用来源IP未授权', 40106, 401);
        }
        $skew = max(30, (int)$client['clock_skew_seconds']);
        if (abs(time() - $timestamp) > $skew) {
            throw new DomainException('请求时间已过期', 40104, 401);
        }

        $body = (string)$request->getContent();
        $canonical = strtoupper($request->method()) . "\n"
            . self::normalizePath($request->url()) . "\n"
            . $timestamp . "\n"
            . $nonce . "\n"
            . hash('sha256', $body);
        $expected = hash_hmac('sha256', $canonical, SecretCipher::decrypt($client['secret_ciphertext']));
        if (!hash_equals($expected, strtolower($signature))) {
            throw new DomainException('服务签名验证失败', 40105, 401);
        }

        $nonceHash = hash('sha256', $nonce);
        try {
            Db::name('shop_integration_nonce')->insert([
                'client_id'  => $clientId,
                'nonce_hash' => $nonceHash,
                'expires_at' => time() + $skew * 2,
                'createtime' => time(),
            ]);
        } catch (\Exception $e) {
            throw new DomainException('检测到重复请求', 40902, 409);
        }

        unset($client['secret_ciphertext']);
        return $client;
    }

    public static function sign($method, $path, $timestamp, $nonce, $body, $secret)
    {
        $canonical = strtoupper($method) . "\n"
            . self::normalizePath($path) . "\n"
            . (int)$timestamp . "\n"
            . $nonce . "\n"
            . hash('sha256', (string)$body);
        return hash_hmac('sha256', $canonical, $secret);
    }

    public static function normalizePath($url)
    {
        $path = parse_url((string)$url, PHP_URL_PATH);
        $path = $path === null || $path === false ? (string)$url : $path;
        return '/' . ltrim($path, '/');
    }
}
