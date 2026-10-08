<?php

// V5 is the only supported administration surface. The legacy admin menu
// tree was removed; shared runtime services remain available to API routes.
$workspaceRules = [
    ['name' => 'shop/v5/workspace/data', 'title' => '读取业务数据'],
    ['name' => 'shop/v5/workspace/save', 'title' => '维护业务资料'],
    ['name' => 'shop/v5/workspace/remove', 'title' => '删除可删除资料'],
    ['name' => 'shop/v5/workspace/reviewapplication', 'title' => '审核供应商申请'],
    ['name' => 'shop/v5/workspace/retrysupplier', 'title' => '重试供应商推单'],
    ['name' => 'shop/v5/workspace/resolveexception', 'title' => '关闭异常单'],
    ['name' => 'shop/v5/workspace/adjuststock', 'title' => '人工调整库存'],
    ['name' => 'shop/v5/workspace/revalidaterecommendation', 'title' => '重新交易校验'],
    ['name' => 'shop/v5/workspace/retrybatch', 'title' => '重试批次备货'],
    ['name' => 'shop/v5/workspace/publishpolicy', 'title' => '发布政策版本'],
    ['name' => 'shop/v5/workspace/reviewaftersale', 'title' => '审核例外售后'],
    ['name' => 'shop/v5/workspace/retryoutbox', 'title' => '补偿发送事件'],
    ['name' => 'shop/v5/workspace/downloadimporttemplate', 'title' => '下载供应商商品模板'],
    ['name' => 'shop/v5/workspace/previewimport', 'title' => '预检供应商商品目录'],
    ['name' => 'shop/v5/workspace/confirmimport', 'title' => '确认供应商商品导入'],
];

return [
    [
        'name' => 'shop/v5/workspace/dashboard', 'title' => '工作台', 'icon' => 'fa fa-dashboard',
        'ismenu' => 1, 'weigh' => 100,
    ],
    [
        'name' => 'shop_v5_catalog', 'title' => '商品与配餐', 'icon' => 'fa fa-cubes', 'ismenu' => 1, 'weigh' => 90,
        'sublist' => [
            ['name' => 'shop/v5/workspace/product', 'title' => '商品与食材库', 'icon' => 'fa fa-shopping-basket', 'ismenu' => 1],
            ['name' => 'shop/v5/workspace/recommendations', 'title' => '食材包与推荐', 'icon' => 'fa fa-magic', 'ismenu' => 1],
            ['name' => 'shop/v5/workspace/plans', 'title' => 'AI专属计划', 'icon' => 'fa fa-calendar-check-o', 'ismenu' => 1],
            ['name' => 'shop/v5/workspace/purchases', 'title' => '采购清单', 'icon' => 'fa fa-list-alt', 'ismenu' => 1],
        ],
    ],
    [
        'name' => 'shop_v5_orders', 'title' => '订单与履约', 'icon' => 'fa fa-truck', 'ismenu' => 1, 'weigh' => 80,
        'sublist' => [
            ['name' => 'shop/v5/workspace/orders', 'title' => '订单管理', 'icon' => 'fa fa-file-text-o', 'ismenu' => 1],
            ['name' => 'shop/v5/workspace/batches', 'title' => '配送批次', 'icon' => 'fa fa-calendar', 'ismenu' => 1],
            ['name' => 'shop/v5/workspace/fulfillment', 'title' => '备货配送', 'icon' => 'fa fa-archive', 'ismenu' => 1],
            ['name' => 'shop/v5/workspace/aftersales', 'title' => '售后与异常', 'icon' => 'fa fa-exclamation-triangle', 'ismenu' => 1],
        ],
    ],
    [
        'name' => 'shop_v5_supply', 'title' => '供应链', 'icon' => 'fa fa-sitemap', 'ismenu' => 1, 'weigh' => 70,
        'sublist' => [
            ['name' => 'shop/v5/workspace/suppliers', 'title' => '供应商档案', 'icon' => 'fa fa-building-o', 'ismenu' => 1],
            ['name' => 'shop/v5/workspace/supplier_sku', 'title' => '供应商商品', 'icon' => 'fa fa-tags', 'ismenu' => 1],
            ['name' => 'shop/v5/workspace/supplier_collaboration', 'title' => '供应商协同', 'icon' => 'fa fa-exchange', 'ismenu' => 1],
            ['name' => 'shop/v5/workspace/delivery_rules', 'title' => '配送规则', 'icon' => 'fa fa-map-marker', 'ismenu' => 1],
        ],
    ],
    [
        'name' => 'shop_v5_operations', 'title' => '运营与系统', 'icon' => 'fa fa-cogs', 'ismenu' => 1, 'weigh' => 60,
        'sublist' => array_merge([
            ['name' => 'shop/v5/workspace/analytics', 'title' => '经营数据', 'icon' => 'fa fa-line-chart', 'ismenu' => 1],
            ['name' => 'shop/v5/workspace/marketing', 'title' => '营销管理', 'icon' => 'fa fa-bullhorn', 'ismenu' => 1],
            ['name' => 'shop/v5/workspace/members', 'title' => '会员管理', 'icon' => 'fa fa-users', 'ismenu' => 1],
            ['name' => 'shop/v5/workspace/settings', 'title' => '系统配置', 'icon' => 'fa fa-sliders', 'ismenu' => 1],
            ['name' => 'shop/v5/workspace/audit', 'title' => '权限与日志', 'icon' => 'fa fa-shield', 'ismenu' => 1],
        ], $workspaceRules),
    ],
];
