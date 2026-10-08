<?php

namespace addons\shop\library\v5;

use think\Config;

class SecretCipher
{
    public static function encrypt($plainText)
    {
        $key = self::key();
        $iv = random_bytes(12);
        $tag = '';
        $cipher = openssl_encrypt($plainText, 'aes-256-gcm', $key, OPENSSL_RAW_DATA, $iv, $tag);
        if ($cipher === false) {
            throw new DomainException('密钥加密失败', 50010, 500);
        }
        return 'enc:v1:' . base64_encode($iv) . ':' . base64_encode($tag) . ':' . base64_encode($cipher);
    }

    public static function decrypt($value)
    {
        if (strpos($value, 'enc:v1:') !== 0) {
            throw new DomainException('集成密钥未加密或格式无效', 50011, 500);
        }
        $parts = explode(':', $value, 5);
        $plain = openssl_decrypt(base64_decode($parts[4]), 'aes-256-gcm', self::key(), OPENSSL_RAW_DATA, base64_decode($parts[2]), base64_decode($parts[3]));
        if ($plain === false) {
            throw new DomainException('集成密钥解密失败', 50012, 500);
        }
        return $plain;
    }

    protected static function key()
    {
        $material = trim((string)getenv('SHOP_V5_MASTER_KEY'));
        $config = get_addon_config('shop');
        if ($material === '') {
            $material = isset($config['v5_master_key']) ? trim($config['v5_master_key']) : '';
        }
        if ($material === '') {
            $material = (string)Config::get('app_key');
        }
        if ($material === '') {
            throw new DomainException('请先配置V5主密钥', 50013, 500);
        }
        return hash('sha256', $material, true);
    }
}
