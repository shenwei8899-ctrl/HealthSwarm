<?php

namespace addons\shop\library\v5;

use think\Db;

class IntegrationLogger
{
    protected static $sensitiveKeys = [
        'authorization', 'token', 'access_token', 'openid', 'mobile', 'phone',
        'address', 'detail', 'secret', 'signature', 'credential', 'prepay_id',
    ];

    public static function write(array $data)
    {
        $defaults = [
            'request_id' => Identifiers::requestId(), 'partner_type' => '', 'partner_code' => '',
            'direction' => 'inbound', 'interface_name' => '', 'method' => '', 'url_path' => '',
            'business_type' => '', 'business_ref' => '', 'request_headers_masked' => '',
            'request_body_masked' => '', 'response_code' => '', 'response_body_masked' => '',
            'http_status' => 0, 'duration_ms' => 0, 'success' => 0, 'retry_count' => 0,
            'error_code' => '', 'createtime' => time(),
        ];
        foreach (['request_headers_masked', 'request_body_masked', 'response_body_masked'] as $field) {
            if (isset($data[$field]) && is_array($data[$field])) {
                $data[$field] = Json::encode(self::mask($data[$field]));
            }
            if (isset($data[$field])) {
                $data[$field] = mb_substr((string)$data[$field], 0, 8000);
            }
        }
        try {
            Db::name('shop_integration_log')->insert(array_merge($defaults, $data));
        } catch (\Exception $e) {
            // Logging must never make the business transaction fail.
        }
    }

    public static function mask($value)
    {
        if (!is_array($value)) {
            return $value;
        }
        $result = [];
        foreach ($value as $key => $item) {
            if (in_array(strtolower((string)$key), self::$sensitiveKeys, true)) {
                $result[$key] = '***';
            } else {
                $result[$key] = is_array($item) ? self::mask($item) : $item;
            }
        }
        return $result;
    }
}
