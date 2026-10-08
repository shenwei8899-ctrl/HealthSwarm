<?php

define('APP_PATH', dirname(__DIR__, 2) . DIRECTORY_SEPARATOR . 'application' . DIRECTORY_SEPARATOR);
require dirname(__DIR__, 2) . DIRECTORY_SEPARATOR . 'thinkphp' . DIRECTORY_SEPARATOR . 'base.php';

$config = \think\App::initCommon();
$routes = [
    ['POST', '/api/v1/shop/matching/preview'],
    ['POST', '/api/v1/shop/shopping-lists'],
    ['GET', '/api/v1/shop/shopping-lists'],
    ['GET', '/api/v1/shop/shopping-lists/1'],
    ['POST', '/api/v1/shop/shopping-lists/1/items/1'],
    ['POST', '/api/v1/shop/shopping-lists/1/confirm'],
    ['GET', '/api/v1/shop/cart'],
    ['POST', '/api/v1/shop/cart/items'],
    ['PATCH', '/api/v1/shop/cart/items/1'],
    ['DELETE', '/api/v1/shop/cart/items/1'],
    ['POST', '/api/v1/shop/checkout/preview'],
    ['GET', '/api/v1/shop/goods'],
    ['GET', '/api/v1/shop/goods/1'],
    ['GET', '/api/v1/shop/skus/1/availability'],
    ['GET', '/api/v1/shop/skus/1/substitutes'],
    ['GET', '/api/v1/shop/orders'],
    ['POST', '/api/v1/shop/orders/TEST/cancel'],
    ['GET', '/api/v1/shop/orders/TEST/shipments'],
    ['GET', '/api/v1/shop/orders/TEST/payment-status'],
    ['POST', '/api/v1/shop/orders/TEST/payment'],
    ['POST', '/api/v1/shop/orders/TEST/substitutions/1/confirm'],
    ['POST', '/api/v1/shop/orders/TEST/substitutions/1/reject'],
    ['POST', '/api/v1/shop/payments/wechat/notify'],
    ['GET', '/api/v1/shop/orders/TEST'],
    ['POST', '/api/v1/shop/aftersales'],
    ['POST', '/api/v1/shop/aftersales/1/return-shipment'],
    ['GET', '/api/v1/shop/aftersales/1'],
];
foreach ($routes as $route) {
    $request = \think\Request::create($route[1], $route[0], [], [], [], [
        'REMOTE_ADDR' => '127.0.0.1',
        'HTTP_X_REQUESTED_WITH' => 'XMLHttpRequest',
    ]);
    $dispatch = \think\App::routeCheck($request, $config);
    if (!is_array($dispatch) || $dispatch['type'] !== 'function' || !isset($dispatch['function'])) {
        throw new RuntimeException('Versioned shop route was not registered: ' . $route[1]);
    }
}

echo "Versioned routes integration test passed.\n";
