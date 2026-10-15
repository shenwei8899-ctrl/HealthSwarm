<?php

namespace addons\shop\library\v5;

class MediaUrl
{
    public static function absolute($path)
    {
        $path = trim((string)$path);
        if ($path === '' || preg_match('#^https?://#i', $path)) return $path;
        $base = rtrim(getenv('SHOP_MEDIA_BASE_URL') ?: \think\Request::instance()->domain(), '/');
        return $base . '/' . ltrim($path, '/');
    }
}
