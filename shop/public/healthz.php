<?php

define('APP_PATH', dirname(__DIR__) . DIRECTORY_SEPARATOR . 'application' . DIRECTORY_SEPARATOR);
require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'thinkphp' . DIRECTORY_SEPARATOR . 'base.php';

header('Content-Type: text/plain; charset=utf-8');
try {
    \think\App::initCommon();
    \think\Db::query('SELECT 1');
    http_response_code(200);
    echo "ok\n";
} catch (\Throwable $e) {
    http_response_code(503);
    echo "unavailable\n";
}
