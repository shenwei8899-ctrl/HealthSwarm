<?php
// Ordinary merchant navigation. Compatibility permissions remain hidden.
$workspaceRules = [
    ['name'=>'shop/v5/workspace/commercedetail','title'=>'查看用户与采购交易详情'],
    ['name'=>'shop/v5/workspace/reviewcatalog','title'=>'审核商品资料'],
    ['name' => 'shop/v5/workspace/data', 'title' => '读取业务数据'],
    ['name' => 'shop/v5/workspace/save', 'title' => '维护业务资料'],
    ['name' => 'shop/v5/workspace/remove', 'title' => '删除可删除资料'],
    ['name' => 'shop/v5/workspace/reviewapplication', 'title' => '审核供应商申请'],
    ['name' => 'shop/v5/workspace/retrysupplier', 'title' => '重试供应商推单'],
    ['name' => 'shop/v5/workspace/resolveexception', 'title' => '关闭异常单'],
    ['name' => 'shop/v5/workspace/shiporder', 'title' => '安排普通订单发货'],
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

$menu=[['name'=>'shop/v5/workspace/dashboard','title'=>'工作台','icon'=>'fa fa-dashboard','ismenu'=>1,'weigh'=>100],['name'=>'shop_v5_catalog','title'=>'商品管理','icon'=>'fa fa-folder-open','ismenu'=>1,'weigh'=>90,'sublist'=>[['name'=>'shop/v5/workspace/product','title'=>'商品列表','icon'=>'fa fa-circle-o','ismenu'=>1,'weigh'=>20],['name'=>'shop/v5/workspace/marketing','title'=>'优惠券','icon'=>'fa fa-circle-o','ismenu'=>1,'weigh'=>10]]],['name'=>'shop_v5_orders','title'=>'订单管理','icon'=>'fa fa-folder-open','ismenu'=>1,'weigh'=>80,'sublist'=>[['name'=>'shop/v5/workspace/orders','title'=>'订单列表','icon'=>'fa fa-circle-o','ismenu'=>1,'weigh'=>30],['name'=>'shop/v5/workspace/fulfillment','title'=>'发货与物流','icon'=>'fa fa-circle-o','ismenu'=>1,'weigh'=>20],['name'=>'shop/v5/workspace/aftersales','title'=>'售后退款','icon'=>'fa fa-circle-o','ismenu'=>1,'weigh'=>10]]],['name'=>'shop/v5/workspace/members','title'=>'用户管理','icon'=>'fa fa-users','ismenu'=>1,'weigh'=>70],['name'=>'shop_v5_supply','title'=>'供应商管理','icon'=>'fa fa-folder-open','ismenu'=>1,'weigh'=>60,'sublist'=>[['name'=>'shop/v5/workspace/suppliers','title'=>'供应商档案','icon'=>'fa fa-circle-o','ismenu'=>1,'weigh'=>30],['name'=>'shop/v5/workspace/supplier_sku','title'=>'供货商品','icon'=>'fa fa-circle-o','ismenu'=>1,'weigh'=>20],['name'=>'shop/v5/workspace/supplier_collaboration','title'=>'供应商订单','icon'=>'fa fa-circle-o','ismenu'=>1,'weigh'=>10]]],['name'=>'shop_plain_finance','title'=>'财务管理','icon'=>'fa fa-folder-open','ismenu'=>1,'weigh'=>50,'sublist'=>[['name'=>'shop/v5/workspace/finance','title'=>'财务记录','icon'=>'fa fa-circle-o','ismenu'=>1,'weigh'=>20],['name'=>'shop/v5/workspace/analytics','title'=>'经营统计','icon'=>'fa fa-circle-o','ismenu'=>1,'weigh'=>10]]],['name'=>'shop_v5_operations','title'=>'系统设置','icon'=>'fa fa-folder-open','ismenu'=>1,'weigh'=>40,'sublist'=>[['name'=>'shop/v5/workspace/delivery_rules','title'=>'配送设置','icon'=>'fa fa-circle-o','ismenu'=>1,'weigh'=>40],['name'=>'shop/v5/workspace/settings','title'=>'接口与支付配置','icon'=>'fa fa-circle-o','ismenu'=>1,'weigh'=>30],['name'=>'shop/v5/workspace/audit','title'=>'权限与操作日志','icon'=>'fa fa-circle-o','ismenu'=>1,'weigh'=>20],['name'=>'shop/v5/workspace/technical','title'=>'技术维护','icon'=>'fa fa-circle-o','ismenu'=>1,'weigh'=>10]]]];
$menu[6]['sublist']=array_merge($menu[6]['sublist'],$workspaceRules,[['name'=>'shop/v5/workspace/recommendations','title'=>'兼容管理入口','ismenu'=>0],['name'=>'shop/v5/workspace/plans','title'=>'兼容管理入口','ismenu'=>0],['name'=>'shop/v5/workspace/purchases','title'=>'兼容管理入口','ismenu'=>0],['name'=>'shop/v5/workspace/batches','title'=>'兼容管理入口','ismenu'=>0]]);
return $menu;
