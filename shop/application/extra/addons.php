<?php

return [
    'autoload' => false,
    'hooks' => [
        'upgrade' => [
            'shop',
        ],
        'app_init' => [
            'shop',
        ],
        'view_filter' => [
            'shop',
        ],
        'user_sidenav_after' => [
            'shop',
        ],
        'xunsearch_config_init' => [
            'shop',
        ],
        'xunsearch_index_reset' => [
            'shop',
        ],
        'meilisearch_config_init' => [
            'shop',
        ],
        'meilisearch_index_reset' => [
            'shop',
        ],
    ],
    'route' => [
        '/shop/$' => 'shop/index/index',
        '/shop/a/[:id]' => 'shop/goods/index',
        '/shop/p/[:diyname]' => 'shop/page/index',
        '/shop/s' => 'shop/search/index',
        '/shop/c/[:diyname]' => 'shop/category/index',
        '/shop/coupon/[:coupon]' => 'shop/coupon/show',
        '/shop/coupon' => 'shop/coupon/index',
        '/shop/exchange/[:id]' => 'shop/exchange/show',
        '/shop/exchange' => 'shop/exchange/index',
    ],
    'priority' => [],
    'domain' => '',
];
