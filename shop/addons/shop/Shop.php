<?php

namespace addons\shop;

use addons\shop\library\Search;
use app\common\library\Menu;
use think\Addons;
use think\Config;
use think\Db;
use think\Request;
use think\Loader;

/**
 * Shop插件
 */
class Shop extends Addons
{

    /**
     * 插件安装方法
     * @return bool
     */
    public function install()
    {
        $menu = include ADDON_PATH . 'shop' . DS . 'data' . DS . 'menu.php';
        Menu::create($menu);

        \addons\shop\library\v5\Migrator::migrate();

        return true;
    }

    /**
     * 插件卸载方法
     * @return bool
     */
    public function uninstall()
    {
        foreach ($this->menuRoots() as $root) {
            Menu::delete($root);
        }
        return true;
    }

    /**
     * 插件启用方法
     */
    public function enable()
    {
        $menu = include ADDON_PATH . 'shop' . DS . 'data' . DS . 'menu.php';
        $this->upgradeMenus($menu);
        foreach ($this->menuRoots() as $root) {
            Menu::enable($root);
        }
    }

    /**
     * 插件禁用方法
     */
    public function disable()
    {
        foreach ($this->menuRoots() as $root) {
            Menu::disable($root);
        }
    }

    /**
     * 插件升级方法
     */
    public function upgrade()
    {
        $menu = include ADDON_PATH . 'shop' . DS . 'data' . DS . 'menu.php';
        $this->upgradeMenus($menu);
        \addons\shop\library\v5\Migrator::migrate();
    }

    protected function menuRoots()
    {
        return ['shop', 'shop/v5/workspace/dashboard', 'shop_v5_catalog', 'shop_v5_orders', 'shop_v5_supply', 'shop_v5_operations'];
    }

    protected function upgradeMenus(array $menu)
    {
        // Remove the obsolete legacy administration tree before syncing V5.
        // Its controllers are retained because APIs and shared services may
        // still reference them, but it is no longer an admin entry point.
        Menu::delete('shop');
        $this->syncMenuTree($menu);
        Menu::refresh('shop', $menu);
    }

    protected function syncMenuTree(array $nodes, $parentId = 0)
    {
        $allowed = array_flip([
            'file', 'name', 'title', 'url', 'icon', 'condition', 'remark',
            'ismenu', 'menutype', 'extend', 'weigh', 'status',
        ]);

        foreach ($nodes as $node) {
            $children = isset($node['sublist']) && is_array($node['sublist']) ? $node['sublist'] : [];
            $data = array_intersect_key($node, $allowed);
            $data['pid'] = (int)$parentId;
            $data['ismenu'] = isset($data['ismenu']) ? (int)$data['ismenu'] : ($children ? 1 : 0);
            $data['icon'] = isset($data['icon']) ? $data['icon'] : ($children ? 'fa fa-list' : 'fa fa-circle-o');
            $data['status'] = isset($data['status']) ? $data['status'] : 'normal';

            $existing = Db::name('auth_rule')->where('name', $data['name'])->find();
            if ($existing) {
                Db::name('auth_rule')->where('id', $existing['id'])->update($data);
                $ruleId = (int)$existing['id'];
            } else {
                $ruleId = (int)Db::name('auth_rule')->insertGetId($data);
            }

            if ($children) {
                $this->syncMenuTree($children, $ruleId);
            }
        }
    }

    /**
     * 应用初始化
     */
    public function appInit()
    {
        //添加命名空间
        if (!class_exists('\Hashids\Hashids')) {
            Loader::addNamespace('Hashids', ADDON_PATH . 'shop' . DS . 'library' . DS . 'hashids' . DS);
        }
        // 自定义路由变量规则
        // \think\Route::pattern([
        //     'diyname' => "/[a-zA-Z0-9\-_\x{4e00}-\x{9fa5}]+/u",
        //     'id'      => "\d+",
        // ]);
        $config = get_addon_config('shop');
        $taglib = Config::get('template.taglib_pre_load');
        Config::set('template.taglib_pre_load', ($taglib ? $taglib . ',' : '') . 'addons\\shop\\taglib\\Shop');
        Config::set('shop', $config);
        $this->registerV5Routes();
    }

    /**
     * Stable V1 routes used by Agent, mini-program and supply-chain partners.
     */
    protected function registerV5Routes()
    {
        $routes = [
            ['api/v1/integration/ai/catalog/products', 'addons/shop/api.v1.integration_ai_catalog/products', 'GET'],
            ['api/v1/integration/ai/catalog/skus/:sku_id/alternatives', 'addons/shop/api.v1.integration_ai_catalog/alternatives', 'GET'],
            ['api/v1/integration/ai/catalog/skus/:sku_id', 'addons/shop/api.v1.integration_ai_catalog/sku', 'GET'],
            ['api/v1/integration/ai/recommendation-packages', 'addons/shop/api.v1.integration_ai_recommendation/create', 'POST'],
            ['api/v1/integration/ai/recommendation-packages/:package_sn/dish-swap-versions', 'addons/shop/api.v1.integration_ai_recommendation/swap', 'POST'],
            ['api/v1/integration/ai/recommendation-packages/:package_sn', 'addons/shop/api.v1.integration_ai_recommendation/detail', 'GET'],
            ['api/v1/integration/ai/service-plans', 'addons/shop/api.v1.integration_ai_plan/create', 'POST'],
            ['api/v1/integration/ai/service-plans/:plan_sn/versions', 'addons/shop/api.v1.integration_ai_plan/version', 'POST'],
            ['api/v1/integration/ai/service-plans/:plan_sn', 'addons/shop/api.v1.integration_ai_plan/detail', 'GET'],
            ['api/v1/integration/ai/plan-orders/:order_sn/resume-validations', 'addons/shop/api.v1.integration_ai_plan/resumeValidation', 'POST'],
            ['api/v1/integration/ai/professional-reviews/:review_ref/result', 'addons/shop/api.v1.integration_review/result', 'POST'],
            ['api/v1/integration/ai/events', 'addons/shop/api.v1.integration_event/index', 'GET'],
            ['api/v1/integration/suppliers/orders/callback', 'addons/shop/api.v1.integration_supplier/callback', 'POST'],
            ['api/v1/integration/suppliers/:supplier_code/order-events', 'addons/shop/api.v1.integration_supplier/callback', 'POST'],
            ['api/v1/integration/logistics/events', 'addons/shop/api.v1.integration_logistics/callback', 'POST'],
            ['api/v1/payment/wechat/notify', 'addons/shop/api.v1.payment_notify/wechat', 'POST'],
            ['api/v1/refund/wechat/notify', 'addons/shop/api.v1.payment_notify/refund', 'POST'],

            ['api/v1/commerce/products', 'addons/shop/api.v1.commerce_product/products', 'GET'],
            ['api/v1/commerce/categories', 'addons/shop/api.v1.commerce_product/categories', 'GET'],
            ['api/v1/commerce/products/:product_id', 'addons/shop/api.v1.commerce_product/detail', 'GET'],
            ['api/v1/commerce/products/:product_id/alternatives', 'addons/shop/api.v1.commerce_product/alternatives', 'GET'],
            ['api/v1/commerce/skus/:sku_id/availability', 'addons/shop/api.v1.commerce_product/availability', 'GET'],
            ['api/v1/commerce/recommendation-packages/:package_sn', 'addons/shop/api.v1.commerce_recommendation/detail', 'GET'],
            ['api/v1/commerce/recommendation-packages/:package_sn/versions', 'addons/shop/api.v1.commerce_recommendation/versions', 'GET'],
            ['api/v1/commerce/recommendation-packages/:package_sn/trade-validate', 'addons/shop/api.v1.commerce_recommendation/tradeValidate', 'POST'],
            ['api/v1/commerce/recommendation-packages/:package_sn/confirm', 'addons/shop/api.v1.commerce_recommendation/confirm', 'POST'],
            ['api/v1/commerce/recommendation-packages/:package_sn/purchase-list', 'addons/shop/api.v1.commerce_recommendation/purchaseList', 'POST'],
            ['api/v1/commerce/purchase-lists', 'addons/shop/api.v1.commerce_purchase_list/index', 'GET'],
            ['api/v1/commerce/purchase-lists/:purchase_list_sn', 'addons/shop/api.v1.commerce_purchase_list/detail', 'GET'],
            ['api/v1/commerce/purchase-lists/:purchase_list_sn/pantry', 'addons/shop/api.v1.commerce_purchase_list/pantry', 'PUT'],
            ['api/v1/commerce/purchase-lists/:purchase_list_sn/rematch', 'addons/shop/api.v1.commerce_purchase_list/rematch', 'POST'],
            ['api/v1/commerce/purchase-lists/:purchase_list_sn/matches/:item_id', 'addons/shop/api.v1.commerce_purchase_list/selectMatch', 'PUT'],
            ['api/v1/commerce/purchase-lists/:purchase_list_sn/confirm', 'addons/shop/api.v1.commerce_purchase_list/confirm', 'POST'],
            ['api/v1/commerce/purchase-lists/:purchase_list_sn/cart', 'addons/shop/api.v1.commerce_purchase_list/cart', 'POST'],
            ['api/v1/commerce/purchase-lists/:purchase_list_sn/checkout', 'addons/shop/api.v1.commerce_purchase_list/checkout', 'POST'],
            ['api/v1/commerce/service-plans', 'addons/shop/api.v1.commerce_plan/index', 'GET'],
            ['api/v1/commerce/service-plans/:plan_sn/calendar', 'addons/shop/api.v1.commerce_plan/calendar', 'GET'],
            ['api/v1/commerce/service-plans/:plan_sn/purchase-policy', 'addons/shop/api.v1.commerce_plan/policy', 'GET'],
            ['api/v1/commerce/service-plans/:plan_sn/checkout', 'addons/shop/api.v1.commerce_plan/checkout', 'POST'],
            ['api/v1/commerce/service-plans/:plan_sn/trade-validate', 'addons/shop/api.v1.commerce_plan/tradeValidate', 'POST'],
            ['api/v1/commerce/service-plans/:plan_sn/schedule-preview', 'addons/shop/api.v1.commerce_plan/schedulePreview', 'POST'],
            ['api/v1/commerce/service-plans/:plan_sn', 'addons/shop/api.v1.commerce_plan/detail', 'GET'],
            ['api/v1/commerce/checkout/preview', 'addons/shop/api.v1.commerce_checkout/preview', 'POST'],
            ['api/v1/commerce/checkout/refresh', 'addons/shop/api.v1.commerce_checkout/refresh', 'POST'],
            ['api/v1/commerce/delivery/slots', 'addons/shop/api.v1.commerce_delivery/slots', 'GET'],
            ['api/v1/commerce/delivery/validate', 'addons/shop/api.v1.commerce_delivery/validateDelivery', 'POST'],
            ['api/v1/commerce/cart', 'addons/shop/api.v1.commerce_cart/index', 'GET'],
            ['api/v1/commerce/cart/items', 'addons/shop/api.v1.commerce_cart/add', 'POST'],
            ['api/v1/commerce/cart/items/:id', 'addons/shop/api.v1.commerce_cart/update', 'PUT'],
            ['api/v1/commerce/cart/items/:id', 'addons/shop/api.v1.commerce_cart/remove', 'DELETE'],
            ['api/v1/commerce/cart/validate', 'addons/shop/api.v1.commerce_cart/validateCart', 'POST'],
            ['api/v1/commerce/orders', 'addons/shop/api.v1.commerce_order/create', 'POST'],
            ['api/v1/commerce/orders', 'addons/shop/api.v1.commerce_order/index', 'GET'],
            ['api/v1/commerce/orders/:order_sn/payments/wechat', 'addons/shop/api.v1.commerce_order/payment', 'POST'],
            ['api/v1/commerce/orders/:order_sn/payment-status', 'addons/shop/api.v1.commerce_order/paymentStatus', 'GET'],
            ['api/v1/commerce/orders/:order_sn/cancel', 'addons/shop/api.v1.commerce_order/cancel', 'POST'],
            ['api/v1/commerce/orders/:order_sn/receipt', 'addons/shop/api.v1.commerce_order/receipt', 'POST'],
            ['api/v1/commerce/orders/:order_sn/repurchase', 'addons/shop/api.v1.commerce_order/repurchase', 'POST'],
            ['api/v1/commerce/orders/:order_sn/timeline', 'addons/shop/api.v1.commerce_order/timeline', 'GET'],
            ['api/v1/commerce/plan-orders/:order_sn', 'addons/shop/api.v1.commerce_order/planDetail', 'GET'],
            ['api/v1/commerce/plan-orders/:order_sn/batches', 'addons/shop/api.v1.commerce_order/batches', 'GET'],
            ['api/v1/commerce/plan-orders/:order_sn/pause', 'addons/shop/api.v1.commerce_order/pause', 'POST'],
            ['api/v1/commerce/plan-orders/:order_sn/resume', 'addons/shop/api.v1.commerce_order/resume', 'POST'],
            ['api/v1/commerce/plan-orders/:order_sn/batches/:batch_no/address', 'addons/shop/api.v1.commerce_order/batchAddress', 'PUT'],
            ['api/v1/commerce/plan-orders/:order_sn/batches/:batch_no/receipt', 'addons/shop/api.v1.commerce_order/batchReceipt', 'POST'],
            ['api/v1/commerce/orders/:order_sn/fulfillment', 'addons/shop/api.v1.commerce_fulfillment/timeline', 'GET'],
            ['api/v1/commerce/orders/:order_sn/logistics', 'addons/shop/api.v1.commerce_fulfillment/timeline', 'GET'],
            ['api/v1/commerce/orders/:order_sn/delivery-issue', 'addons/shop/api.v1.commerce_fulfillment/deliveryIssue', 'POST'],
            ['api/v1/commerce/plan-orders/:order_sn/batches/:batch_no/fulfillment', 'addons/shop/api.v1.commerce_fulfillment/batchTimeline', 'GET'],
            ['api/v1/commerce/plan-orders/:order_sn/batches/:batch_no/logistics', 'addons/shop/api.v1.commerce_fulfillment/batchTimeline', 'GET'],
            ['api/v1/commerce/orders/:order_sn/aftersales/eligibility', 'addons/shop/api.v1.commerce_aftersale/eligibility', 'GET'],
            ['api/v1/commerce/aftersales', 'addons/shop/api.v1.commerce_aftersale/create', 'POST'],
            ['api/v1/commerce/aftersales', 'addons/shop/api.v1.commerce_aftersale/index', 'GET'],
            ['api/v1/commerce/aftersales/:id', 'addons/shop/api.v1.commerce_aftersale/detail', 'GET'],
            ['api/v1/commerce/aftersales/:id/cancel', 'addons/shop/api.v1.commerce_aftersale/cancel', 'POST'],
            ['api/v1/commerce/aftersales/:id/confirm', 'addons/shop/api.v1.commerce_aftersale/confirm', 'POST'],
            ['api/v1/commerce/aftersales/:id/timeline', 'addons/shop/api.v1.commerce_aftersale/timeline', 'GET'],
            ['api/v1/commerce/orders/:order_sn', 'addons/shop/api.v1.commerce_order/detail', 'GET'],
            ['api/v1/commerce/supplier-applications', 'addons/shop/api.v1.commerce_supplier_application/create', 'POST'],
            ['api/v1/commerce/supplier-applications/:application_sn', 'addons/shop/api.v1.commerce_supplier_application/detail', 'GET'],
        ];
        foreach ($routes as $route) {
            $handler = preg_replace('#^addons/shop/#', '', $route[1]);
            $separator = strrpos($handler, '/');
            $controller = substr($handler, 0, $separator);
            $action = substr($handler, $separator + 1);
            $target = '\\think\\addons\\Route@execute?addon=shop&controller=' . $controller . '&action=' . $action;
            \think\Route::rule($route[0], $target, $route[2]);
        }
    }

    /**
     * 脚本替换
     */
    public function viewFilter(&$content)
    {
        $request = \think\Request::instance();
        $dispatch = $request->dispatch();
        if (!$dispatch) {
            return;
        }

        if ($request->module() || !isset($dispatch['method'][0]) || $dispatch['method'][0] != '\think\addons\Route') {
            return;
        }
        $addon = $dispatch['var']['addon'] ?? $request->param('addon');
        if ($addon != 'shop') {
            return;
        }
        $style = '';
        $script = '';
        $result = preg_replace_callback("/<(script|style)\s(data\-render=\"(script|style)\")([\s\S]*?)>([\s\S]*?)<\/(script|style)>/i", function ($match) use (&$style, &$script) {
            if (isset($match[1]) && in_array($match[1], ['style', 'script'])) {
                ${$match[1]} .= str_replace($match[2], '', $match[0]);
            }
            return '';
        }, $content);
        $content = preg_replace_callback('/^\s+(\{__STYLE__\}|\{__SCRIPT__\})\s+$/m', function ($matches) use ($style, $script) {
            return $matches[1] == '{__STYLE__}' ? $style : $script;
        }, $result ?: $content);
    }

    /**
     * 会员中心边栏后
     * @return mixed
     * @throws \Exception
     */
    public function userSidenavAfter()
    {
        $request = Request::instance();
        $controllername = strtolower($request->controller());
        $actionname = strtolower($request->action());
        $config = get_addon_config('shop');
        $usersidebar = explode(',', $config['usersidenav']);
        if (!$usersidebar) {
            return '';
        }
        $data = [
            'controllername' => $controllername,
            'actionname'     => $actionname,
            'usersidebar'    => $usersidebar
        ];

        return $this->fetch('view/hook/user_sidenav_after', $data);
    }

    /**
     * Xunsearch获取配置
     */
    public function xunsearchConfigInit()
    {
        return Search::getDriver('xunsearch')->getIndexConfig();
    }

    /**
     * Xunsearch重置索引
     */
    public function xunsearchIndexReset($project)
    {
        $driver = Search::getDriver('xunsearch');
        if (!$project['isaddon'] || $project['name'] != $driver->getProjectName()) {
            return;
        }
        return $driver->reset();
    }

    /**
     * Meilisearch获取配置信息
     */
    public function meilisearchConfigInit()
    {
        return Search::getDriver('meilisearch')->getIndexConfig();
    }

    /**
     * Meilisearch重置索引
     */
    public function meilisearchIndexReset($project)
    {
        $driver = Search::getDriver('meilisearch');
        if ($project['name'] != $driver->getProjectName()) {
            return;
        }
        return $driver->reset();
    }


}
