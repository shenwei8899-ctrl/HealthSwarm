<?php

// +----------------------------------------------------------------------
// | ThinkPHP [ WE CAN DO IT JUST THINK ]
// +----------------------------------------------------------------------
// | Copyright (c) 2006~2016 http://thinkphp.cn All rights reserved.
// +----------------------------------------------------------------------
// | Licensed ( http://www.apache.org/licenses/LICENSE-2.0 )
// +----------------------------------------------------------------------
// | Author: liu21st <liu21st@gmail.com>
// +----------------------------------------------------------------------

return [
    'api/v1/shop/goods$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.catalog', 'index');
    },
    'api/v1/shop/goods/:id$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.catalog', 'detail');
    },
    'api/v1/shop/skus/:id/availability$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.catalog', 'availability');
    },
    'api/v1/shop/skus/:id/substitutes$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.catalog', 'substitutes');
    },
    'api/v1/shop/matching/preview$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.matching', 'preview');
    },
    'api/v1/shop/shopping-lists$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.shopping_list', 'collection');
    },
    'api/v1/shop/shopping-lists/:id$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.shopping_list', 'detail');
    },
    'api/v1/shop/shopping-lists/:id/items/:item_id$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.shopping_list', 'updateItem');
    },
    'api/v1/shop/shopping-lists/:id/confirm$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.shopping_list', 'confirm');
    },
    'api/v1/shop/cart$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.cart_v1', 'collection');
    },
    'api/v1/shop/cart/items$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.cart_v1', 'collection');
    },
    'api/v1/shop/cart/items/:id$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.cart_v1', 'item');
    },
    'api/v1/shop/checkout/preview$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.checkout', 'preview');
    },
    'api/v1/shop/orders$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.commerce_order', 'collection');
    },
    'api/v1/shop/orders/:order_sn/cancel$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.commerce_order', 'cancel');
    },
    'api/v1/shop/orders/:order_sn/shipments$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.commerce_order', 'shipments');
    },
    'api/v1/shop/orders/:order_sn/payment-status$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.commerce_order', 'paymentStatus');
    },
    'api/v1/shop/orders/:order_sn/payment$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.commerce_payment', 'create');
    },
    'api/v1/shop/orders/:order_sn/substitutions/:id/confirm$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.commerce_order', 'confirmSubstitution');
    },
    'api/v1/shop/orders/:order_sn/substitutions/:id/reject$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.commerce_order', 'rejectSubstitution');
    },
    'api/v1/shop/payments/wechat/notify$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.commerce_payment', 'notify');
    },
    'api/v1/shop/orders/:order_sn$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.commerce_order', 'detail');
    },
    'api/v1/shop/aftersales$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.aftersales_v1', 'create');
    },
    'api/v1/shop/aftersales/:id/return-shipment$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.aftersales_v1', 'returnShipment');
    },
    'api/v1/shop/aftersales/:id$' => function () {
        return (new \think\addons\Route())->execute('shop', 'api.aftersales_v1', 'detail');
    },
    //别名配置,别名只能是映射到控制器且访问时必须加上请求的方法
    '__alias__'   => [
    ],
    //变量规则
    '__pattern__' => [
    ],
//        域名绑定到模块
//        '__domain__'  => [
//            'admin' => 'admin',
//            'api'   => 'api',
//        ],
];
