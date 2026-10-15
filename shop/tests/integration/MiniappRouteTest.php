<?php

require dirname(__DIR__) . '/bootstrap.php';

$config = \think\Config::get();
$routes = [
    ['POST', '/api/v1/commerce/session/login', 'api.v1.commerce_session', 'login'],
    ['POST', '/api/v1/commerce/session/wechat', 'api.v1.commerce_session', 'wechat'],
    ['GET', '/api/v1/commerce/session', 'api.v1.commerce_session', 'detail'],
    ['DELETE', '/api/v1/commerce/session', 'api.v1.commerce_session', 'logout'],
    ['GET', '/api/v1/commerce/addresses', 'api.v1.commerce_address', 'index'],
    ['GET', '/api/v1/commerce/areas', 'api.v1.commerce_address', 'areas'],
    ['POST', '/api/v1/commerce/addresses', 'api.v1.commerce_address', 'create'],
    ['PUT', '/api/v1/commerce/addresses/1/default', 'api.v1.commerce_address', 'selectDefault'],
    ['PUT', '/api/v1/commerce/addresses/1', 'api.v1.commerce_address', 'update'],
    ['DELETE', '/api/v1/commerce/addresses/1', 'api.v1.commerce_address', 'remove'],
    ['PUT', '/api/v1/commerce/cart/items/1/selection', 'api.v1.commerce_cart', 'selection'],
    ['GET', '/api/v1/commerce/products/1', 'api.v1.commerce_product', 'detail'],
    ['GET', '/api/v1/commerce/orders/TEST', 'api.v1.commerce_order', 'detail'],
    ['GET', '/api/v1/commerce/orders/TEST/fulfillment', 'api.v1.commerce_fulfillment', 'timeline'],
    ['GET', '/api/v1/commerce/orders/TEST/aftersales/eligibility', 'api.v1.commerce_aftersale', 'eligibility'],
];
foreach ($routes as [$method, $path, $controller, $action]) {
    $request = \think\Request::create($path, $method);
    $dispatch = \think\App::routeCheck($request, $config);
    if (($dispatch['var']['controller'] ?? '') !== $controller || ($dispatch['var']['action'] ?? '') !== $action) {
        throw new RuntimeException('Wrong mini-program route dispatch: ' . $path . ' ' . json_encode($dispatch));
    }
    if (!get_addon_class('shop', 'controller', $controller)) throw new RuntimeException('Missing commerce controller: ' . $controller);
}
echo "Miniapp route registration passed.\n";
