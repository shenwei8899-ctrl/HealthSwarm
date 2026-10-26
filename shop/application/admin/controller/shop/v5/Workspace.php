<?php

namespace app\admin\controller\shop\v5;

use addons\shop\library\v5\CatalogService;
use addons\shop\library\v5\DomainException;
use addons\shop\library\v5\ExceptionService;
use addons\shop\library\v5\Identifiers;
use addons\shop\library\v5\InventoryService;
use addons\shop\library\v5\MasterDataImportService;
use addons\shop\library\v5\SupplierCatalogImportService;
use addons\shop\library\v5\RecommendationPackageService;
use addons\shop\library\v5\RefundService;
use addons\shop\library\v5\OutboxDispatcher;
use addons\shop\library\v5\SecretCipher;
use addons\shop\library\v5\SupplierOrderService;
use app\common\controller\Backend;
use think\Db;
use think\Response;

class Workspace extends Backend
{
    protected $noNeedRight = ['supplierApiConfig','saveSupplierApiConfig'];
    protected $workspace = '';

    public function supplierApiConfig()
    {
        if (!$this->request->isGet()) $this->error('请求方式错误');
        if (!$this->auth->check('shop/v5/workspace/suppliers') || !$this->auth->check('shop/v5/workspace/settings')) $this->error('需要供应商档案和系统配置权限');
        header('Cache-Control: no-store');
        try { $data=(new \addons\shop\library\v5\SupplierApiConfigService())->detail((int)$this->request->get('id',0)); }
        catch (DomainException $e) { $this->error($e->getMessage()); }
        $data['__token__']=$this->request->token();
        $this->success('读取成功',null,$data);
    }

    public function saveSupplierApiConfig()
    {
        // AdminLog otherwise records request parameters. Never record credentials.
        \app\admin\model\AdminLog::setTitle('供应商API与回调配置');
        \app\admin\model\AdminLog::setContent(['supplier_id'=>(int)$this->request->post('id',0),'action'=>'保存配置，不启用对接']);
        if (!$this->request->isPost()) $this->error('请求方式错误');
        if (!$this->auth->check('shop/v5/workspace/suppliers') || !$this->auth->check('shop/v5/workspace/settings')) $this->error('需要供应商档案和系统配置权限');
        $this->token();
        header('Cache-Control: no-store');
        try { $data=(new \addons\shop\library\v5\SupplierApiConfigService())->save((int)$this->request->post('id',0),$this->request->post('row/a',[])); }
        catch (DomainException $e) { $this->error($e->getMessage(),null,['__token__'=>$this->request->token()]); }
        catch (\Throwable $e) { $this->error('配置保存失败，未启用对接；请检查内容或刷新后重试',null,['__token__'=>$this->request->token()]); }
        $data['__token__']=$this->request->token();
        $this->success('配置已保存；对接方式和回调启用状态保持不变，未触发推单',null,$data);
    }

    public function commerceDetail()
    {
        $resource=$this->request->get('resource','');
        $pages=['members'=>'members','catalog_readiness'=>'product','recommendations'=>'recommendations','purchase_lists'=>'purchases','orders_normal'=>'orders','orders_all'=>'orders','orders_pending'=>'orders','orders_unpaid'=>'orders','orders_shipping'=>'orders','orders_completed'=>'orders','orders_closed'=>'orders'];
        if (!isset($pages[$resource]) || !$this->auth->check('shop/v5/workspace/'.$pages[$resource])) $this->error('无权查看此业务资料');
        $id=(int)$this->request->get('id',0);
        $service=new \addons\shop\library\v5\CommerceAdminService();
        try {
            if ($resource==='members') $data=$service->user($id);
            elseif (strpos($resource,'orders_')===0) { $data=$service->order($id); unset($data['sources']); $logistics=Db::name('shop_order')->where('id',$id)->field('expressname,expressno,shippingtime,receivetime')->find(); $data['order']=array_merge($data['order'],$logistics?:[]); $data['items']=Db::name('shop_order_goods')->where('order_sn',$data['order']['order_sn'])->field('title,goods_sku_id,nums,price,realprice,salestate')->select(); }
            elseif ($resource==='catalog_readiness') $data=['product'=>(new CatalogService())->getSku($id), 'notice'=>'资料编辑请使用商品食材关联、营养资料和配料与过敏原页签。'];
            else $data=$service->purchase($resource,$id);
        } catch (DomainException $e) { $this->error($e->getMessage()); }
        if ($resource==='members') { unset($data['purchases']); $data['user']['account_source']=str_replace('小程序 / Agent','小程序账号',$data['user']['account_source']); $data['credential_note']='密码不回显，地址、购物车和订单仅用于商城交易管理。'; }
        header('Cache-Control: no-store');
        $this->success('读取成功',null,$data);
    }

    public function dashboard()
    {
        $this->workspace = 'dashboard';
        return $this->render();
    }

    public function product()
    {
        $this->workspace = 'product';
        return $this->render();
    }

    public function ingredients()
    {
        $this->redirect('shop/v5/workspace/product');
    }

    public function recommendations()
    {
        $this->redirect('shop/v5/workspace/product');
    }

    public function plans()
    {
        $this->redirect('shop/v5/workspace/orders');
    }

    public function purchases()
    {
        $this->redirect('shop/v5/workspace/orders');
    }

    public function orders()
    {
        $this->workspace = 'orders';
        return $this->render();
    }

    public function batches()
    {
        $this->redirect('shop/v5/workspace/fulfillment');
    }

    public function fulfillment()
    {
        $this->workspace = 'fulfillment';
        return $this->render();
    }

    public function aftersales()
    {
        $this->workspace = 'aftersales';
        return $this->render();
    }

    public function suppliers()
    {
        $this->workspace = 'suppliers';
        return $this->render();
    }

    public function supplier_sku()
    {
        $this->workspace = 'supplier_sku';
        return $this->render();
    }

    public function supplier_collaboration()
    {
        $this->workspace = 'supplier_collaboration';
        return $this->render();
    }

    public function delivery_rules()
    {
        $this->workspace = 'delivery_rules';
        return $this->render();
    }

    public function finance() { $this->workspace='finance'; return $this->render(); }

    public function technical() { $this->workspace='technical'; return $this->render(); }

    public function analytics()
    {
        $this->workspace = 'analytics';
        return $this->render();
    }

    public function marketing()
    {
        $this->workspace = 'marketing';
        return $this->render();
    }

    public function members()
    {
        $this->workspace = 'members';
        return $this->render();
    }

    public function settings()
    {
        $this->workspace = 'settings';
        return $this->render();
    }

    public function audit()
    {
        $this->workspace = 'audit';
        return $this->render();
    }

    public function data()
    {
        $resource = $this->request->get('resource', '');
        $definition = $this->resource($resource);
        header('Cache-Control: no-store');
        $resourcePages=['members'=>'members','external_identities'=>'members','ingredient_maps'=>'product','nutrition'=>'product','components'=>'product','catalog_reviews'=>'product'];
        if (isset($resourcePages[$resource]) && !$this->auth->check('shop/v5/workspace/'.$resourcePages[$resource])) $this->error('无权查看此业务资料');
        if ($resource === 'catalog_readiness') {
            if (!$this->auth->check('shop/v5/workspace/product')) $this->error('无权查看商品资料');
            return json((new \addons\shop\library\v5\CommerceAdminService())->readiness(trim((string)$this->request->get('q','')),max(0,(int)$this->request->get('offset',0)),min(100,max(1,(int)$this->request->get('limit',20)))));
        }
        $limit = min(100, max(1, (int)$this->request->get('limit', 20)));
        $offset = max(0, (int)$this->request->get('offset', 0));
        $sort = $this->request->get('sort', $definition['pk']);
        $order = strtolower($this->request->get('order', 'desc')) === 'asc' ? 'asc' : 'desc';
        $allowedColumns = array_keys($definition['columns']);
        // These are calculated from the SKU table and are not physical columns
        // on shop_goods, so never include them in the SQL select list.
        $virtualColumns = ['price_range','available_sku_count','total_stocks','account_source','linked_account','binding_status','wechat_status'];
        $queryColumns = array_values(array_diff($allowedColumns, array_merge(['secret_configured'], $virtualColumns)));
        // Edit dialogs need persisted fields even when the list hides those columns.
        $editColumns = array_keys(array_filter($definition['fields'], function ($field) { return $field['type'] !== 'password'; }));
        $queryColumns = array_values(array_unique(array_merge($queryColumns, $editColumns)));
        if (!in_array($sort, $queryColumns, true)) {
            $sort = $definition['pk'];
        }
        $filter = json_decode((string)$this->request->get('filter', '{}'), true) ?: [];
        $q = trim((string)$this->request->get('q', ''));
        // ThinkPHP 5 shares bound parameters when a query object is cloned. Build
        // the count and row queries independently so fixed filters do not bind twice.
        $total = $this->buildResourceQuery($definition, $filter, $q, $queryColumns)->count();
        if (in_array($resource, ['integration_clients', 'suppliers'], true)) {
            $queryColumns[] = 'secret_ciphertext';
        }
        if ($resource === 'suppliers') {
            $queryColumns[] = 'contact_mobile_encrypted';
        }
        $query = $this->buildResourceQuery($definition, $filter, $q, $queryColumns);
        $rows = $query->field(implode(',', array_unique($queryColumns)))->order($sort, $order)->limit($offset, $limit)->select();
        foreach ($rows as &$row) {
            if ($resource === 'integration_clients') {
                $row['secret_configured'] = empty($row['secret_ciphertext']) ? '否' : '是';
                unset($row['secret_ciphertext']);
            }
            if ($resource === 'suppliers') {
                $row['secret_configured'] = empty($row['secret_ciphertext']) ? '否' : '是';
                unset($row['secret_ciphertext'], $row['contact_mobile_encrypted']);
            }
        }
        if ($resource === 'goods') {
            $this->decorateGoodsSummary($rows);
        }
        if ($resource === 'members') { (new \addons\shop\library\v5\CommerceAdminService())->decorateUsers($rows); foreach ($rows as &$memberRow) $memberRow['account_source']=str_replace('小程序 / Agent','小程序账号',$memberRow['account_source']); unset($memberRow); }
        $this->decorateDisplayRows($resource, $rows);
        $this->decorateScalarDisplayRows($resource, $rows, $definition);
        return json(['total' => $total, 'rows' => $rows]);
    }

    /** Add the SKU summary users need while keeping SKU codes internal. */
    protected function decorateGoodsSummary(&$rows)
    {
        foreach ($rows as &$row) {
            $goodsId = (int)$row['id'];
            // Do not clone ThinkPHP query builders here: with PostgreSQL PDO,
            // cloned builders can retain a placeholder without its bind value.
            $row['available_sku_count'] = (int)Db::name('shop_goods_sku')->where('goods_id', $goodsId)->count();
            $row['total_stocks'] = (int)Db::name('shop_goods_sku')->where('goods_id', $goodsId)->sum('stocks');
            $min = Db::name('shop_goods_sku')->where('goods_id', $goodsId)->min('price');
            $max = Db::name('shop_goods_sku')->where('goods_id', $goodsId)->max('price');
            if ($min === null) {
                $row['price_range'] = '-';
            } elseif ((float)$min === (float)$max) {
                $row['price_range'] = number_format((float)$min, 2);
            } else {
                $row['price_range'] = number_format((float)$min, 2) . ' - ' . number_format((float)$max, 2);
            }
        }
        unset($row);
    }

    /** Return a business-facing product detail with all of its SKU variants. */
    public function goodsDetail()
    {
        $goodsId = (int)$this->request->get('id', 0);
        if (!$goodsId) $this->error('商品参数错误');
        $goods = Db::name('shop_goods')->where('id', $goodsId)->find();
        if (!$goods) $this->error('商品不存在');
        $category = $goods['category_id'] ? $this->displayLabels('category', [(int)$goods['category_id']]) : [];
        $skus = Db::name('shop_goods_sku')->where('goods_id', $goodsId)->order('id', 'asc')->select();
        $unitLabels = ['g'=>'克', 'kg'=>'千克', 'ml'=>'毫升', 'piece'=>'件', 'pack'=>'包'];
        $skuRows = [];
        foreach ($skus as $sku) {
            $spec = trim((string)$sku['sku_id']);
            $unit = $unitLabels[$sku['net_content_unit']] ?? (string)$sku['net_content_unit'];
            $skuRows[] = [
                'id' => (int)$sku['id'],
                // Kept for internal writes and integrations; the UI never renders it.
                'sku_code' => $sku['sku_code'],
                'sku_name' => trim($goods['title'] . ($spec ? ' ' . $spec : '')),
                'specification' => $spec ?: '-',
                'price' => $sku['price'],
                'marketprice' => $sku['marketprice'],
                'stocks' => (int)$sku['stocks'],
                'reserved_stock' => (int)$sku['reserved_stock'],
                'safety_stock' => (int)$sku['safety_stock'],
                'net_content' => ($sku['net_content_value'] === null || $sku['net_content_value'] === '') ? '-' : rtrim(rtrim(number_format((float)$sku['net_content_value'], 6, '.', ''), '0'), '.') . $unit,
                'net_content_value' => $sku['net_content_value'],
                'net_content_unit' => $sku['net_content_unit'],
                'image' => $sku['image'],
            ];
        }
        // Supplier data is kept separate from the platform SKU, but is shown
        // here so every field supplied in the supplier workbook has a visible
        // operational home in product management.
        $supplierItems = [];
        if ($skuRows) {
            $skuNames = [];
            foreach ($skuRows as $skuRow) $skuNames[(int)$skuRow['id']] = $skuRow['sku_name'];
            $supplierRows = Db::name('shop_supplier_sku')->alias('ss')
                ->join('shop_supplier s', 's.id=ss.supplier_id', 'LEFT')
                ->where('ss.sku_id', 'in', array_keys($skuNames))
                ->order('ss.priority', 'desc')->order('ss.id', 'asc')
                ->field('ss.sku_id,ss.supplier_goods_code,ss.supplier_sku_code,ss.purchase_price_cent,ss.minimum_order_quantity,ss.delivery_days,ss.stock_quantity,ss.source_note,ss.status,s.name as supplier_name')
                ->select();
            foreach ($supplierRows as $supplierRow) {
                $supplierItems[] = [
                    'sku_name' => $skuNames[(int)$supplierRow['sku_id']] ?? 'SKU',
                    'supplier_name' => $supplierRow['supplier_name'] ?: '-',
                    'supplier_goods_code' => $supplierRow['supplier_goods_code'] ?: '-',
                    'supplier_sku_code' => $supplierRow['supplier_sku_code'] ?: '-',
                    'supply_price' => number_format(((int)$supplierRow['purchase_price_cent']) / 100, 2, '.', ''),
                    'stock_quantity' => (int)$supplierRow['stock_quantity'],
                    'minimum_order_quantity' => (int)$supplierRow['minimum_order_quantity'],
                    'delivery_days' => (int)$supplierRow['delivery_days'],
                    'source_note' => $supplierRow['source_note'] ?: '-',
                    'status' => $supplierRow['status'] === 'normal' ? '可供货' : '已停用',
                ];
            }
        }
        $min = Db::name('shop_goods_sku')->where('goods_id', $goodsId)->min('price');
        $max = Db::name('shop_goods_sku')->where('goods_id', $goodsId)->max('price');
        // Backend::success follows ThinkPHP's jump signature: data is the
        // third argument, while the second argument is the redirect URL.
        $this->success('商品详情', null, [
            'edit_values' => array_intersect_key($goods, array_flip(['id','image','title','sale_type','category_id','agent_visible','status'])),
            'goods' => [
                'id' => $goodsId, 'goods_sn' => $goods['goods_sn'], 'title' => $goods['title'],
                'image' => $goods['image'], 'sale_type' => $goods['sale_type'],
                'category' => $category[(int)$goods['category_id']] ?? '-',
                'agent_visible' => ((int)$goods['agent_visible'] === 1 ? '是' : '否'),
                'status' => $goods['status'] === 'normal' ? '上架' : '下架',
                'price_range' => $min === null ? '-' : (((float)$min === (float)$max) ? number_format((float)$min, 2) : number_format((float)$min, 2) . ' - ' . number_format((float)$max, 2)),
                'available_sku_count' => count($skuRows), 'total_stocks' => array_sum(array_column($skuRows, 'stocks')),
            ],
            'skus' => $skuRows,
            'supplier_items' => $supplierItems,
        ]);
    }

    /** Options used by the product-detail SKU creator. */
    public function skuOptions()
    {
        $specs = Db::name('shop_spec')->order('id', 'asc')->field('id,name')->select();
        $values = Db::name('shop_spec_value')->order('spec_id', 'asc')->order('id', 'asc')->field('id,spec_id,value')->select();
        $this->success('规格选项', null, ['specs' => $specs, 'values' => $values]);
    }

    /**
     * Convert storage enums and Unix timestamps to the labels used by the
     * edit forms. __raw remains untouched so editing still submits raw values.
     */
    protected function decorateScalarDisplayRows($resource, &$rows, array $definition)
    {
        $common = [
            'normal' => '上架', 'hidden' => '下架', 'draft' => '草稿', 'active' => '生效',
            'retired' => '停用', 'published' => '已发布', 'suspended' => '已暂停',
            'imported' => '已导入', 'invalid' => '预检失败', 'validated' => '预检通过',
            'pending' => '待处理', 'processing' => '处理中', 'failed' => '失败',
            'resolved' => '已解决', 'open' => '待处理', 'completed' => '已完成',
            'cancelled' => '已取消', 'expired' => '已失效', 'scheduled' => '已排程',
            'preparing' => '备货中', 'supplier_pending' => '待供应商处理', 'shipped' => '已发货',
            'delivered' => '已送达', 'paused' => '已暂停', 'approved' => '已通过',
            'rejected' => '已拒绝', 'unconfirmed' => '未确认', 'confirmed' => '已确认',
            'yes' => '是', 'no' => '否',
        ];
        $byField = [
            'sale_type' => ['normal'=>'普通商品','bundle'=>'组合商品','service'=>'服务商品'],
            'agent_visible' => [0=>'否',1=>'是'], 'catalog_status' => ['draft'=>'草稿','published'=>'已发布','suspended'=>'已暂停'],
            'data_completeness' => ['complete'=>'完整','partial'=>'部分完整','insufficient'=>'资料不足'],
            'order_type' => ['normal'=>'普通订单','plan'=>'历史周期订单'], 'paystate' => [0=>'待付款',1=>'已付款'],
            'shippingstate' => [0=>'未发货',1=>'已发货',2=>'已收货'],
            'orderstate' => [0=>'正常',1=>'已取消',2=>'已失效',3=>'已完成',4=>'退货退款中'],
            'interface_type' => ['manual'=>'人工','api'=>'API'], 'stock_status' => ['sufficient'=>'充足','low'=>'偏低','out'=>'缺货','unknown'=>'未知'],
            'basis_type' => ['per_100g'=>'每100克','per_serving'=>'每份'],
            'role' => ['primary'=>'主食材','component'=>'组成','alternative'=>'备选'],
            'review_status' => ['pending'=>'待审核','approved'=>'已通过','rejected'=>'已拒绝','supplement_required'=>'需补充资料'],
            'nutrition_status' => ['pending'=>'待校验','passed'=>'已通过','failed'=>'未通过','blocked'=>'已阻断'],
            'trade_status' => ['pending'=>'待校验','passed'=>'已通过','failed'=>'未通过','blocked'=>'已阻断'],
            'confirm_status' => ['unconfirmed'=>'未确认','confirmed'=>'已确认'],
            'match_status' => ['pending'=>'待匹配','matched'=>'已匹配','partial'=>'部分匹配','unmatched'=>'未匹配'],
            'push_status' => ['pending'=>'待推送','processing'=>'推送中','success'=>'已推送','failed'=>'推送失败','manual'=>'待人工对接'],
            'fulfillment_status' => ['pending'=>'待履约','preparing'=>'备货中','shipped'=>'已发货','delivered'=>'已送达','failed'=>'履约失败'],
            'inventory_status' => ['pending'=>'待锁库存','locked'=>'已锁库存','insufficient'=>'库存不足','released'=>'已释放'],
            'supplier_status' => ['pending'=>'待供应商处理','accepted'=>'供应商已接单','rejected'=>'供应商已拒单','completed'=>'供应商已完成'],
            'purchase_gate' => ['allowed'=>'允许购买','blocked'=>'禁止购买','pending'=>'待审核'],
            'source_type' => ['normal'=>'普通订单','plan'=>'历史周期订单','plan_exception'=>'计划例外','service_plan'=>'专属计划'],
            'change_type' => ['in'=>'入库','out'=>'出库','reserve'=>'占用库存','release'=>'释放占用','adjust'=>'盘点调整'],
            'type' => [1=>'按件计费',2=>'按重量计费',3=>'按金额计费'],
            'temperature_zone' => ['ambient'=>'常温','chilled'=>'冷藏','frozen'=>'冷冻'],
            'result' => ['fixed_amount'=>'固定金额','discount'=>'折扣','percentage'=>'百分比'],
            'source_scope' => ['all'=>'全部订单','normal'=>'普通订单','plan'=>'历史周期订单'],
            'plan_allowed' => [0=>'否',1=>'是'],
            'refund_allocation_rule' => ['none'=>'不参与退款','proportional'=>'按比例分摊','first_batch'=>'首批优先'],
            'client_type' => ['agent'=>'Agent','supplier'=>'供应商','logistics'=>'物流','review'=>'专业审核'],
            'partner_type' => ['agent'=>'Agent','supplier'=>'供应商','channel'=>'渠道商','distributor'=>'经销商','logistics'=>'物流','review'=>'专业审核'],
            'resource_type' => ['recommendation'=>'食材包推荐','plan'=>'历史周期订单','swap'=>'换菜请求','order'=>'订单'],
            'policy_type' => ['plan_non_refund'=>'专属计划不退款'],
            'direction' => ['inbound'=>'入站','outbound'=>'出站'], 'success' => [0=>'失败',1=>'成功'],
            'is_open' => [0=>'关闭',1=>'开启'], 'switch' => [0=>'关闭',1=>'开启'],
            'delivery_slot_required' => [0=>'否',1=>'是'], 'user_cancellable' => [0=>'否',1=>'是'],
            'requires_agent_revalidation' => [0=>'否',1=>'是'], 'is_selected' => [0=>'否',1=>'是'],
            'status' => $common,
        ];
        $timestamps = ['createtime'=>true,'updatetime'=>true,'expires_at'=>true,'imported_at'=>true,'effective_at'=>true,
            'calculated_at'=>true,'reviewed_at'=>true,'submitted_at'=>true,'paid_at'=>true,'last_query_at'=>true,
            'inventory_lock_at'=>true,'shipped_at'=>true,'delivered_at'=>true,'processed_at'=>true,'requested_at'=>true,
            'success_at'=>true,'started_at'=>true,'finished_at'=>true,'occurred_at'=>true,'stock_updated_at'=>true,
            'confirmed_at'=>true,'validated_at'=>true,'trade_checked_at'=>true,'sent_at'=>true,'next_retry_at'=>true,
            'jointime'=>true,'executed_at'=>true];
        foreach ($rows as &$row) {
            if (!isset($row['__raw'])) $row['__raw'] = $row;
            foreach ($definition['columns'] as $field => $unused) {
                if (!array_key_exists($field, $row) || $row[$field] === null || $row[$field] === '') continue;
                $value = $row[$field];
                $options = isset($definition['fields'][$field]['options']) ? $definition['fields'][$field]['options'] : [];
                if ($options && array_key_exists($value, $options)) {
                    $row[$field] = $options[$value];
                } elseif (isset($byField[$field]) && array_key_exists($value, $byField[$field])) {
                    $row[$field] = $byField[$field][$value];
                } elseif (isset($common[$value])) {
                    $row[$field] = $common[$value];
                } elseif (isset($timestamps[$field]) && preg_match('/^\d{10}$/', (string)$value) && (int)$value > 0) {
                    $row[$field] = date('Y-m-d H:i:s', (int)$value);
                }
            }
        }
        unset($row);
    }

    /**
     * Keep foreign keys for writes, but present business names in list views.
     * The original row is returned under __raw so the generic edit dialog can
     * still submit numeric IDs.
     */
    protected function decorateDisplayRows($resource, &$rows)
    {
        if ($resource === 'imports') {
            $adminIds = [];
            foreach ($rows as $row) {
                foreach (['created_by', 'confirmed_by'] as $field) {
                    if (!empty($row[$field])) $adminIds[] = (int)$row[$field];
                }
            }
            $adminLabels = $this->displayLabels('admin', array_values(array_unique($adminIds)));
            foreach ($rows as &$row) {
                foreach (['created_by', 'confirmed_by'] as $field) {
                    $id = isset($row[$field]) ? (int)$row[$field] : 0;
                    $row[$field] = $id && isset($adminLabels[$id]) ? $adminLabels[$id] : '-';
                }
                foreach (['imported_at', 'createtime'] as $field) {
                    $timestamp = isset($row[$field]) ? (int)$row[$field] : 0;
                    $row[$field] = $timestamp > 0 ? date('Y-m-d H:i:s', $timestamp) : '-';
                }
            }
            unset($row);
            return;
        }
        $fieldTypes = [
            'goods' => ['category_id' => 'category'],
            'skus' => ['goods_id' => 'goods'],
            'inventory_logs' => ['sku_id' => 'sku'],
            'ingredient_maps' => ['ingredient_id' => 'ingredient', 'goods_id' => 'goods', 'sku_id' => 'sku'],
            'nutrition' => ['sku_id' => 'sku'],
            'recommendations' => ['agent_client_id' => 'integration_client'],
            'recommendation_versions' => ['package_id' => 'recommendation'],
            'bundle_items' => ['bundle_goods_id' => 'goods', 'bundle_sku_id' => 'sku', 'item_goods_id' => 'goods', 'item_sku_id' => 'sku'],
            'recipe_maps' => ['bundle_sku_id' => 'sku'],
            'swaps' => ['package_id' => 'recommendation'],
            'purchase_items' => ['purchase_list_id' => 'purchase_list', 'ingredient_id' => 'ingredient', 'selected_match_id' => 'purchase_match'],
            'purchase_matches' => ['purchase_item_id' => 'purchase_item', 'sku_id' => 'sku'],
            'plan_versions' => ['plan_id' => 'plan'],
            'plan_days' => ['plan_version_id' => 'plan_version'],
            'purchase_lists' => ['user_id' => 'member'],
            'batches' => ['plan_order_id' => 'plan_order'],
            'batches_prepare' => ['plan_order_id' => 'plan_order'],
            'batches_shipping' => ['plan_order_id' => 'plan_order'],
            'batch_items' => ['batch_id' => 'batch', 'goods_id' => 'goods', 'sku_id' => 'sku'],
            'plan_changes' => ['plan_order_id' => 'plan_order', 'request_user_id' => 'member'],
            'plan_orders' => ['plan_id' => 'plan', 'user_id' => 'member'],
            'supplier_skus' => ['supplier_id' => 'supplier', 'sku_id' => 'sku'],
            'supplier_applications' => ['user_id' => 'member', 'review_admin_id' => 'admin', 'supplier_id' => 'supplier'],
            'supplier_orders' => ['supplier_id' => 'supplier', 'plan_batch_id' => 'batch'],
            'supplier_order_items' => ['supplier_order_id' => 'supplier_order', 'supplier_sku_id' => 'supplier_sku'],
            'delivery_areas' => ['supplier_id' => 'supplier'],
            'delivery_slots' => ['area_id' => 'delivery_area'],
            'freights' => ['supplier_id' => 'supplier'],
            'user_coupons' => ['coupon_id' => 'coupon', 'user_id' => 'member'],
            'external_identities' => ['client_id' => 'integration_client', 'user_id' => 'member'],
            'admin_logs' => ['admin_id' => 'admin'],
            'roles' => ['pid' => 'role'],
            'aftersales' => ['order_id' => 'order', 'order_goods_id' => 'order_goods', 'user_id' => 'member', 'batch_id' => 'batch'],
            'refunds' => ['aftersale_id' => 'aftersale'],
            'exceptions' => ['assignee_admin_id' => 'admin'],
            'exceptions_supply' => ['batch_id' => 'batch'],
            'exceptions_supplier' => ['supplier_order_id' => 'supplier_order'],
            'fulfillment_events' => ['plan_batch_id' => 'batch'],
        ];
        if (empty($rows) || empty($fieldTypes[$resource])) return;
        $labels = [];
        foreach ($fieldTypes[$resource] as $field => $type) {
            $ids = [];
            foreach ($rows as $row) {
                if (isset($row[$field]) && $row[$field] !== '' && $row[$field] !== null && (int)$row[$field] > 0) $ids[] = (int)$row[$field];
            }
            if ($ids) $labels[$field] = $this->displayLabels($type, array_values(array_unique($ids)));
        }
        foreach ($rows as &$row) {
            $row['__raw'] = $row;
            foreach ($fieldTypes[$resource] as $field => $type) {
                $id = isset($row[$field]) ? (int)$row[$field] : 0;
                if (!$id) {
                    $row[$field] = '-';
                } elseif (isset($labels[$field][$id])) {
                    $row[$field] = $labels[$field][$id];
                } else {
                    $row[$field] = '关联记录不存在';
                }
            }
        }
        unset($row);
    }

    protected function displayLabels($type, array $ids)
    {
        $labels = [];
        if (!$ids) return $labels;
        if ($type === 'goods') {
            $rows = Db::name('shop_goods')->where('id', 'in', $ids)->field('id,title,goods_sn')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = $row['title'] . ($row['goods_sn'] ? '（' . $row['goods_sn'] . '）' : '');
        } elseif ($type === 'category') {
            $rows = Db::name('shop_category')->where('id', 'in', $ids)->field('id,name')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = $row['name'];
        } elseif ($type === 'ingredient') {
            $rows = Db::name('shop_ingredient')->where('id', 'in', $ids)->field('id,name,ingredient_code')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = $row['name'] . ($row['ingredient_code'] ? '（' . $row['ingredient_code'] . '）' : '');
        } elseif ($type === 'sku') {
            $rows = Db::name('shop_goods_sku')->alias('s')->join('shop_goods g', 'g.id=s.goods_id', 'LEFT')->where('s.id', 'in', $ids)->field('s.id,s.sku_code,s.sku_id,g.title')->select();
            foreach ($rows as $row) {
                $code = $row['sku_code'] ?: $row['sku_id'];
                $labels[(int)$row['id']] = trim($row['title'] . ($code ? ' / ' . $code : ''));
            }
        } elseif ($type === 'supplier') {
            $rows = Db::name('shop_supplier')->where('id', 'in', $ids)->field('id,name,supplier_code')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = $row['name'] . ($row['supplier_code'] ? '（' . $row['supplier_code'] . '）' : '');
        } elseif ($type === 'plan') {
            $rows = Db::name('shop_service_plan')->where('id', 'in', $ids)->field('id,plan_sn,plan_name')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = $row['plan_sn'] . ($row['plan_name'] ? ' / ' . $row['plan_name'] : '');
        } elseif ($type === 'recommendation') {
            $rows = Db::name('shop_recommendation_package')->where('id', 'in', $ids)->field('id,package_sn')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = $row['package_sn'] ?: ('推荐包 #' . $row['id']);
        } elseif ($type === 'plan_version') {
            $rows = Db::name('shop_service_plan_version')->where('id', 'in', $ids)->field('id,plan_id,version_no')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = '计划 #' . $row['plan_id'] . ' / V' . $row['version_no'];
        } elseif ($type === 'plan_order') {
            $rows = Db::name('shop_service_plan_order')->where('id', 'in', $ids)->field('id,plan_order_sn,order_sn')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = $row['plan_order_sn'] ?: $row['order_sn'];
        } elseif ($type === 'batch') {
            $rows = Db::name('shop_plan_delivery_batch')->where('id', 'in', $ids)->field('id,batch_sn,batch_no')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = $row['batch_sn'] ?: ('第' . $row['batch_no'] . '批');
        } elseif ($type === 'purchase_list') {
            $rows = Db::name('shop_purchase_list')->where('id', 'in', $ids)->field('id,purchase_list_sn')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = $row['purchase_list_sn'];
        } elseif ($type === 'purchase_item') {
            $rows = Db::name('shop_purchase_item')->where('id', 'in', $ids)->field('id,recipe_ref')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = $row['recipe_ref'] ?: ('采购项 #' . $row['id']);
        } elseif ($type === 'purchase_match') {
            $rows = Db::name('shop_purchase_match')->where('id', 'in', $ids)->field('id,sku_id,rank_no')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = '候选SKU ' . $row['sku_id'] . '（第' . $row['rank_no'] . '候选）';
        } elseif ($type === 'supplier_order') {
            $rows = Db::name('shop_supplier_order')->where('id', 'in', $ids)->field('id,supplier_order_sn,platform_order_sn')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = $row['supplier_order_sn'] ?: $row['platform_order_sn'];
        } elseif ($type === 'supplier_sku') {
            $rows = Db::name('shop_supplier_sku')->where('id', 'in', $ids)->field('id,supplier_sku_code,supplier_sku_name')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = $row['supplier_sku_name'] . ($row['supplier_sku_code'] ? '（' . $row['supplier_sku_code'] . '）' : '');
        } elseif ($type === 'admin') {
            $rows = Db::name('admin')->where('id', 'in', $ids)->field('id,username,nickname')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = $row['nickname'] ?: $row['username'];
        } elseif ($type === 'member') {
            $rows = Db::name('user')->where('id', 'in', $ids)->field('id,username,nickname,mobile')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = $row['nickname'] ?: ($row['username'] ?: ($row['mobile'] ?: ('会员 #' . $row['id'])));
        } elseif ($type === 'integration_client') {
            $rows = Db::name('shop_integration_client')->where('id', 'in', $ids)->field('id,client_id,name')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = $row['name'] . '（' . $row['client_id'] . '）';
        } elseif ($type === 'delivery_area') {
            $rows = Db::name('shop_delivery_area')->where('id', 'in', $ids)->field('id,area_code,name')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = $row['name'] . ($row['area_code'] ? '（' . $row['area_code'] . '）' : '');
        } elseif ($type === 'coupon') {
            $rows = Db::name('shop_coupon')->where('id', 'in', $ids)->field('id,name')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = $row['name'];
        } elseif ($type === 'role') {
            $rows = Db::name('auth_group')->where('id', 'in', $ids)->field('id,name')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = $row['name'];
        } elseif ($type === 'order') {
            $rows = Db::name('shop_order')->where('id', 'in', $ids)->field('id,order_sn')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = $row['order_sn'] ?: ('订单 #' . $row['id']);
        } elseif ($type === 'order_goods') {
            $rows = Db::name('shop_order_goods')->where('id', 'in', $ids)->field('id,order_sn,title')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = ($row['title'] ?: '订单商品') . '（订单 ' . $row['order_sn'] . '）';
        } elseif ($type === 'aftersale') {
            $rows = Db::name('shop_order_aftersales')->where('id', 'in', $ids)->field('id,order_id,reason')->select();
            foreach ($rows as $row) $labels[(int)$row['id']] = '售后 #' . $row['id'] . ($row['reason'] ? ' / ' . $row['reason'] : '');
        }
        return $labels;
    }

    protected function buildResourceQuery(array $definition, array $filter, $q, array $queryColumns)
    {
        $query = Db::name($definition['table']);
        if (!empty($definition['where'])) {
            foreach ($definition['where'] as $field => $value) {
                is_array($value) ? $query->where($field, $value[0], $value[1]) : $query->where($field, $value);
            }
        }
        $filterIndex = 0;
        foreach ($filter as $field => $value) {
            if (in_array($field, $queryColumns, true) && is_scalar($value) && $value !== '') {
                $this->whereResourceLike($query, [$field], $value, 'workspace_filter_' . $filterIndex++);
            }
        }
        if ($definition['table']==='user' && $q!=='') {
            $userIds=Db::name('shop_external_identity')->where('external_user_ref','like','%'.$q.'%')->column('user_id');
            $query->where(function($nested) use($q,$userIds){$nested->where('username|nickname|mobile','like','%'.$q.'%')->whereOr('id','in',$userIds?:[0]);});
            return $query;
        }
        if ($q !== '' && !empty($definition['search'])) {
            $this->whereResourceLike($query, $definition['search'], $q, 'workspace_search');
        }
        return $query;
    }

    /** PostgreSQL requires text operands for LIKE, including numeric/date filters. */
    protected function whereResourceLike($query, array $fields, $value, $prefix)
    {
        if (\think\Config::get('database.type') !== 'pgsql') {
            return $query->where(implode('|', $fields), 'like', '%' . $value . '%');
        }
        $conditions = [];
        $bindings = [];
        foreach ($fields as $index => $field) {
            // Identifiers come only from the resource definition/allowed columns.
            if (!preg_match('/^[a-zA-Z_][a-zA-Z0-9_]*$/D', $field)) {
                throw new \InvalidArgumentException('Invalid workspace search field');
            }
            $parameter = $prefix . '_' . $index;
            $conditions[] = 'CAST("' . $field . '" AS TEXT) LIKE :' . $parameter;
            $bindings[$parameter] = '%' . $value . '%';
        }
        return $query->whereRaw('(' . implode(' OR ', $conditions) . ')', $bindings);
    }

    public function save()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $resource = $this->request->post('resource', '');
        $definition = $this->resource($resource);
        if (empty($definition['editable'])) {
            $this->error('该数据仅允许查看');
        }
        $id = (int)$this->request->post('id', 0);
        $row = $this->request->post('row/a', []);
        if ($resource === 'integration_clients') {
            \app\admin\model\AdminLog::setTitle('商城集成调用方配置');
            \app\admin\model\AdminLog::setContent(['id'=>$id,'client_id'=>$row['client_id']??'','action'=>'保存调用方配置，密钥不记录']);
        }
        $allowed = array_keys(isset($definition['fields']) ? $definition['fields'] : []);
        $data = array_intersect_key($row, array_flip($allowed));
        if ($resource === 'plan_rules') {
            $this->token();
            if (!$this->auth->check('shop/v5/workspace/settings')) $this->error('无权发布专属计划规则');
            if ($id) $this->error('已发布规则不可修改，请新增版本');
            $config=json_decode($data['config_json'] ?? '',true);
            if (!is_array($config)) $this->error('请填写完整的规则配置');
            try { $published=(new \addons\shop\library\v5\PlanPolicyService())->publish($data['policy_version'] ?? '',$config,(int)($data['effective_at'] ?? 0)); }
            catch (DomainException $e) { $this->error($e->getMessage(),null,['__token__'=>$this->request->token()]); }
            $this->success('规则已发布',null,$published+['__token__'=>$this->request->token()]);
        }
        foreach ($definition['fields'] as $field => $meta) {
            if (!empty($meta['required']) && (!isset($data[$field]) || trim((string)$data[$field]) === '')) {
                $this->error($meta['title'] . '不能为空');
            }
        }
        foreach ($data as $field => $value) {
            $meta = $definition['fields'][$field];
            if (!is_scalar($value) && $value !== null) $this->error($meta['title'] . '格式无效');
            if ($meta['type'] === 'select' && !array_key_exists((string)$value, $meta['options'])) $this->error($meta['title'] . '选项无效');
            if ($meta['type'] === 'number' && $value !== '' && (!is_numeric($value) || !is_finite((float)$value))) $this->error($meta['title'] . '必须为有效数字');
            if (substr($field, -5) === '_json' && trim((string)$value) !== '') {
                $decoded = json_decode($value, true);
                if (json_last_error() !== JSON_ERROR_NONE || !is_array($decoded)) $this->error($meta['title'] . '必须为有效JSON数组');
            }
        }
        $integerFields = [
            'categories'=>['weigh'], 'suppliers'=>['priority'],
            'supplier_skus'=>['supplier_id','sku_id','purchase_price_cent','minimum_order_quantity','stock_quantity','priority'],
            'delivery_areas'=>['supplier_id'], 'delivery_slots'=>['area_id','cutoff_minutes','capacity','extra_fee_cent'],
            'integration_clients'=>['clock_skew_seconds'], 'roles'=>['pid'],
        ];
        foreach ($integerFields[$resource] ?? [] as $field) {
            if (isset($data[$field]) && $data[$field] !== '' && (!preg_match('/^-?\d+$/D', (string)$data[$field]) || (float)$data[$field] < -2147483648 || (float)$data[$field] > 2147483647)) $this->error($definition['fields'][$field]['title'].'必须为有效整数');
        }
        if ($resource === 'supplier_skus') {
            if (!Db::name('shop_supplier')->where('id',(int)$data['supplier_id'])->find()) $this->error('供应商不存在');
            if (!Db::name('shop_goods_sku')->where('id',(int)$data['sku_id'])->find()) $this->error('平台SKU不存在');
            if ((int)$data['minimum_order_quantity'] < 1) $this->error('最小起订量必须大于零');
            foreach (['purchase_price_cent','stock_quantity'] as $field) if (isset($data[$field]) && (int)$data[$field] < 0) $this->error($definition['fields'][$field]['title'].'不能为负数');
        }
        if ($resource === 'delivery_areas' && !empty($data['supplier_id']) && !Db::name('shop_supplier')->where('id',(int)$data['supplier_id'])->find()) $this->error('供应商不存在；通用配送区域请填0或留空');
        if ($resource === 'delivery_slots') {
            if ($id && isset($data['service_scope']) && $data['service_scope']!==Db::name('shop_delivery_slot')->where('id',$id)->value('service_scope')) $this->error('配送名额用途创建后不可切换，请新增时段');
            if (!Db::name('shop_delivery_area')->where('id',(int)$data['area_id'])->find()) $this->error('配送区域不存在');
            foreach (['start_time','end_time'] as $field) if (!preg_match('/^(?:[01]\d|2[0-3]):[0-5]\d$/D',(string)$data[$field])) $this->error('配送时间请使用HH:mm格式');
            if ($data['end_time'] <= $data['start_time']) $this->error('结束时间必须晚于开始时间');
            foreach (['cutoff_minutes','capacity','extra_fee_cent'] as $field) if (isset($data[$field]) && (int)$data[$field] < 0) $this->error($definition['fields'][$field]['title'].'不能为负数');
            if (!empty($data['weekday_mask']) && !preg_match('/^[1-7](?:,[1-7])*$/D',(string)$data['weekday_mask'])) $this->error('配送星期请填写1至7，用英文逗号分隔');
        }
        if ($resource === 'integration_clients') {
            if ((int)$data['clock_skew_seconds'] < 30 || (int)$data['clock_skew_seconds'] > 900) $this->error('允许时间偏差须为30至900秒');
            $ips=trim((string)($data['allowed_ip_json']??''))===''?[]:json_decode($data['allowed_ip_json'],true);
            if ($ips && array_keys($ips)!==range(0,count($ips)-1)) $this->error('IP白名单必须为JSON列表');
            foreach ($ips as $ip) if (!is_string($ip) || !filter_var($ip,FILTER_VALIDATE_IP)) $this->error('IP白名单中存在无效的IP地址');
        }
        if ($resource === 'roles') {
            $parent=(int)$data['pid'];$seen=[];
            while ($parent) {
                if ($parent < 0 || $parent===$id || isset($seen[$parent])) $this->error('上级角色不能形成循环关联');
                $seen[$parent]=true;$group=Db::name('auth_group')->where('id',$parent)->find();
                if (!$group) $this->error('上级角色不存在');
                $parent=(int)$group['pid'];
            }
        }
        if (in_array($resource,['ingredient_maps','nutrition','components'],true)) {
            $this->token();
            if (!$this->auth->check('shop/v5/workspace/product')) $this->error('无权维护商品资料');
            if (($data['review_status']??'')==='approved' && !$this->auth->check('shop/v5/workspace/reviewcatalog')) $this->error('无权审核商品资料');
            try {$saved=(new \addons\shop\library\v5\CatalogReviewService())->save($resource,$id,$data,$this->request->post('version',''),$this->auth->id);}
            catch (DomainException $e) {$this->error($e->getMessage(),null,['__token__'=>$this->request->token()]);}
            catch (\Throwable $e) {$this->error(strpos($e->getMessage(),'23505')!==false?'该关联资料已存在，请编辑已有记录':'保存失败，请检查填写内容后重试',null,['__token__'=>$this->request->token()]);}
            $this->success('保存成功',null,['id'=>$saved,'__token__'=>$this->request->token()]);
        }
        if (!$id && $resource === 'integration_clients' && empty($data['secret_plaintext'])) {
            $this->error('新建集成调用方必须设置签名密钥');
        }
        if (!$id && $resource === 'suppliers' && isset($data['interface_type']) && $data['interface_type'] === 'api' && empty($data['secret_plaintext'])) {
            $this->error('API供应商必须设置接口密钥');
        }
        if (isset($data['secret_plaintext'])) {
            if (trim($data['secret_plaintext']) !== '') {
                $data['secret_ciphertext'] = SecretCipher::encrypt(trim($data['secret_plaintext']));
            }
            unset($data['secret_plaintext']);
        }
        if (!$id && $resource === 'suppliers') $data['interface_type']='manual';
        if ($resource === 'suppliers' && isset($data['credit_code']) && trim($data['credit_code']) === '') $data['credit_code'] = null;
        $now = time();
        $existing = $id ? Db::name($definition['table'])->where($definition['pk'], $id)->find() : null;
        if ($id && !$existing) {
            $this->error('记录不存在');
        }
        if ($resource === 'suppliers' && $existing && isset($data['supplier_code']) && $data['supplier_code']!==$existing['supplier_code']) $this->error('供应商编码用于回调身份绑定，已有供应商不能修改编码');
        if ($resource === 'integration_clients' && $existing && $data['client_id']!==$existing['client_id']) $this->error('调用方编号用于接口鉴权，已有调用方不能修改编号');
        if ($resource === 'skus') {
            unset($data['sku_code']);
            foreach (['price','marketprice','stocks','safety_stock','net_content_value'] as $field) {
                if (!isset($data[$field]) || $data[$field] === '') continue;
                if ((float)$data[$field] < 0 || ($field === 'net_content_value' && (float)$data[$field] <= 0)) $this->error('价格和库存不能为负，净含量必须大于零');
                if (in_array($field, ['stocks','safety_stock'], true) && floor((float)$data[$field]) != (float)$data[$field]) $this->error('库存必须为整数');
            }
            if ($existing && (int)$data['stocks'] < (int)$existing['reserved_stock']) $this->error('实物库存不能小于已占用库存');
            if (!Db::name('shop_goods')->where('id', (int)$data['goods_id'])->find()) $this->error('商品不存在');
            $goodsId = (int)($data['goods_id'] ?? ($existing['goods_id'] ?? 0));
            $spec = trim((string)($data['sku_id'] ?? ($existing['sku_id'] ?? '')));
            if ($goodsId && $spec !== '') {
                // Compare the small SKU set in PHP. This avoids mixing named
                // and positional PDO parameters in PostgreSQL/ThinkPHP.
                $siblings = Db::name('shop_goods_sku')->where('goods_id', $goodsId)->field('id,sku_id')->select();
                foreach ($siblings as $sibling) {
                    if ($id && (int)$sibling['id'] === $id) continue;
                    if (strtolower(trim((string)$sibling['sku_id'])) === strtolower($spec)) {
                        $this->error('同一商品的该规格已存在，请直接编辑已有SKU，不能重复创建');
                    }
                }
            }
        }
        if (!$id && $resource === 'goods') {
            // Product codes are integration keys. They are generated by the
            // server for manual creation just as they are for spreadsheet import.
            $data['goods_sn'] = 'AUTO-' . strtoupper(substr(hash('sha256', ($data['category_id'] ?? '') . '|' . ($data['title'] ?? '') . '|' . microtime(true)), 0, 14));
            $data['price'] = 0;
            $data['marketprice'] = 0;
            $data['stocks'] = 0;
            $data['status'] = 'hidden';
            $data['catalog_status'] = 'draft';
            $data['data_completeness'] = 'partial';
        }
        if (!$id && $resource === 'skus') {
            // Never accept a browser-provided internal SKU identifier.
            $data['sku_code'] = 'PSKU-' . strtoupper(substr(hash('sha256', ($data['goods_id'] ?? '') . '|' . ($data['sku_id'] ?? '') . '|' . microtime(true)), 0, 14));
            $data['goods_sn'] = $data['sku_code'];
        }
        if ($resource === 'ingredients' && $existing) {
            unset($data['ingredient_code']);
        }
        if ($resource === 'policies' && $existing && $existing['status'] === 'active') {
            $this->error('已生效政策不可覆盖，请新增版本');
        }
        if ($resource === 'policies' && isset($data['content'])) {
            $data['content_hash'] = hash('sha256', $data['content']);
        }
        if (isset($definition['timestamps']) && !$definition['timestamps']) {
            // No timestamps on this resource.
        } else {
            $data['updatetime'] = $now;
            if (!$id) {
                $data['createtime'] = $now;
            }
        }
        $this->token();
        Db::startTrans();
        try {
        if ($id) {
            if (isset($existing['version'])) {
                $data['version'] = (int)$existing['version'] + 1;
            }
            Db::name($definition['table'])->where($definition['pk'], $id)->update($data);
        } else {
            if (array_key_exists('version', $definition['columns']) && !isset($data['version'])) {
                $data['version'] = 1;
            }
            $id = Db::name($definition['table'])->insertGetId($data);
        }
        if (in_array($resource, ['goods', 'skus', 'ingredients', 'ingredient_maps', 'nutrition'], true)) {
            (new CatalogService())->touchVersion($resource, $id, '后台维护');
        }
        Db::commit();
        } catch (\Throwable $e) {
            Db::rollback();
            $message = strpos($e->getMessage(), '23505') !== false || strpos($e->getMessage(), 'Duplicate entry') !== false
                ? '编号或名称已存在，请修改后重试' : '保存失败，请检查填写内容后重试';
            $this->error($message, null, ['__token__'=>$this->request->token()]);
        }
        $this->success('保存成功', null, ['id' => $id, '__token__'=>$this->request->token()]);
    }

    public function remove()
    {
        if (!$this->request->isPost()) $this->error('请求方式错误');
        $this->token();
        try {
            $resource=$this->request->post('resource','');$definition=$this->resource($resource);
            if (empty($definition['deletable'])) throw new DomainException('该数据不可删除，请改为停用',40001,400);
            $id=(int)$this->request->post('id',0);
            if ($id<=0 || !Db::name($definition['table'])->where($definition['pk'],$id)->find()) throw new DomainException('记录不存在，请刷新列表',40401,404);
            if ($resource==='suppliers' && (Db::name('shop_supplier_sku')->where('supplier_id',$id)->count() || Db::name('shop_supplier_order')->where('supplier_id',$id)->count() || Db::name('shop_delivery_area')->where('supplier_id',$id)->count())) throw new DomainException('供应商已关联商品、订单或配送区域，请改为停用，不能删除',40910,409);
            if ($resource==='integration_clients') {
                $client=Db::name('shop_integration_client')->where('id',$id)->find();
                if (Db::name('shop_external_identity')->where('client_id',$client['client_id'])->count()) throw new DomainException('调用方已关联用户身份，请改为停用，不能删除',40910,409);
            }
            Db::startTrans();
            try {
                if ($resource==='imports') Db::name('shop_master_data_import_row')->where('batch_id',$id)->delete();
                if (array_key_exists('deletetime',$definition['columns'])) Db::name($definition['table'])->where($definition['pk'],$id)->update(['deletetime'=>time(),'status'=>'hidden','updatetime'=>time()]);
                else Db::name($definition['table'])->where($definition['pk'],$id)->delete();
                Db::commit();
            } catch (\Throwable $e) { Db::rollback(); throw $e; }
        } catch (\Throwable $e) { $this->error($e instanceof DomainException?$e->getMessage():'删除失败，请刷新后重试',null,['__token__'=>$this->request->token()]); }
        $this->success('删除成功',null,['__token__'=>$this->request->token()]);
    }

    public function reviewApplication()
    {
        if (!$this->request->isPost()) $this->error('请求方式错误');
        $this->token();
        try {
            $id=(int)$this->request->post('id');$decision=$this->request->post('decision');
            if (!in_array($decision,['approved','rejected','supplement_required'],true)) throw new DomainException('审核结论无效',40001,400);
            Db::startTrans();
            try {
                $application=Db::name('shop_supplier_application')->where('id',$id)->lock(true)->find();
                if (!$application || $application['review_status']!=='pending') throw new DomainException('申请不存在或已处理',40910,409);
                $supplierId=0;
                if ($decision==='approved' && ($application['partner_type']??'supplier')==='supplier') {
                    $supplierId=Db::name('shop_supplier')->insertGetId([
                        'supplier_code'=>'SUP-'.date('Ymd').'-'.$id,'name'=>$application['company_name'],'company_name'=>$application['company_name'],
                        'credit_code'=>$application['credit_code']?:null,'contact_name'=>$application['contact_name'],'contact_mobile_encrypted'=>$application['contact_mobile_encrypted'],
                        'interface_type'=>'manual','service_area_json'=>$application['service_areas_json'],'status'=>'normal','version'=>1,'createtime'=>time(),'updatetime'=>time(),
                    ]);
                }
                Db::name('shop_supplier_application')->where('id',$id)->update([
                    'review_status'=>$decision,'review_admin_id'=>$this->auth->id,'review_comment'=>$this->request->post('comment',''),'supplier_id'=>$supplierId,
                    'reviewed_at'=>time(),'version'=>(int)$application['version']+1,'updatetime'=>time(),
                ]);
                Db::commit();
            } catch (\Throwable $e) { Db::rollback(); throw $e; }
        } catch (\Throwable $e) { $this->error($e instanceof DomainException?$e->getMessage():'审核失败，请刷新后重试',null,['__token__'=>$this->request->token()]); }
        $this->success('审核完成',null,['__token__'=>$this->request->token()]);
    }

    public function shipOrder()
    {
        if (!$this->request->isPost()) $this->error('请求方式错误');
        $this->token();
        try {
            $result=(new \addons\shop\library\v5\ManualFulfillmentService())->ship($this->request->post('order_sn'),$this->request->post('carrier'),$this->request->post('tracking_no'),$this->auth->id);
        } catch (\Exception $e) { $this->error($e->getMessage(),null,['__token__'=>$this->request->token()]); }
        $result['__token__']=$this->request->token();
        $this->success('已安排发货',null,$result);
    }

    public function retrySupplier()
    {
        if (!$this->request->isPost()) $this->error('请求方式错误');
        $this->token();
        try { $row=(new SupplierOrderService())->push((int)$this->request->post('id')); }
        catch (\Exception $e) { $this->error($e->getMessage(),null,['__token__'=>$this->request->token()]); }
        $row['__token__']=$this->request->token();
        $this->success($row['push_status']==='manual'?'人工对接供应商，请线下确认接单':'推送完成；接单与发货以供应商回执为准',null,$row);
    }

    public function resolveException()
    {
        if (!$this->request->isPost()) $this->error('请求方式错误');
        $this->token();
        try {
            $id=(int)$this->request->post('id');
            $resolution=trim((string)$this->request->post('resolution'));
            if ($resolution==='') throw new DomainException('必须填写处理结论',40001,400);
            $updated=Db::name('shop_exception_order')->where('id',$id)->where('status','in',['open','processing'])->update([
                'status'=>'resolved','resolution'=>$resolution,'assignee_admin_id'=>(int)$this->auth->id,'resolved_at'=>time(),'updatetime'=>time(),
            ]);
            if (!$updated) throw new DomainException('异常不存在或已处理，请刷新列表',40910,409);
        } catch (\Exception $e) { $this->error($e->getMessage(),null,['__token__'=>$this->request->token()]); }
        $this->success('异常已关闭；业务状态不会被自动改写',null,['__token__'=>$this->request->token()]);
    }

    public function adjustStock()
    {
        if (!$this->request->isPost()) $this->error('请求方式错误');
        $this->token();
        try {
            $delta=$this->request->post('delta');
            if (!is_scalar($delta) || !preg_match('/^-?\d+$/D',(string)$delta) || (float)$delta < -2147483648 || (float)$delta > 2147483647) throw new DomainException('库存调整量必须为有效整数',40005,400);
            $result=(new InventoryService())->adjust((int)$this->request->post('sku_id'),(int)$delta,(string)$this->request->post('reason'),(int)$this->auth->id,Identifiers::requestId());
        } catch (\Throwable $e) { $this->error($e instanceof DomainException?$e->getMessage():'库存调整失败，请刷新后重试',null,['__token__'=>$this->request->token()]); }
        $result['__token__']=$this->request->token();
        $this->success('库存调整成功，已写入不可变流水',null,$result);
    }

    public function revalidateRecommendation()
    {
        try {
            $result = (new RecommendationPackageService())->revalidateTrade((int)$this->request->post('id'));
            $this->success('交易校验完成', null, $result);
        } catch (\Exception $e) {
            $this->error($e->getMessage());
        }
    }

    public function retryBatch()
    {
        if (!$this->request->isPost()) $this->error('请求方式错误');
        $this->token();
        try {
            $batchId=(int)$this->request->post('id');
            $batch=Db::name('shop_plan_delivery_batch')->where('id',$batchId)->find();
            if (!$batch || !in_array($batch['status'],['scheduled','preparing','supplier_pending','exception'],true)) throw new DomainException('配送批次不存在或当前状态不可重试',40910,409);
            $plan=Db::name('shop_service_plan_order')->where('id',$batch['plan_order_id'])->find();
            $order=$plan?Db::name('shop_order')->where('order_sn',$plan['order_sn'])->find():null;
            if (!$plan || $plan['status']!=='active' || !$order || (int)$order['paystate']!==1 || (int)$order['orderstate']!==0) throw new DomainException('计划未生效或订单当前不可备货',40932,409);
            $orders=Db::name('shop_supplier_order')->where('plan_batch_id',$batchId)->column('id');
            if (!$orders) $orders=(new SupplierOrderService())->createForBatch($batchId,Identifiers::requestId());
            if (!$orders) throw new DomainException('未生成供应商订单，请检查计划状态、批次商品和供应商资料',40932,409);
            foreach ($orders as $id) (new SupplierOrderService())->push($id);
        } catch (\Exception $e) { $this->error($e->getMessage(),null,['__token__'=>$this->request->token()]); }
        $this->success('批次重试完成，请查看供应商推单状态',null,['supplier_order_ids'=>$orders,'__token__'=>$this->request->token()]);
    }

    public function publishPolicy()
    {
        $id = (int)$this->request->post('id');
        Db::startTrans();
        try {
            $policy = Db::name('shop_policy_version')->where('id', $id)->lock(true)->find();
            if (!$policy || $policy['status'] !== 'draft') {
                throw new DomainException('仅草稿政策可以发布', 40950, 409);
            }
            Db::name('shop_policy_version')->where('policy_type', $policy['policy_type'])->where('status', 'active')->update(['status'=>'retired','updatetime'=>time()]);
            Db::name('shop_policy_version')->where('id', $id)->update(['status'=>'active','effective_at'=>max(time(), (int)$policy['effective_at']),'updatetime'=>time()]);
            Db::commit();
            $this->success('政策版本已发布；历史订单继续引用原确认版本');
        } catch (\Exception $e) {
            Db::rollback();
            $this->error($e->getMessage());
        }
    }

    public function reviewAftersale()
    {
        if (!$this->request->isPost()) $this->error('请求方式错误');
        $this->token();
        try {
            $decision=(string)$this->request->post('decision');
            if (!in_array($decision,['approved','rejected'],true)) throw new DomainException('审核结果无效',40001,400);
            $id=(int)$this->request->post('id');$comment=trim((string)$this->request->post('comment'));
            $service=new RefundService();
            $result=$decision==='approved'?$service->approveAftersale($id,(int)$this->auth->id,$comment,Identifiers::requestId()):$service->rejectAftersale($id,(int)$this->auth->id,$comment);
        } catch (\Exception $e) { $this->error($e->getMessage(),null,['__token__'=>$this->request->token()]); }
        $result['__token__']=$this->request->token();
        $message='售后审核完成';
        if (isset($result['failure_message']) && $result['status']==='failed') $message='审核已通过，但退款提交失败：'.$result['failure_message'].'；尚未退款成功，请查看退款记录和异常';
        elseif ($decision==='approved' && isset($result['refund_sn'])) $message='审核已通过，退款处理中；以支付渠道最终结果为准';
        $this->success($message,null,$result);
    }

    public function retryOutbox()
    {
        if (!$this->request->isPost()) $this->error('请求方式错误');
        $this->token();
        try {
            $id=(int)$this->request->post('id');
            $event=Db::name('shop_outbox_event')->where('id',$id)->find();
            if (!$event || !in_array($event['status'],['failed','pending'],true)) throw new DomainException('事件不存在或已发送',40910,409);
            Db::name('shop_outbox_event')->where('id',$id)->where('status','in',['failed','pending'])->update(['next_retry_at'=>0,'updatetime'=>time()]);
            (new OutboxDispatcher())->dispatch(1,$id);
            $event=Db::name('shop_outbox_event')->where('id',$id)->find();
            if ($event['status']!=='sent') throw new DomainException('事件尚未发送：'.($event['last_error']?:'等待处理'),40910,409);
        } catch (\Exception $e) { $this->error($e->getMessage(),null,['__token__'=>$this->request->token()]); }
        $this->success('所选事件已处理',null,['id'=>$id,'status'=>$event['status'],'__token__'=>$this->request->token()]);
    }

    public function downloadImportTemplate()
    {
        $path = (new SupplierCatalogImportService())->createTemplate();
        $content = file_get_contents($path);
        @unlink($path);
        return Response::create($content, '', 200, [
            'Content-Type' => 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'Content-Disposition' => "attachment; filename*=UTF-8''" . rawurlencode('家庭营养师供应商商品目录-嵌入图片版.xlsx'),
            'Content-Length' => strlen($content),
            'Cache-Control' => 'no-store, no-cache, must-revalidate, max-age=0',
            'Pragma' => 'no-cache',
        ]);
    }

    public function previewImport()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $maxBytes = 12 * 1024 * 1024;
        if ((int)$this->request->server('CONTENT_LENGTH') > 14 * 1024 * 1024) {
            $this->error('上传文件超过服务器限制，请将 Excel 控制在 12 MB 以内');
        }
        $uploadError = isset($_FILES['file']['error']) ? (int)$_FILES['file']['error'] : UPLOAD_ERR_NO_FILE;
        if ($uploadError === UPLOAD_ERR_INI_SIZE || $uploadError === UPLOAD_ERR_FORM_SIZE) {
            $this->error('Excel 文件超过服务器上传上限，请将文件控制在 12 MB 以内');
        }
        if ($uploadError !== UPLOAD_ERR_OK && $uploadError !== UPLOAD_ERR_NO_FILE) {
            $this->error('文件上传失败，错误码：' . $uploadError);
        }
        $file = $this->request->file('file');
        if (!$file) {
            $this->error('请选择Excel文件');
        }
        if ((int)$file->getSize() > $maxBytes) {
            $this->error('Excel 文件不能超过 12 MB');
        }
        try {
            $result = (new SupplierCatalogImportService())->preview($file->getRealPath(), (string)$file->getInfo('name'), (int)$this->auth->id);
        } catch (\Exception $e) {
            $this->error($e->getMessage());
        }
        $this->success($result['duplicate'] ? '该文件已经预检过，已返回原批次' : '供应商商品目录预检完成', null, $result);
    }

    public function confirmImport()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        try {
            $result = (new SupplierCatalogImportService())->confirm((int)$this->request->post('batch_id'), (int)$this->auth->id);
        } catch (\Exception $e) {
            $this->error($e->getMessage());
        }
        $this->success('供应商商品目录导入完成', null, $result);
    }

    public function importDetail()
    {
        try {
            $result = (new MasterDataImportService())->detail((int)$this->request->get('id', 0));
        } catch (\Exception $e) {
            $this->error($e->getMessage());
        }
        $this->success('导入批次详情', null, $result);
    }

    protected function render()
    {
        // Version the workspace assets by content so existing browser caches refresh.
        $site=\think\Config::get('site');
        $site['version'].='-commerce-'.substr(hash_file('sha256',ROOT_PATH.'public/assets/js/backend/shop/v5/workspace.js'),0,12);
        $this->assignconfig('site',array_intersect_key($site,array_flip(['name','indexurl','cdnurl','version','timezone','languages'])));
        $this->view->assign('site',$site);
        $workspaces = $this->workspaces();
        if (!isset($workspaces[$this->workspace])) {
            $this->error('页面配置不存在');
        }
        $config = $workspaces[$this->workspace];
        $config['key'] = $this->workspace;
        $config['csrfToken'] = $this->request->token();
        foreach ($config['tabs'] as &$tab) {
            $resource = $this->resource($tab['resource']);
            $tab['columns'] = $resource['columns'];
            $tab['fields'] = isset($resource['fields']) ? $resource['fields'] : [];
            $tab['editable'] = !empty($resource['editable']);
            $tab['deletable'] = !empty($resource['deletable']);
            $tab['pk'] = $resource['pk'];
        }
        $this->assignconfig('v5Workspace', $config);
        $this->view->assign('workspace', $config);
        $this->view->assign('dashboard', $this->dashboardData());
        $config['canManageSupplierApi']=$this->auth->check('shop/v5/workspace/suppliers') && $this->auth->check('shop/v5/workspace/settings');
        $this->assignconfig('v5Workspace',$config);
        return $this->view->fetch('shop/v5/workspace');
    }

    protected function dashboardData()
    {
        $todayStart=strtotime(date('Y-m-d 00:00:00'));
        return [
            'today_paid_cent'=>(int)round((float)Db::name('shop_order')->where('paytime','>=',$todayStart)->where('paystate',1)->sum('payamount')*100),
            'today_order_count'=>Db::name('shop_order')->where('createtime','>=',$todayStart)->count(),
            'pending_shipment_count'=>Db::name('shop_order')->where('order_type','normal')->where('paystate',1)->where('orderstate',0)->where('shippingstate',0)->count(),
            'pending_aftersale_count'=>Db::name('shop_order_aftersales')->where('status',1)->count(),
            'supplier_attention_count'=>Db::name('shop_supplier_order')->where('push_status','in',['failed','manual'])->where('status','in',['created','pushing','exception'])->count(),
        ];
    }

    protected function orderColumns()
    {
        return ['id'=>'ID','order_sn'=>'订单号','user_id'=>'用户ID','order_type'=>'订单类型','saleamount'=>'应付金额','payamount'=>'实付金额','paystate'=>'支付状态','shippingstate'=>'配送状态','orderstate'=>'订单状态','receiver'=>'收货人','mobile'=>'联系电话','address'=>'收货地址','createtime'=>'创建时间'];
    }

    protected function workspaces()
    {
        return [
            'dashboard'=>['title'=>'工作台','description'=>'查看销售概况、待发货、待售后和供应商待办','tabs'=>[['label'=>'待发货订单','resource'=>'orders_pending'],['label'=>'待审核售后','resource'=>'aftersales_pending']]],
            'product'=>['title'=>'商品管理','description'=>'维护商品、分类、规格、售价和库存，支持供应商商品导入','tabs'=>[['label'=>'商品列表','resource'=>'goods'],['label'=>'商品分类','resource'=>'categories'],['label'=>'规格管理','resource'=>'specs'],['label'=>'规格值','resource'=>'spec_values'],['label'=>'库存流水','resource'=>'inventory_logs'],['label'=>'商品导入记录','resource'=>'imports']]],
            'orders'=>['title'=>'订单管理','description'=>'按交易状态查询订单、查看商品明细和处理发货；历史订单继续保留','tabs'=>[['label'=>'全部订单','resource'=>'orders_all'],['label'=>'待付款','resource'=>'orders_unpaid'],['label'=>'待发货','resource'=>'orders_pending'],['label'=>'已发货','resource'=>'orders_shipping'],['label'=>'已完成','resource'=>'orders_completed'],['label'=>'已关闭','resource'=>'orders_closed']]],
            'fulfillment'=>['title'=>'发货与物流','description'=>'处理普通订单发货，查询配送状态和物流轨迹','tabs'=>[['label'=>'待发货','resource'=>'orders_pending'],['label'=>'配送中','resource'=>'orders_shipping'],['label'=>'物流轨迹','resource'=>'fulfillment_events']]],
            'aftersales'=>['title'=>'售后退款','description'=>'审核售后申请，查询退款进度；审核通过不代表退款成功','tabs'=>[['label'=>'待审核','resource'=>'aftersales_pending'],['label'=>'全部售后','resource'=>'aftersales'],['label'=>'退款记录','resource'=>'refunds']]],
            'members'=>['title'=>'用户管理','description'=>'查看小程序用户、收货地址、购物车和购买记录','tabs'=>[['label'=>'用户列表','resource'=>'members'],['label'=>'收货地址','resource'=>'addresses']]],
            'suppliers'=>['title'=>'供应商档案','description'=>'维护供应商资料和合作申请，查看对接配置','tabs'=>[['label'=>'供应商列表','resource'=>'suppliers'],['label'=>'合作申请','resource'=>'supplier_applications']]],
            'supplier_sku'=>['title'=>'供货商品','description'=>'维护供应商商品编码、采购价、起订量及库存信息','tabs'=>[['label'=>'供货商品','resource'=>'supplier_skus']]],
            'supplier_collaboration'=>['title'=>'供应商订单','description'=>'查询向供应商拆分的供货订单、明细和推送状态','tabs'=>[['label'=>'供应商订单','resource'=>'supplier_orders'],['label'=>'订单明细','resource'=>'supplier_order_items']]],
            'finance'=>['title'=>'财务记录','description'=>'查看支付、退款和订单金额；自动渠道对账、供应商结算及开票尚未接入','tabs'=>[['label'=>'支付记录','resource'=>'payments'],['label'=>'退款记录','resource'=>'refunds'],['label'=>'订单金额','resource'=>'orders_all']]],
            'analytics'=>['title'=>'经营统计','description'=>'查询商城订单记录和经营指标；金额以系统交易记录为准','tabs'=>[['label'=>'订单记录','resource'=>'orders_all'],['label'=>'日指标','resource'=>'metrics']]],
            'marketing'=>['title'=>'优惠券','description'=>'维护已有优惠券和领取记录','tabs'=>[['label'=>'优惠券','resource'=>'coupons'],['label'=>'领取记录','resource'=>'user_coupons']]],
            'delivery_rules'=>['title'=>'配送设置','description'=>'设置配送地区、时段和运费','tabs'=>[['label'=>'配送区域','resource'=>'delivery_areas'],['label'=>'配送时段','resource'=>'delivery_slots'],['label'=>'运费模板','resource'=>'freights']]],
            'settings'=>['title'=>'接口与支付配置','description'=>'维护商城集成调用方和支付基础配置，供应商密钥在供应商档案中维护','tabs'=>[['label'=>'集成调用方','resource'=>'integration_clients'],['label'=>'专属计划规则','resource'=>'plan_rules']]],
            'audit'=>['title'=>'权限与操作日志','description'=>'维护管理员角色权限，查看后台操作记录','tabs'=>[['label'=>'角色权限','resource'=>'roles'],['label'=>'操作日志','resource'=>'admin_logs']]],
            'technical'=>['title'=>'技术维护','description'=>'供技术人员排查系统异常、接口调用和任务执行情况','tabs'=>[['label'=>'系统异常','resource'=>'exceptions'],['label'=>'推单异常','resource'=>'exceptions_supplier'],['label'=>'接口日志','resource'=>'integration_logs'],['label'=>'事件补偿','resource'=>'outbox_events'],['label'=>'任务记录','resource'=>'job_runs']]],
        ];
    }

    protected function resource($key)
    {
        $resources = $this->resources();
        if (!isset($resources[$key])) {
            $this->error('数据资源不存在');
        }
        return $resources[$key];
    }

    protected function resources()
    {
        $status = ['normal' => '上架', 'hidden' => '下架'];
        return [
            'goods' => $this->r('shop_goods', ['id'=>'ID','goods_sn'=>'货号','image'=>'商品图片','title'=>'商品名称','sale_type'=>'销售类型','category_id'=>'商品分类','price_range'=>'售价区间','available_sku_count'=>'可售SKU','total_stocks'=>'总库存','status'=>'上架状态','updatetime'=>'更新时间'], ['goods_sn','title'], [
                'image'=>$this->f('商品图片','image'), 'title'=>$this->f('商品名称', 'text', true), 'sale_type'=>$this->f('销售类型','select',true,['normal'=>'普通商品','bundle'=>'组合商品','service'=>'服务商品']),
                'category_id'=>$this->f('商品分类','select',true,$this->categoryOptions()), 'agent_visible'=>$this->f('商品接口可见','select',true,[0=>'否',1=>'是']),
                'status'=>$this->f('上架状态','select',true,$status),
            ]),
            'specs' => $this->r('shop_spec', ['id'=>'ID','name'=>'规格名称','updatetime'=>'更新时间'], ['name'], [
                'name'=>$this->f('规格名称','text',true),
            ]),
            'spec_values' => $this->r('shop_spec_value', ['id'=>'ID','spec_id'=>'规格名称','value'=>'规格值','updatetime'=>'更新时间'], ['value'], [
                'spec_id'=>$this->f('规格名称','select',true,$this->specOptions()), 'value'=>$this->f('规格值','text',true),
            ]),
            'categories' => $this->r('shop_category', ['id'=>'ID','name'=>'分类名称','business_category_code'=>'业务编码','weigh'=>'排序','status'=>'状态'], ['name','business_category_code'], [
                'name'=>$this->f('分类名称','text',true), 'business_category_code'=>$this->f('业务编码'),
                'agent_visible'=>$this->f('商品接口可见','select',true,[0=>'否',1=>'是']), 'weigh'=>$this->f('排序','number'), 'status'=>$this->f('状态','select',true,$status),
            ]),
            'skus' => $this->r('shop_goods_sku', ['id'=>'ID','goods_id'=>'商品名称','sku_code'=>'SKU编码','sku_id'=>'规格标识','price'=>'售价','stocks'=>'实物库存','reserved_stock'=>'占用库存','safety_stock'=>'安全库存','net_content_value'=>'净含量','net_content_unit'=>'单位','stock_updated_at'=>'库存更新时间'], ['sku_code','goods_sn','sku_id'], [
                'goods_id'=>$this->f('商品','select',true,$this->goodsOptions()), 'sku_code'=>$this->f('SKU编码（自动生成）','text'), 'sku_id'=>$this->f('规格标识','text',true),
                'price'=>$this->f('售价','number',true), 'marketprice'=>$this->f('市场价','number'), 'stocks'=>$this->f('实物库存','number',true), 'safety_stock'=>$this->f('安全库存','number',true), 'net_content_value'=>$this->f('净含量','number',true),
                'net_content_unit'=>$this->f('单位','select',true,['g'=>'克','kg'=>'千克','ml'=>'毫升','piece'=>'件','pack'=>'包']),
            ]),
            'inventory_logs' => $this->r('shop_inventory_log', ['id'=>'ID','sku_id'=>'SKU名称','change_type'=>'变动类型','quantity_delta'=>'实物变化','stock_before'=>'变动前库存','stock_after'=>'变动后库存','reserved_before'=>'变动前占用','reserved_after'=>'变动后占用','source_type'=>'来源','source_ref'=>'业务号','reason'=>'原因','createtime'=>'时间'], ['source_ref','request_id']),
            'imports' => $this->r('shop_master_data_import', ['id'=>'ID','batch_sn'=>'批次号','original_name'=>'文件名','status'=>'状态','total_rows'=>'总行数','valid_rows'=>'有效','invalid_rows'=>'错误','inserted_count'=>'新增','updated_count'=>'更新','created_by'=>'创建人','confirmed_by'=>'确认人','imported_at'=>'导入时间','createtime'=>'预检时间'], ['batch_sn','original_name','status'], [], true),
            'ingredients' => $this->r('shop_ingredient', ['id'=>'ID','ingredient_code'=>'食材编码','name'=>'食材名称','category_code'=>'类别','default_unit'=>'默认单位','status'=>'状态','version'=>'版本','updatetime'=>'更新时间'], ['ingredient_code','name'], [
                'ingredient_code'=>$this->f('食材编码','text',true), 'name'=>$this->f('食材名称','text',true),
                'category_code'=>$this->f('类别编码','text',true), 'default_unit'=>$this->f('默认单位','select',true,['g'=>'克','kg'=>'千克','ml'=>'毫升','piece'=>'件']),
                'description'=>$this->f('说明','textarea'), 'status'=>$this->f('状态','select',true,$status),
            ], true),
            'ingredient_maps' => $this->r('shop_ingredient_sku_map', ['id'=>'ID','ingredient_id'=>'食材名称','goods_id'=>'商品名称','sku_id'=>'SKU名称','role'=>'角色','net_value'=>'可用净量','net_unit'=>'单位','convert_ratio'=>'换算率','loss_rate'=>'损耗率','priority'=>'优先级','review_status'=>'审核状态','source_ref'=>'换算来源','reviewer_id'=>'审核人ID','reviewed_at'=>'审核时间','valid_to'=>'有效截止','version'=>'版本','status'=>'状态','updatetime'=>'更新时间'], ['ingredient_id','sku_id'], [
                'ingredient_id'=>$this->f('食材ID','number',true), 'goods_id'=>$this->f('商品ID','number',true), 'sku_id'=>$this->f('SKU ID','number',true),
                'role'=>$this->f('角色','select',true,['primary'=>'主食材','component'=>'组成','alternative'=>'备选']),
                'net_value'=>$this->f('可用净量','number',true), 'net_unit'=>$this->f('单位','text',true),
                'convert_ratio'=>$this->f('换算率','number',true), 'loss_rate'=>$this->f('损耗率','number',true), 'priority'=>$this->f('优先级','number'), 'source_ref'=>$this->f('真实换算依据或证明文件','textarea'), 'valid_from'=>$this->f('有效开始（日期时间）'), 'valid_to'=>$this->f('有效截止（审核通过时必填）'),
                'review_status'=>$this->f('审核状态','select',true,['pending'=>'待审核','approved'=>'已通过','rejected'=>'已拒绝']), 'status'=>$this->f('状态','select',true,$status),
            ]),
            'nutrition' => $this->r('shop_sku_nutrition_fact', ['id'=>'ID','sku_id'=>'SKU名称','basis_type'=>'基准','energy_kcal'=>'能量kcal','protein_g'=>'蛋白质g','fat_g'=>'脂肪g','carbohydrate_g'=>'碳水g','fiber_g'=>'膳食纤维g','sodium_mg'=>'钠mg','source_name'=>'来源','source_version'=>'来源版本','review_status'=>'审核状态','reviewed_at'=>'审核时间','valid_to'=>'有效截止','version'=>'版本','status'=>'状态'], ['sku_id','source_name'], [
                'sku_id'=>$this->f('SKU ID','number',true), 'basis_type'=>$this->f('基准类型','text',true), 'basis_value'=>$this->f('基准值','number',true), 'basis_unit'=>$this->f('基准单位','text',true),
                'energy_kcal'=>$this->f('能量kcal','number'), 'protein_g'=>$this->f('蛋白质g','number'), 'fat_g'=>$this->f('脂肪g','number'),
                'carbohydrate_g'=>$this->f('碳水g','number'), 'fiber_g'=>$this->f('膳食纤维g','number'), 'sodium_mg'=>$this->f('钠mg','number'),
                'source_name'=>$this->f('资料来源','text',true), 'source_version'=>$this->f('来源版本'), 'valid_from'=>$this->f('有效开始（日期时间）'), 'valid_to'=>$this->f('有效截止（审核通过时必填）'),
                'review_status'=>$this->f('审核状态','select',true,['pending'=>'待审核','approved'=>'已通过','rejected'=>'已拒绝']), 'status'=>$this->f('状态','select',true,$status),
            ]),
            'catalog_readiness' => $this->r('shop_goods_sku', ['id'=>'SKU ID','title'=>'商品','specification'=>'规格','mapping_status'=>'采购映射','nutrition_status'=>'营养资料','allergen_status'=>'过敏原资料','missing_data'=>'待补事项']),
            'catalog_reviews' => $this->r('shop_catalog_review_log', ['id'=>'ID','resource_type'=>'资料类型','resource_id'=>'资料ID','admin_id'=>'操作人ID','createtime'=>'时间'], ['resource_type']),
            'components' => $this->r('shop_sku_ingredient_component', ['id'=>'ID','sku_id'=>'SKU ID','ingredient_id'=>'食材ID','component_value'=>'成分数量','component_unit'=>'单位','allergen_flag'=>'含过敏原','data_source'=>'来源文件或声明','data_version'=>'来源版本','updatetime'=>'更新时间'], ['data_source'], [
                'sku_id'=>$this->f('SKU ID','number',true),'ingredient_id'=>$this->f('食材ID','number',true),
                'component_value'=>$this->f('成分数量','number',true),'component_unit'=>$this->f('单位','select',true,['g'=>'克','kg'=>'千克','ml'=>'毫升','piece'=>'件','pack'=>'包']),
                'allergen_flag'=>$this->f('该成分是否为已声明过敏原','select',true,['0'=>'不是','1'=>'是']),
                'data_source'=>$this->f('真实配料表或声明来源','textarea',true),'data_version'=>$this->f('资料版本','text',true),
            ]),
            'recommendations' => $this->r('shop_recommendation_package', ['id'=>'ID','package_sn'=>'推荐包号','agent_client_id'=>'Agent','agent_task_id'=>'任务号','user_ref'=>'用户引用','family_ref'=>'家庭引用','current_version'=>'当前版本','nutrition_status'=>'营养校验','trade_status'=>'交易校验','confirm_status'=>'用户确认','total_amount_cent'=>'金额(分)','status'=>'状态','expires_at'=>'失效时间','createtime'=>'创建时间'], ['package_sn','agent_task_id','user_ref']),
            'recommendation_versions' => $this->r('shop_recommendation_package_version', ['id'=>'ID','package_id'=>'推荐包ID','version_no'=>'版本','base_version_no'=>'基础版本','menu_version_ref'=>'菜单版本','nutrition_status'=>'营养校验','trade_status'=>'交易校验','total_amount_cent'=>'金额(分)','change_type'=>'变更类型','createtime'=>'创建时间'], ['package_id','menu_version_ref']),
            'bundle_items' => $this->r('shop_bundle_item', ['id'=>'ID','bundle_goods_id'=>'食材包商品','bundle_sku_id'=>'食材包SKU','item_goods_id'=>'成员商品','item_sku_id'=>'成员SKU','quantity'=>'件数','version_no'=>'版本','status'=>'状态','updatetime'=>'更新时间'], ['bundle_sku_id','item_sku_id'], [
                'bundle_goods_id'=>$this->f('食材包商品ID','number',true), 'bundle_sku_id'=>$this->f('食材包SKU ID','number',true),
                'item_goods_id'=>$this->f('成员商品ID','number',true), 'item_sku_id'=>$this->f('成员SKU ID','number',true),
                'quantity'=>$this->f('件数','number',true), 'sort'=>$this->f('排序','number'), 'version_no'=>$this->f('版本','number',true), 'status'=>$this->f('状态','select',true,$status),
            ]),
            'recipe_maps' => $this->r('shop_recipe_bundle_map', ['id'=>'ID','recipe_ref'=>'菜品引用','recipe_version_ref'=>'菜品版本','bundle_sku_id'=>'食材包SKU','people_count'=>'人数','meal_type'=>'餐次','priority'=>'优先级','status'=>'状态'], ['recipe_ref','recipe_version_ref'], [
                'recipe_ref'=>$this->f('菜品引用','text',true), 'recipe_version_ref'=>$this->f('菜品版本'), 'bundle_sku_id'=>$this->f('食材包SKU ID','number',true),
                'people_count'=>$this->f('适用人数','number',true), 'meal_type'=>$this->f('餐次','select',true,['breakfast'=>'早餐','lunch'=>'午餐','dinner'=>'晚餐','snack'=>'加餐']),
                'priority'=>$this->f('优先级','number'), 'status'=>$this->f('状态','select',true,$status),
            ]),
            'swaps' => $this->r('shop_recommendation_swap', ['id'=>'ID','swap_request_id'=>'换菜请求','package_id'=>'推荐包ID','base_version_no'=>'原版本','result_version_no'=>'新版本','old_recipe_ref'=>'原菜品','new_recipe_ref'=>'新菜品','nutrition_status'=>'营养复核','trade_status'=>'交易复核','status'=>'状态','createtime'=>'时间'], ['swap_request_id','old_recipe_ref','new_recipe_ref']),
            'plans' => $this->r('shop_service_plan', ['id'=>'ID','plan_sn'=>'计划号','plan_name'=>'计划名称','user_ref'=>'用户引用','family_ref'=>'家庭引用','plan_days'=>'天数','delivery_frequency'=>'配送频率','current_version'=>'版本','nutrition_status'=>'营养校验','trade_status'=>'交易校验','review_gate_status'=>'专业审核','estimated_amount_cent'=>'预计金额(分)','status'=>'状态','createtime'=>'创建时间'], ['plan_sn','plan_name','user_ref']),
            'plan_versions' => $this->r('shop_service_plan_version', ['id'=>'ID','plan_id'=>'计划ID','version_no'=>'版本','base_version_no'=>'基础版本','catalog_version'=>'目录版本','nutrition_status'=>'营养校验','review_gate_status'=>'审核门禁','trade_status'=>'交易校验','change_reason'=>'变更原因','createtime'=>'创建时间'], ['plan_id','nutrition_validation_id']),
            'plan_days' => $this->r('shop_service_plan_day', ['id'=>'ID','plan_version_id'=>'计划版本ID','day_no'=>'第几天','relative_date_offset'=>'日期偏移','display_title'=>'标题','daily_summary'=>'摘要','createtime'=>'创建时间'], ['display_title','daily_summary']),
            'reviews' => $this->r('shop_professional_review_ref', ['id'=>'ID','review_ref'=>'审核引用','resource_type'=>'资源类型','resource_ref'=>'业务号','resource_version'=>'版本','review_system'=>'审核系统','review_status'=>'审核状态','purchase_gate'=>'购买门禁','summary'=>'摘要','reviewed_at'=>'审核时间','updatetime'=>'更新时间'], ['review_ref','resource_ref']),
            'purchase_lists' => $this->r('shop_purchase_list', ['id'=>'ID','purchase_list_sn'=>'清单号','user_id'=>'用户ID','source_type'=>'来源','source_ref'=>'来源编号','source_version'=>'来源版本','current_version'=>'当前版本','match_status'=>'匹配状态','confirm_status'=>'确认状态','estimated_total_cent'=>'预计金额(分)','status'=>'状态','expires_at'=>'失效时间'], ['purchase_list_sn','source_ref']),
            'purchase_items' => $this->r('shop_purchase_item', ['id'=>'ID','purchase_list_id'=>'清单ID','list_version_no'=>'版本','recipe_ref'=>'菜品引用','ingredient_id'=>'食材ID','required_value'=>'总需求','pantry_value'=>'家中已有','net_required_value'=>'净需求','match_status'=>'匹配状态','selected_match_id'=>'选中匹配'], ['purchase_list_id','recipe_ref']),
            'purchase_matches' => $this->r('shop_purchase_match', ['id'=>'ID','purchase_item_id'=>'采购项ID','sku_id'=>'SKU ID','rank_no'=>'候选排序','required_pack_count'=>'购买件数','covered_value'=>'覆盖量','surplus_value'=>'余量','total_price_cent'=>'金额(分)','trade_status'=>'交易状态','requires_agent_revalidation'=>'需Agent复核','is_selected'=>'已选'], ['purchase_item_id','sku_id']),
            'addresses' => $this->r('shop_address', ['id'=>'ID','user_id'=>'用户ID','receiver'=>'收货人','mobile'=>'联系电话','province_id'=>'省ID','city_id'=>'市ID','area_id'=>'区ID','address'=>'详细地址','isdefault'=>'默认地址','row_version'=>'版本','updatetime'=>'更新时间'], ['receiver','mobile','address'], [], false, ['status'=>'normal','deletetime'=>null]),
            'orders_unpaid'=>$this->r('shop_order',$this->orderColumns(),['order_sn','receiver'],[],false,['paystate'=>0,'orderstate'=>0]),
            'orders_pending'=>$this->r('shop_order',$this->orderColumns(),['order_sn','receiver'],[],false,['order_type'=>'normal','paystate'=>1,'orderstate'=>0,'shippingstate'=>0]),
            'orders_shipping'=>$this->r('shop_order',$this->orderColumns(),['order_sn','receiver'],[],false,['paystate'=>1,'shippingstate'=>1]),
            'orders_completed'=>$this->r('shop_order',$this->orderColumns(),['order_sn','receiver'],[],false,['orderstate'=>3]),
            'orders_closed'=>$this->r('shop_order',$this->orderColumns(),['order_sn','receiver'],[],false,['orderstate'=>['in',[1,2]]]),
            'aftersales_pending'=>$this->r('shop_order_aftersales',['id'=>'ID','order_id'=>'订单ID','order_goods_id'=>'订单商品ID','user_id'=>'用户ID','reason'=>'申请原因','refund'=>'申请退款金额','status'=>'状态','createtime'=>'申请时间'],['order_id','reason'],[],false,['status'=>1]),
            'orders_normal' => $this->r('shop_order', ['id'=>'ID','order_sn'=>'订单号','user_id'=>'用户ID','order_type'=>'类型','saleamount'=>'应付金额','payamount'=>'实付金额','paystate'=>'支付状态','shippingstate'=>'配送状态','orderstate'=>'订单状态','receiver'=>'收货人','mobile'=>'联系电话','address'=>'收货地址','createtime'=>'创建时间'], ['order_sn','receiver'], [], false, ['order_type'=>'normal']),
            'orders_all' => $this->r('shop_order',$this->orderColumns(),['order_sn','receiver']),
            'plan_orders' => $this->r('shop_service_plan_order', ['id'=>'ID','plan_order_sn'=>'计划订单号','order_sn'=>'商城订单号','plan_id'=>'计划ID','user_id'=>'用户ID','first_delivery_date'=>'首批日期','total_batches'=>'总批次','completed_batches'=>'已完成','total_amount_cent'=>'实付金额(分)','fulfilled_amount_cent'=>'已履约金额(分)','exception_refunded_amount_cent'=>'例外退款(分)','user_cancellable'=>'用户可取消','status'=>'状态','row_version'=>'版本','updatetime'=>'更新时间'], ['plan_order_sn','order_sn']),
            'payments' => $this->r('shop_payment_record', ['id'=>'ID','payment_sn'=>'支付单号','order_sn'=>'订单号','channel'=>'渠道','amount_cent'=>'金额(分)','status'=>'状态','paid_at'=>'支付时间','last_query_at'=>'最后查询','updatetime'=>'更新时间'], ['payment_sn','order_sn']),
            'batches' => $this->r('shop_plan_delivery_batch', ['id'=>'ID','batch_sn'=>'批次号','plan_order_id'=>'计划订单ID','batch_no'=>'批次序号','meal_date'=>'食用日期','delivery_date'=>'送达日期','inventory_lock_at'=>'锁库存时间','allocated_pay_amount_cent'=>'分摊实付(分)','inventory_status'=>'库存状态','supplier_status'=>'供应商状态','fulfillment_status'=>'履约状态','status'=>'批次状态','row_version'=>'版本'], ['batch_sn','plan_order_id']),
            'batches_prepare' => $this->r('shop_plan_delivery_batch', ['id'=>'ID','batch_sn'=>'批次号','plan_order_id'=>'计划订单ID','batch_no'=>'序号','delivery_date'=>'送达日期','inventory_lock_at'=>'锁库存时间','inventory_status'=>'库存状态','supplier_status'=>'供应商状态','status'=>'批次状态'], ['batch_sn'], [], false, ['status'=>['in',['scheduled','preparing','supplier_pending']]]),
            'batches_shipping' => $this->r('shop_plan_delivery_batch', ['id'=>'ID','batch_sn'=>'批次号','plan_order_id'=>'计划订单ID','batch_no'=>'序号','delivery_date'=>'送达日期','supplier_status'=>'供应商状态','fulfillment_status'=>'履约状态','shipped_at'=>'发货时间','delivered_at'=>'送达时间','status'=>'状态'], ['batch_sn'], [], false, ['status'=>['in',['shipped','delivered']]]),
            'batch_items' => $this->r('shop_plan_delivery_batch_item', ['id'=>'ID','batch_id'=>'批次ID','goods_id'=>'商品ID','sku_id'=>'SKU ID','quantity'=>'数量','unit_price_cent'=>'单价(分)','line_amount_cent'=>'金额(分)','inventory_reservation_id'=>'库存占用','supplier_order_item_id'=>'供应商明细','status'=>'状态'], ['batch_id','sku_id']),
            'plan_changes' => $this->r('shop_plan_change_request', ['id'=>'ID','change_request_sn'=>'变更单号','plan_order_id'=>'计划订单ID','request_type'=>'类型','base_version'=>'基础版本','agent_revalidation_ref'=>'Agent重评','request_user_id'=>'申请会员','status'=>'状态','processed_at'=>'处理时间','failure_message'=>'失败原因','createtime'=>'创建时间'], ['change_request_sn','plan_order_id']),
            'fulfillment_events' => $this->r('shop_fulfillment_event', ['id'=>'ID','event_id'=>'事件号','platform_order_sn'=>'订单号','plan_batch_id'=>'批次ID','carrier_code'=>'承运商','tracking_no'=>'运单号','source_status'=>'原始状态','normalized_status'=>'标准状态','occurred_at'=>'发生时间','location'=>'位置','description'=>'说明'], ['event_id','platform_order_sn','tracking_no']),
            'aftersales' => $this->r('shop_order_aftersales', ['id'=>'ID','order_id'=>'订单ID','order_goods_id'=>'订单商品ID','user_id'=>'用户ID','source_type'=>'来源','batch_id'=>'批次ID','reason_code'=>'原因码','reason'=>'原因','refund'=>'退款金额','status'=>'状态','createtime'=>'申请时间'], ['order_id','reason']),
            'refunds' => $this->r('shop_refund_record', ['id'=>'ID','refund_sn'=>'退款单号','order_sn'=>'订单号','aftersale_id'=>'售后ID','refund_amount_cent'=>'退款金额(分)','reason'=>'原因','status'=>'状态','requested_at'=>'申请时间','success_at'=>'成功时间','failure_message'=>'失败信息'], ['refund_sn','order_sn']),
            'exceptions' => $this->r('shop_exception_order', ['id'=>'ID','exception_sn'=>'异常单号','severity'=>'级别','module'=>'模块','exception_type'=>'类型','resource_ref'=>'业务号','order_sn'=>'订单号','summary'=>'摘要','assignee_admin_id'=>'处理人','status'=>'状态','retry_count'=>'重试次数','createtime'=>'创建时间'], ['exception_sn','resource_ref','order_sn','summary']),
            'exceptions_supply' => $this->r('shop_exception_order', ['id'=>'ID','exception_sn'=>'异常单号','severity'=>'级别','exception_type'=>'类型','resource_ref'=>'业务号','order_sn'=>'订单号','batch_id'=>'批次ID','summary'=>'摘要','status'=>'状态','createtime'=>'创建时间'], ['exception_sn','resource_ref','summary'], [], false, ['module'=>'supply_chain']),
            'exceptions_supplier' => $this->r('shop_exception_order', ['id'=>'ID','exception_sn'=>'异常单号','severity'=>'级别','exception_type'=>'类型','resource_ref'=>'供应商业务号','order_sn'=>'订单号','supplier_order_id'=>'供应商订单ID','summary'=>'摘要','status'=>'状态','retry_count'=>'重试次数','createtime'=>'创建时间'], ['exception_sn','resource_ref','summary'], [], false, ['module'=>'supplier']),
            'suppliers' => $this->r('shop_supplier', ['id'=>'ID','supplier_code'=>'供应商编码','name'=>'名称','company_name'=>'公司主体','credit_code'=>'信用代码','contact_name'=>'联系人','interface_type'=>'接口方式','endpoint_url'=>'接口地址','priority'=>'优先级','secret_configured'=>'密钥已配置','status'=>'状态','version'=>'版本','updatetime'=>'更新时间'], ['supplier_code','name','company_name'], [
                'supplier_code'=>$this->f('供应商编码','text',true), 'name'=>$this->f('名称','text',true), 'company_name'=>$this->f('公司主体','text',true),
                'credit_code'=>$this->f('统一信用代码'), 'contact_name'=>$this->f('联系人'), 'priority'=>$this->f('优先级','number'), 'status'=>$this->f('状态','select',true,$status),
            ], true),
            'supplier_applications' => $this->r('shop_supplier_application', ['id'=>'ID','application_sn'=>'申请编号','user_id'=>'用户ID','company_name'=>'公司名称','partner_type'=>'合作类型','credit_code'=>'信用代码','contact_name'=>'联系人','review_status'=>'审核状态','review_admin_id'=>'审核人','review_comment'=>'审核意见','supplier_id'=>'供应商ID','submitted_at'=>'提交时间','reviewed_at'=>'审核时间'], ['application_sn','company_name','credit_code']),
            'supplier_skus' => $this->r('shop_supplier_sku', ['id'=>'ID','supplier_id'=>'供应商ID','sku_id'=>'平台SKU','supplier_sku_code'=>'供应商SKU','supplier_sku_name'=>'供应商商品名','purchase_price_cent'=>'采购价(分)','minimum_order_quantity'=>'最小起订量','stock_status'=>'库存状态','stock_quantity'=>'供应商库存','stock_updated_at'=>'同步时间','priority'=>'优先级','status'=>'状态'], ['supplier_sku_code','supplier_sku_name'], [
                'supplier_id'=>$this->f('供应商ID','number',true), 'sku_id'=>$this->f('平台SKU ID','number',true),
                'supplier_sku_code'=>$this->f('供应商SKU编码','text',true), 'supplier_sku_name'=>$this->f('供应商商品名'),
                'purchase_price_cent'=>$this->f('采购价(分)','number',true), 'minimum_order_quantity'=>$this->f('最小起订量','number',true),
                'stock_status'=>$this->f('库存状态','select',true,['sufficient'=>'充足','low'=>'偏低','out'=>'缺货','unknown'=>'未知']),
                'stock_quantity'=>$this->f('供应商库存','number'), 'priority'=>$this->f('优先级','number'), 'status'=>$this->f('状态','select',true,$status),
            ]),
            'supplier_orders' => $this->r('shop_supplier_order', ['id'=>'ID','supplier_order_sn'=>'供应商订单号','supplier_id'=>'供应商ID','platform_order_sn'=>'平台订单号','plan_batch_id'=>'批次ID','external_order_no'=>'外部单号','status'=>'业务状态','push_status'=>'推单状态','push_attempts'=>'尝试次数','next_retry_at'=>'下次重试','reject_code'=>'拒单原因','updatetime'=>'更新时间'], ['supplier_order_sn','platform_order_sn','external_order_no']),
            'supplier_order_items' => $this->r('shop_supplier_order_item', ['id'=>'ID','supplier_order_id'=>'供应商订单ID','plan_batch_item_id'=>'批次商品ID','supplier_sku_id'=>'供应商SKU','quantity'=>'数量','purchase_price_cent'=>'采购价(分)','unavailable_quantity'=>'缺货数量','reason_code'=>'原因码','status'=>'状态'], ['supplier_order_id','supplier_sku_id']),
            'integration_logs' => $this->r('shop_integration_log', ['id'=>'ID','request_id'=>'请求ID','partner_type'=>'合作方类型','partner_code'=>'合作方','direction'=>'方向','interface_name'=>'接口','business_type'=>'业务类型','business_ref'=>'业务号','response_code'=>'响应码','http_status'=>'HTTP','duration_ms'=>'耗时ms','success'=>'成功','retry_count'=>'重试','error_code'=>'错误码','createtime'=>'时间'], ['request_id','partner_code','business_ref']),
            'delivery_areas' => $this->r('shop_delivery_area', ['id'=>'ID','area_code'=>'区域编码','name'=>'区域名称','province_code'=>'省编码','city_code'=>'市编码','district_code'=>'区编码','supplier_id'=>'供应商ID','status'=>'状态','version'=>'版本','updatetime'=>'更新时间'], ['area_code','name'], [
                'area_code'=>$this->f('区域编码','text',true), 'name'=>$this->f('区域名称','text',true), 'province_code'=>$this->f('省编码'),
                'city_code'=>$this->f('市编码'), 'district_code'=>$this->f('区编码'), 'supplier_id'=>$this->f('供应商ID','number'),
                'postal_codes_json'=>$this->f('邮编JSON','textarea'), 'status'=>$this->f('配送状态','select',true,['normal'=>'支持配送','hidden'=>'暂停配送']),
            ]),
            'delivery_slots' => $this->r('shop_delivery_slot', ['id'=>'ID','area_id'=>'区域ID','slot_code'=>'时段编码','name'=>'名称','start_time'=>'开始','end_time'=>'结束','cutoff_minutes'=>'提前截单分钟','capacity'=>'容量','used_capacity'=>'已用','weekday_mask'=>'星期','extra_fee_cent'=>'附加费(分)','status'=>'状态'], ['slot_code','name'], [
                'area_id'=>$this->f('区域ID','number',true), 'slot_code'=>$this->f('时段编码','text',true), 'name'=>$this->f('名称','text',true),
                'start_time'=>$this->f('开始时间','text',true), 'end_time'=>$this->f('结束时间','text',true),
                'service_scope'=>$this->f('名额用途','select',true,['normal'=>'普通订单','plan'=>'专属计划（每日独立容量）']),
                'cutoff_minutes'=>$this->f('提前截单分钟','number'), 'capacity'=>$this->f('容量','number'),
                'weekday_mask'=>$this->f('配送星期'), 'blackout_dates_json'=>$this->f('停运日期JSON','textarea'),
                'extra_fee_cent'=>$this->f('附加费(分)','number'), 'status'=>$this->f('状态','select',true,$status),
            ]),
            'freights' => $this->r('shop_freight', ['id'=>'ID','name'=>'模板名称','type'=>'计费类型','temperature_zone'=>'温层','supplier_id'=>'供应商ID','delivery_slot_required'=>'必须选时段','switch'=>'启用','updatetime'=>'更新时间'], ['name']),
            'metrics' => $this->r('shop_metric_daily', ['id'=>'ID','metric_date'=>'日期','metric_group'=>'指标组','metric_key'=>'指标','dimension_key'=>'维度','metric_value'=>'数值','calculated_at'=>'计算时间'], ['metric_key','dimension_key']),
            'coupons' => $this->r('shop_coupon', ['id'=>'ID','name'=>'优惠券','result'=>'优惠类型','result_data'=>'优惠内容','source_scope'=>'适用来源','plan_allowed'=>'适用计划','refund_allocation_rule'=>'退款分摊','is_open'=>'启用','begintime'=>'开始','endtime'=>'结束'], ['name']),
            'user_coupons' => $this->r('shop_user_coupon', ['id'=>'ID','coupon_id'=>'优惠券ID','user_id'=>'用户ID','is_used'=>'使用状态','begin_time'=>'开始时间','expire_time'=>'失效时间','createtime'=>'领取时间'], ['coupon_id','user_id']),
            'members' => $this->r('user', ['id'=>'ID','username'=>'用户名','nickname'=>'昵称','mobile'=>'手机号','account_source'=>'账号来源','linked_account'=>'小程序账号','binding_status'=>'关联状态','wechat_status'=>'微信绑定','jointime'=>'加入时间','status'=>'状态'], ['username','nickname','mobile']),
            'external_identities' => $this->r('shop_external_identity', ['id'=>'ID','client_id'=>'调用方','external_user_ref'=>'外部用户引用','user_id'=>'商城用户ID','status'=>'状态','updatetime'=>'更新时间'], ['client_id','external_user_ref']),
            'integration_clients' => $this->r('shop_integration_client', ['id'=>'ID','client_id'=>'调用方编号','client_type'=>'类型','name'=>'名称','clock_skew_seconds'=>'时间偏差秒','secret_configured'=>'密钥已配置','status'=>'状态','version'=>'版本','updatetime'=>'更新时间'], ['client_id','name'], [
                'client_id'=>$this->f('调用方编号','text',true), 'client_type'=>$this->f('类型','select',true,['agent'=>'Agent','supplier'=>'供应商','logistics'=>'物流','review'=>'专业审核']),
                'name'=>$this->f('名称','text',true), 'secret_plaintext'=>$this->f('签名密钥','password'),
                'allowed_ip_json'=>$this->f('IP白名单JSON','textarea'), 'callback_whitelist_json'=>$this->f('回调白名单JSON','textarea'),
                'clock_skew_seconds'=>$this->f('允许时间偏差秒','number',true), 'status'=>$this->f('状态','select',true,$status),
            ], true),
            'plan_rules' => $this->r('shop_plan_policy', ['id'=>'ID','policy_version'=>'规则版本','status'=>'状态','effective_at'=>'生效时间','createtime'=>'发布时间'], ['policy_version'], [
                'policy_version'=>$this->f('新规则版本','text',true),
                'config_json'=>$this->f('完整配置（商品范围、重复限制、预算、费用与配送）','textarea',true),
                'effective_at'=>$this->f('生效时间戳','number',true),
            ]),
            'policies' => $this->r('shop_policy_version', ['id'=>'ID','policy_type'=>'政策类型','policy_version'=>'政策版本','title'=>'标题','content_hash'=>'内容哈希','effective_at'=>'生效时间','status'=>'状态','updatetime'=>'更新时间'], ['policy_type','policy_version','title'], [
                'policy_type'=>$this->f('政策类型','select',true,['plan_non_refund'=>'专属计划不退款']), 'policy_version'=>$this->f('政策版本','text',true),
                'title'=>$this->f('标题','text',true), 'content'=>$this->f('完整政策正文','textarea',true),
                'effective_at'=>$this->f('生效时间戳','number',true), 'status'=>$this->f('状态','select',true,['draft'=>'草稿','active'=>'生效','retired'=>'停用']),
            ]),
            'migrations' => $this->r('shop_schema_migration', ['id'=>'ID','version'=>'迁移版本','description'=>'说明','checksum'=>'校验值','executed_at'=>'执行时间'], ['version','description'], [], false, [], false),
            'admin_logs' => $this->r('admin_log', ['id'=>'ID','admin_id'=>'管理员ID','username'=>'管理员','url'=>'操作地址','title'=>'标题','content'=>'内容','ip'=>'IP','useragent'=>'客户端','createtime'=>'时间'], ['username','url','title']),
            'roles' => $this->r('auth_group', ['id'=>'ID','pid'=>'上级角色','name'=>'角色名称','rules'=>'权限规则ID','status'=>'状态','createtime'=>'创建时间','updatetime'=>'更新时间'], ['name'], [
                'pid'=>$this->f('上级角色ID','number',true),'name'=>$this->f('角色名称','text',true),'rules'=>$this->f('权限规则ID（逗号分隔）','textarea'),'status'=>$this->f('状态','select',true,['normal'=>'正常','hidden'=>'停用']),
            ]),
            'job_runs' => $this->r('shop_job_run', ['id'=>'ID','run_id'=>'运行ID','job_name'=>'任务','owner'=>'执行节点','status'=>'状态','processed_count'=>'处理数','success_count'=>'成功','failure_count'=>'失败','last_error'=>'最后错误','started_at'=>'开始','finished_at'=>'结束'], ['run_id','job_name']),
            'outbox_events' => $this->r('shop_outbox_event', ['id'=>'ID','event_id'=>'事件ID','event_type'=>'事件类型','aggregate_type'=>'资源类型','aggregate_ref'=>'业务号','aggregate_version'=>'版本','destination'=>'目标','status'=>'状态','attempts'=>'次数','next_retry_at'=>'下次重试','last_error'=>'最后错误','createtime'=>'创建时间'], ['event_id','event_type','aggregate_ref']),
        ];
    }

    protected function r($table, array $columns, array $search = [], array $fields = [], $deletable = false, array $where = [], $timestamps = true)
    {
        return ['table'=>$table, 'pk'=>'id', 'columns'=>$columns, 'search'=>$search, 'fields'=>$fields,
            'editable'=>!empty($fields), 'deletable'=>$deletable, 'where'=>$where, 'timestamps'=>$timestamps];
    }

    protected function categoryOptions()
    {
        $options = [];
        $rows = Db::name('shop_category')->where('status', 'normal')->order('weigh', 'desc')->order('id', 'asc')->field('id,name')->select();
        foreach ($rows as $row) $options[(string)$row['id']] = $row['name'];
        return $options;
    }

    protected function goodsOptions()
    {
        $options = [];
        $rows = Db::name('shop_goods')->where('status', 'normal')->order('id', 'desc')->field('id,title,goods_sn')->select();
        foreach ($rows as $row) $options[(string)$row['id']] = $row['title'] . ($row['goods_sn'] ? '（' . $row['goods_sn'] . '）' : '');
        return $options;
    }

    protected function specOptions()
    {
        $options = [];
        $rows = Db::name('shop_spec')->order('id', 'asc')->field('id,name')->select();
        foreach ($rows as $row) $options[(string)$row['id']] = $row['name'];
        return $options;
    }

    protected function f($title, $type = 'text', $required = false, array $options = [])
    {
        return ['title'=>$title, 'type'=>$type, 'required'=>$required, 'options'=>$options];
    }
}
