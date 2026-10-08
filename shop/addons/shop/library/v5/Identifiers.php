<?php

namespace addons\shop\library\v5;

class Identifiers
{
    public static function requestId()
    {
        return self::make('req');
    }

    public static function make($prefix)
    {
        try {
            $random = bin2hex(random_bytes(8));
        } catch (\Exception $e) {
            $random = substr(sha1(uniqid('', true) . mt_rand()), 0, 16);
        }
        return strtolower($prefix) . '_' . date('YmdHis') . '_' . $random;
    }
}
