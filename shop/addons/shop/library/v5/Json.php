<?php

namespace addons\shop\library\v5;

class Json
{
    public static function encode($value)
    {
        $json = json_encode($value, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        if ($json === false) {
            throw new DomainException('JSON数据格式不正确', 40002, 400);
        }
        return $json;
    }

    public static function decode($value, $default = [])
    {
        if ($value === null || $value === '') {
            return $default;
        }
        if (is_array($value)) {
            return $value;
        }
        $decoded = json_decode($value, true);
        return json_last_error() === JSON_ERROR_NONE ? $decoded : $default;
    }

    public static function canonical($value)
    {
        return self::encode(self::sortRecursive($value));
    }

    protected static function sortRecursive($value)
    {
        if (!is_array($value)) {
            return $value;
        }
        if (array_keys($value) !== range(0, count($value) - 1)) {
            ksort($value);
        }
        foreach ($value as $key => $item) {
            $value[$key] = self::sortRecursive($item);
        }
        return $value;
    }
}
