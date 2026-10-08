<?php

define('APP_PATH', dirname(__DIR__) . DIRECTORY_SEPARATOR . 'application' . DIRECTORY_SEPARATOR);
require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'thinkphp' . DIRECTORY_SEPARATOR . 'base.php';

\think\App::initCommon();
\think\Loader::addNamespace('addons', ROOT_PATH . 'addons' . DS);

$results = (new \addons\shop\library\v5\JobRunner())->runAll();
$failed = array_filter($results, function ($result) {
    return isset($result['status']) && $result['status'] === 'failed';
});

echo json_encode($results, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) . PHP_EOL;
exit($failed ? 1 : 0);
