<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'bootstrap.php';

use think\Db;

function v5AdminAssert($condition, $message)
{
    if (!$condition) {
        throw new RuntimeException($message);
    }
}

$root = dirname(__DIR__, 2);
$legacyRules = Db::name('auth_rule')
    ->where(function ($query) {
        $query->where('name', 'shop')->whereOr('name', 'like', 'shop/%');
    })
    ->where('name', 'not like', 'shop/v5/%')
    ->count();
v5AdminAssert((int)$legacyRules === 0, 'Legacy shop admin permissions still exist.');

$menu = require $root . '/addons/shop/data/menu.php';
$menuNames = [];
$walk = function (array $nodes) use (&$walk, &$menuNames) {
    foreach ($nodes as $node) {
        if (!empty($node['name'])) {
            $menuNames[] = $node['name'];
        }
        if (!empty($node['sublist'])) {
            $walk($node['sublist']);
        }
    }
};
$walk($menu);
v5AdminAssert(count($menuNames) > 0, 'V5 menu is empty.');
v5AdminAssert(!in_array('shop', $menuNames, true), 'Legacy shop menu root is still declared.');
foreach (['shop/v5/workspace/dashboard', 'shop_v5_catalog', 'shop_v5_orders', 'shop_v5_supply', 'shop_v5_operations'] as $rootName) {
    v5AdminAssert(in_array($rootName, $menuNames, true), 'Missing V5 menu root: ' . $rootName);
}

foreach ([
    '/application/admin/controller/shop/v5/Workspace.php',
    '/application/admin/view/shop/v5/workspace.html',
    '/public/assets/js/backend/shop/v5/workspace.js',
] as $artifact) {
    v5AdminAssert(is_file($root . $artifact), 'Missing V5 admin artifact: ' . $artifact);
}

foreach ([
    '/application/admin/controller/shop/Goods.php',
    '/application/admin/controller/shop/Order.php',
    '/application/admin/model/shop/Goods.php',
    '/application/admin/model/shop/Order.php',
    '/application/admin/view/shop/goods/index.html',
    '/public/assets/js/backend/shop/goods.js',
] as $artifact) {
    v5AdminAssert(!is_file($root . $artifact), 'Legacy admin artifact still exists: ' . $artifact);
}

v5AdminAssert(strpos((string)file_get_contents($root . '/addons/shop/library/KdApiExpOrder.php'), 'app\\admin\\model\\shop') === false, 'Runtime logistics service still depends on the old admin model namespace.');
v5AdminAssert(class_exists('addons\\shop\\model\\OrderElectronics'), 'Runtime order electronics model is missing.');

echo "V5 admin surface integration test passed.\n";
