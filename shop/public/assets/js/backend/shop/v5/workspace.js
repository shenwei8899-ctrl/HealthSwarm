define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {
    var Controller = {
        dashboard: function () { Workspace.init(); }, product: function () { Workspace.init(); }, ingredients: function () { Workspace.init(); },
        recommendations: function () { Workspace.init(); }, plans: function () { Workspace.init(); }, purchases: function () { Workspace.init(); },
        orders: function () { Workspace.init(); }, batches: function () { Workspace.init(); }, fulfillment: function () { Workspace.init(); },
        aftersales: function () { Workspace.init(); }, suppliers: function () { Workspace.init(); }, supplier_sku: function () { Workspace.init(); },
        supplier_collaboration: function () { Workspace.init(); }, delivery_rules: function () { Workspace.init(); }, analytics: function () { Workspace.init(); },
        finance: function () { Workspace.init(); }, technical: function () { Workspace.init(); },
        marketing: function () { Workspace.init(); }, members: function () { Workspace.init(); }, settings: function () { Workspace.init(); }, audit: function () { Workspace.init(); }
    };

    var Workspace = {
        config: {}, pages: {},
        init: function () {
            this.config = Config.v5Workspace || {};
            var self = this;
            $('.v5-tab-refresh,.btn-v5-refresh').on('click', function () { self.load(self.activePane(), 1); });
            $('.btn-v5-tab-refresh').on('click', function () { self.load($(this).closest('.tab-pane'), 1); });
            $('.btn-v5-search').on('click', function () { self.load($(this).closest('.tab-pane'), 1); });
            $('.v5-query').on('keydown', function (e) { if (e.keyCode === 13) { e.preventDefault(); self.load($(this).closest('.tab-pane'), 1); } });
            $('.btn-v5-add').on('click', function () { self.edit($(this).closest('.tab-pane'), {}); });
            $('.v5-import-file').off('change.v5import').on('change.v5import', function () {
                var $pane = $(this).closest('.tab-pane'), file = this.files && this.files[0];
                self.selectImportFile($pane, file || null);
            });
            $('.btn-v5-preview-import').off('click.v5import').on('click.v5import', function () {
                var $pane = $(this).closest('.tab-pane'), file = $pane.data('v5ImportFile');
                if (!file || !file.name || Number(file.size) <= 0) {
                    Toastr.warning('请先选择一个 .xlsx Excel 文件');
                    return;
                }
                self.previewImport($pane, file);
            });
            $('#v5-edit-modal').on('shown.bs.modal.v5front', function () {
                $(this).css('z-index', 1060);
                $('.modal-backdrop').last().css('z-index', 1055);
            });
            $('a[data-toggle="tab"]').on('shown.bs.tab', function (e) { self.load($($(e.target).attr('href')), 1); });
            this.load(this.activePane(), 1);
        },
        activePane: function () { return $('.v5-main-panel .tab-pane.active'); },
        tabConfig: function (resource) {
            var tabs = this.config.tabs || [];
            for (var i = 0; i < tabs.length; i++) if (tabs[i].resource === resource) return tabs[i];
            return {};
        },
        load: function ($pane, page) {
            if (!$pane || !$pane.length) return;
            var self = this, resource = $pane.data('resource'), cfg = this.tabConfig(resource), limit = 20;
            page = Math.max(1, page || 1); $pane.addClass('v5-loading');
            $.getJSON('shop/v5/workspace/data', {resource: resource, offset: (page - 1) * limit, limit: limit, q: $pane.find('.v5-query').val() || ''})
                .done(function (res) {
                    if (!res || !Array.isArray(res.rows) || typeof res.total === 'undefined') {
                        self.loadError($pane, cfg, (res && res.msg) || '数据返回异常，请刷新重试');
                        return;
                    }
                    self.render($pane, cfg, res, page, limit);
                })
                .fail(function (xhr) { self.loadError($pane, cfg, (xhr.responseJSON && xhr.responseJSON.msg) || '数据加载失败，请点击刷新重试'); })
                .always(function () { $pane.removeClass('v5-loading'); });
        },
        loadError: function ($pane, cfg, message) {
            $pane.find('tbody').html('<tr><td class="text-center v5-empty" colspan="' + (Object.keys(cfg.columns || {}).length + 1) + '">' + this.escape(message) + '</td></tr>');
            $pane.find('.v5-total').text('加载失败');
            this.pagination($pane, 1, 0);
            Toastr.error(message);
        },
        render: function ($pane, cfg, res, page, limit) {
            var self = this, columns = cfg.columns || {}, rows = res.rows || [], keys = Object.keys(columns), html = '<tr>';
            keys.forEach(function (key) { html += '<th>' + self.escape(columns[key]) + '</th>'; });
            if (cfg.editable || cfg.deletable || this.hasAction($pane.data('resource'))) html += '<th>操作</th>';
            html += '</tr>'; $pane.find('thead').html(html); html = '';
            rows.forEach(function (row) {
                html += '<tr>'; keys.forEach(function (key) { var field = (cfg.fields || {})[key] || {}; var cellClass = field.type === 'image' ? ' class="v5-image-cell"' : ''; html += '<td' + cellClass + ' title="' + self.escape(self.textValue(key, row[key], field)) + '">' + self.format(key, row[key], field) + '</td>'; });
                if (cfg.editable || cfg.deletable || self.hasAction($pane.data('resource'))) html += '<td class="v5-actions">' + self.actions($pane.data('resource'), cfg, row) + '</td>';
                html += '</tr>';
            });
            if (!rows.length) html = '<tr><td class="text-center v5-empty" colspan="' + (keys.length + 1) + '">暂无数据</td></tr>';
            $pane.find('tbody').html(html).off('click.v5').on('click.v5', '[data-v5-action]', function () {
                var action = $(this).data('v5-action'), id = $(this).data('id'), row = rows.filter(function (item) { return String(item[cfg.pk]) === String(id); })[0] || {};
                self.handle(action, $pane, row);
            });
            $pane.find('.v5-total').text('共 ' + (res.total || 0) + ' 条'); this.pagination($pane, page, Math.ceil((res.total || 0) / limit));
        },
        display: function (value) { if (value === null || typeof value === 'undefined' || value === '') return '-'; return typeof value === 'object' ? JSON.stringify(value) : String(value); },
        textValue: function (key, value, field) {
            if (value === null || typeof value === 'undefined' || value === '') return '-';
            var options = field && field.options ? field.options : null, optionKey = String(value);
            // PHP serializes numeric-keyed option maps as JSON arrays. Support
            // both array indexes and associative maps so boolean selects such
            // as 0/1 are rendered using their configured labels.
            if (options) {
                if (Object.prototype.hasOwnProperty.call(options, optionKey)) return String(options[optionKey]);
                if (Array.isArray(options) && /^\d+$/.test(optionKey) && options[Number(optionKey)] !== undefined) return String(options[Number(optionKey)]);
            }
            var keyLabels = this.enumLabels[key] || {}, common = this.enumLabels.common || {};
            if (Object.prototype.hasOwnProperty.call(keyLabels, optionKey)) return keyLabels[optionKey];
            if (Object.prototype.hasOwnProperty.call(common, optionKey)) return common[optionKey];
            if (this.timestampKeys[key] && /^\d{10}$/.test(optionKey) && Number(value) > 0) {
                var date = new Date(Number(value) * 1000);
                if (!isNaN(date.getTime())) {
                    var pad = function (n) { return String(n).padStart(2, '0'); };
                    return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate()) + ' ' + pad(date.getHours()) + ':' + pad(date.getMinutes()) + ':' + pad(date.getSeconds());
                }
            }
            return this.display(value);
        },
        format: function (key, value, field) {
            if (field && field.type === 'image') {
                if (value === null || typeof value === 'undefined' || value === '') return '<span class="v5-image-empty">暂无图片</span>';
                var src = this.escape(String(value));
                return '<img class="v5-goods-thumb" src="' + src + '" alt="商品图片" loading="lazy" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'inline\';"><span class="v5-image-empty" style="display:none;">图片不可用</span>';
            }
            var text = this.escape(this.textValue(key, value, field));
            if ((field && field.type === 'select') || /status|state|configured|gate|success|is_open|is_used|agent_visible|cancellable|selected|revalidation/.test(key)) return '<span class="v5-status">' + text + '</span>';
            return text;
        },
        importRowLabel: function (type, value) {
            var labels = {
                status: {valid: '有效', invalid: '错误', pending: '待处理'},
                action: {insert: '待新增', inserted: '已新增', update: '待更新', updated: '已更新', pending: '待处理'}
            };
            var key = value == null || value === '' ? '' : String(value);
            return (labels[type] && labels[type][key]) || (key || '-');
        },
        timestampKeys: { createtime: true, updatetime: true, expires_at: true, imported_at: true, effective_at: true, calculated_at: true, reviewed_at: true, submitted_at: true, paid_at: true, last_query_at: true, inventory_lock_at: true, shipped_at: true, delivered_at: true, processed_at: true, requested_at: true, success_at: true, started_at: true, finished_at: true, occurred_at: true, stock_updated_at: true, confirmed_at: true, validated_at: true, trade_checked_at: true, shippingtime: true, receivetime: true, sent_at: true, next_retry_at: true, jointime: true },
        enumLabels: {
            common: { normal: '上架', hidden: '下架', draft: '草稿', active: '生效', retired: '停用', published: '已发布', suspended: '已暂停', imported: '已导入', invalid: '预检失败', validated: '预检通过', valid: '有效', pending: '待处理', processing: '处理中', failed: '失败', resolved: '已解决', open: '待处理', completed: '已完成', cancelled: '已取消', expired: '已失效', scheduled: '已排程', preparing: '备货中', supplier_pending: '待供应商处理', shipped: '已发货', delivered: '已送达', paused: '已暂停', approved: '已通过', rejected: '已拒绝', unconfirmed: '未确认', confirmed: '已确认', yes: '是', no: '否', inserted: '新增', updated: '更新', insert: '新增', update: '更新' },
            sale_type: { normal: '普通商品', bundle: '固定食材包', service: '服务商品' },
            agent_visible: { '0': '否', '1': '是' },
            order_type: { normal: '普通订单', plan: '专属计划' },
            paystate: { '0': '待付款', '1': '已付款' },
            shippingstate: { '0': '未发货', '1': '已发货', '2': '已收货' },
            orderstate: { '0': '正常', '1': '已取消', '2': '已失效', '3': '已完成', '4': '退货退款中' },
            interface_type: { manual: '人工', api: 'API' },
            stock_status: { sufficient: '充足', low: '偏低', out: '缺货', unknown: '未知' },
            basis_type: { per_100g: '每100克', per_serving: '每份' },
            role: { primary: '主食材', component: '组成', alternative: '备选' },
            review_status: { pending: '待审核', approved: '已通过', rejected: '已拒绝', supplement_required: '需补充资料' },
            nutrition_status: { pending: '待校验', passed: '已通过', failed: '未通过', blocked: '已阻断' },
            trade_status: { pending: '待校验', passed: '已通过', failed: '未通过', blocked: '已阻断' },
            confirm_status: { unconfirmed: '未确认', confirmed: '已确认' },
            purchase_gate: { allowed: '允许购买', blocked: '禁止购买', pending: '待审核' },
            source_type: { normal: '普通订单', plan: '专属计划', plan_exception: '计划例外', service_plan: '专属计划' },
            client_type: { agent: 'Agent', supplier: '供应商', logistics: '物流', review: '专业审核' },
            direction: { inbound: '入站', outbound: '出站' },
            success: { '0': '失败', '1': '成功' },
            is_open: { '0': '关闭', '1': '开启' },
            is_used: { '1': '未使用', '2': '已使用' },
            delivery_slot_required: { '0': '否', '1': '是' },
            user_cancellable: { '0': '否', '1': '是' },
            requires_agent_revalidation: { '0': '否', '1': '是' },
            is_selected: { '0': '否', '1': '是' }
        },
        actions: function (resource, cfg, row) {
            var id = row[cfg.pk], out = [], state = row.__raw || row;
            // Goods are managed from one detail entry: product fields and its
            // SKU variants live together, so do not render a second pencil.
            if (cfg.editable && resource !== 'goods') out.push('<button class="btn btn-xs btn-primary" data-v5-action="edit" data-id="' + id + '"><i class="fa fa-pencil"></i></button>');
            if (resource === 'suppliers' && this.config.canManageSupplierApi) out.push('<button class="btn btn-xs btn-info" data-v5-action="supplierApi" data-id="'+id+'">API 与回调配置</button>');
            if (['orders_normal','orders_all','orders_pending','orders_unpaid','orders_shipping','orders_completed','orders_closed'].indexOf(resource)>=0 && (!state.order_type || state.order_type==='normal') && Number((row.__raw || row).paystate) === 1 && Number((row.__raw || row).orderstate) === 0 && Number((row.__raw || row).shippingstate) === 0) out.push('<button class="btn btn-xs btn-success" data-v5-action="ship" data-id="' + id + '">安排发货</button>');
            if (resource === 'supplier_applications' && state.review_status === 'pending') out.push('<button class="btn btn-xs btn-success" data-v5-action="approve" data-id="' + id + '">审核</button>');
            if (resource === 'supplier_orders' && ['pending','failed'].indexOf(state.push_status)>=0 && ['created','pushing'].indexOf(state.status)>=0) out.push('<button class="btn btn-xs btn-warning" data-v5-action="retry" data-id="' + id + '">重试</button>');
            if (/^exceptions/.test(resource) && ['open','processing'].indexOf(state.status)>=0) out.push('<button class="btn btn-xs btn-default" data-v5-action="resolve" data-id="' + id + '">关闭</button>');
            if (resource === 'skus') out.push('<button class="btn btn-xs btn-default" data-v5-action="stock" data-id="' + id + '">调库存</button>');
            if (resource === 'recommendations') out.push('<button class="btn btn-xs btn-default" data-v5-action="revalidate" data-id="' + id + '">重校验</button>');
            if (resource === 'batches_prepare') out.push('<button class="btn btn-xs btn-warning" data-v5-action="prepare" data-id="' + id + '">重试备货</button>');
            if (resource === 'policies' && state.status === 'draft') out.push('<button class="btn btn-xs btn-success" data-v5-action="publish" data-id="' + id + '">发布</button>');
            if (['aftersales','aftersales_pending'].indexOf(resource)>=0 && Number(state.status) === 1) out.push('<button class="btn btn-xs btn-success" data-v5-action="aftersale" data-id="' + id + '">审核</button>');
            if (resource === 'outbox_events' && (state.status === 'failed' || state.status === 'pending')) out.push('<button class="btn btn-xs btn-warning" data-v5-action="outbox" data-id="' + id + '">补偿</button>');
            if (resource === 'goods') out.push('<button class="btn btn-xs btn-primary" title="管理商品资料、规格与库存" data-v5-action="view" data-id="' + id + '"><i class="fa fa-pencil"></i> 管理</button>');
            if (resource === 'imports') out.push('<button class="btn btn-xs btn-default" title="查看导入预检详情" data-v5-action="view" data-id="' + id + '"><i class="fa fa-eye"></i></button>');
            if (['members','recommendations','purchase_lists','orders_normal','orders_all','orders_pending','orders_unpaid','orders_shipping','orders_completed','orders_closed','catalog_readiness'].indexOf(resource)>=0) out.push('<button class="btn btn-xs btn-info" data-v5-action="commerceDetail" data-id="'+this.escape(id)+'">查看详情</button>');
            if (cfg.deletable) out.push('<button class="btn btn-xs btn-danger" data-v5-action="remove" data-id="' + id + '"><i class="fa fa-trash"></i></button>');
            return out.join(' ');
        },
        hasAction: function (resource) { return ['orders_all','orders_pending','orders_unpaid','orders_shipping','orders_completed','orders_closed','aftersales_pending','suppliers','members','purchase_lists','catalog_readiness','orders_normal','goods','supplier_applications','supplier_orders','skus','recommendations','batches_prepare','policies','aftersales','outbox_events','imports'].indexOf(resource) >= 0 || /^exceptions/.test(resource); },
        handle: function (action, $pane, row) {
            var self = this, resource = $pane.data('resource');
            if (action === 'supplierApi') return this.supplierApiConfig($pane,row.id);
            if (action === 'commerceDetail') return $.getJSON('shop/v5/workspace/commerceDetail',{resource:resource,id:row.id}).done(function(res){if(Number(res.code)!==1){Toastr.error(res.msg||'读取失败');return;}self.showCommerceDetail(res.data||{});}).fail(function(){Toastr.error('详情读取失败');});
            if (action === 'ship') return this.prompt('物流公司', '', function (carrier) { self.prompt('运单号', '', function (tracking) { Fast.api.ajax({url:'shop/v5/workspace/shipOrder',type:'POST',data:{order_sn:row.order_sn,carrier:carrier,tracking_no:tracking,__token__:self.config.csrfToken}},function(data){self.config.csrfToken=data.__token__||self.config.csrfToken;self.load($pane,1);return false;},function(data){if(data&&data.__token__)self.config.csrfToken=data.__token__;return true;}); }); });
            if (action === 'edit') return this.edit($pane, row);
            if (action === 'remove') return Layer.confirm('确认删除该记录？', function (index) { Layer.close(index); self.post('remove', {resource:resource,id:row.id}, $pane); });
            if (action === 'approve') return Layer.confirm('请选择供应商合作申请的审核结果。', {btn:['通过','拒绝','要求补充资料','取消'],btn3:function(i){Layer.close(i);self.reviewSupplierApplication($pane,row,'supplement_required');}}, function(i){Layer.close(i);self.reviewSupplierApplication($pane,row,'approved');}, function(i){Layer.close(i);self.reviewSupplierApplication($pane,row,'rejected');});
            if (action === 'retry') return this.post('retrySupplier', {id:row.id}, $pane);
            if (action === 'resolve') return this.prompt('填写异常处理结论', '', function (value) { self.post('resolveException', {id:row.id,resolution:value}, $pane); });
            if (action === 'stock') return this.prompt('输入库存调整量（可为负数），并用“|”分隔原因，例如 10|盘点入库', '', function (value) { var p=String(value).split('|'); self.post('adjustStock',{sku_id:row.id,delta:p[0],reason:p.slice(1).join('|')},$pane); });
            if (action === 'revalidate') return this.post('revalidateRecommendation',{id:row.id},$pane);
            if (action === 'prepare') return this.post('retryBatch',{id:row.id},$pane);
            if (action === 'publish') return this.post('publishPolicy',{id:row.id},$pane);
            if (action === 'aftersale') return Layer.confirm('请选择售后审核结果。审核通过后退款仍需等待支付渠道确认。', {btn:['审核通过','拒绝申请','取消']}, function(i){Layer.close(i);self.prompt('通过原因或处理说明','',function(value){self.post('reviewAftersale',{id:row.id,decision:'approved',comment:value},$pane);});}, function(i){Layer.close(i);self.prompt('拒绝原因','',function(value){self.post('reviewAftersale',{id:row.id,decision:'rejected',comment:value},$pane);});});
            if (action === 'outbox') return this.post('retryOutbox',{id:row.id},$pane);
            if (action === 'view') {
                if (resource === 'goods') {
                    return $.getJSON('shop/v5/workspace/goodsDetail', {id: row.id}).done(function (res) {
                        if (Number(res.code) !== 1) { Toastr.error(res.msg || '商品详情加载失败'); return; }
                        self.showGoodsDetail(res.data || {}, $pane, row);
                    }).fail(function () { Toastr.error('商品详情加载失败'); });
                }
                return $.getJSON('shop/v5/workspace/importDetail', {id: row.id}).done(function (res) {
                    if (Number(res.code) !== 1) { Toastr.error(res.msg || '导入详情加载失败'); return; }
                    self.showImportResult(res.data || {}, $pane);
                }).fail(function () { Toastr.error('导入详情加载失败'); });
            }
        },
        reviewSupplierApplication: function ($pane, row, decision) {
            var self=this;
            this.prompt('审核意见', '', function(comment){self.post('reviewApplication',{id:row.id,decision:decision,comment:comment},$pane);});
        },
        detailLabels: {
            user:'用户资料',addresses:'收货地址',cart:'购物车',purchases:'采购清单',orders:'关联订单',credential_note:'账号说明',
            package:'餐单采购来源',requirements:'食材需求',issues:'采购问题',purchase_lists:'采购清单',purchase_items:'需求匹配',
            order:'订单信息',sources:'采购来源',state:'交易状态',items:'商品明细',inventory:'库存预占记录',product:'商品资料',notice:'资料说明',
            id:'编号',username:'商城账号',nickname:'昵称',mobile:'电话',jointime:'创建时间',status:'状态',account_source:'账号来源',linked_account:'小程序账号',binding_status:'关联状态',wechat_status:'微信绑定',
            package_sn:'推荐包号',user_id:'用户ID',user_ref:'来源账号',menu_version_ref:'餐单版本',meal_date:'就餐日期',current_version:'当前版本',nutrition_status:'营养校验',trade_status:'交易校验',confirm_status:'用户确认',expires_at:'有效截止',last_issue_code:'最近问题',source_evidence:'来源凭据',expired:'是否过期',generation_notice:'生成依据',
            ingredient_code:'食材编码',required_value:'需求数量',required_unit:'需求单位',is_optional:'是否可选',purchase_list_sn:'采购单号',source_ref:'来源编号',source_type:'来源类型',source_version:'来源版本',match_status:'匹配状态',selected_match_id:'选中匹配编号',pantry_value:'库存数量',pantry_unit:'已有量单位',net_required_value:'采购净需求',net_required_unit:'净需求单位',
            expressname:'物流公司',expressno:'运单号',shippingtime:'发货时间',receivetime:'收货时间',realprice:'商品实付金额',salestate:'售后状态',title:'商品名称',order_sn:'订单号',saleamount:'应付金额(元)',payamount:'实付金额(元)',goodsprice:'商品金额(元)',shippingfee:'运费(元)',discount:'优惠(元)',paystate:'支付状态',orderstate:'订单状态',shippingstate:'配送状态',receiver:'收货人',address:'收货地址',createtime:'创建时间',business_status:'业务状态',payment_status:'支付状态',fulfillment_status:'履约状态',exception_status:'异常状态',request_id:'请求编号',
            sku_id:'SKU ID',goods_sku_id:'SKU ID',goods_id:'商品ID',nums:'数量',quantity:'数量',product_name:'商品',sku_name:'规格',unit_price_cent:'单价(分)',line_amount_cent:'金额(分)',valid:'是否可售',invalid_reason:'失效原因',selected:'已选中',name:'姓名或名称',phone:'电话',region:'地区',detail:'详细地址',is_default:'默认地址',version:'版本',
            mapping_status:'采购映射',data_issues:'待补资料',nutrition_facts:'营养资料',ingredients:'已审核食材关联',allergen_codes:'已记录过敏原编码',allergen_information_status:'过敏原资料状态',purchase_ready:'是否有有效采购映射',data_completeness:'资料完整度',net_content:'净含量',value:'数值',unit:'单位',code:'问题代码',message:'说明',issue_code:'问题代码'
        },
        showCommerceDetail: function(data) {
            var self=this;
            function render(value,key) {
                if(value===null||typeof value==='undefined') return '<span class="text-muted">未提供</span>';
                if(Array.isArray(value)) {
                    if(!value.length)return '<span class="text-muted">暂无记录</span>';
                    if(typeof value[0]!=='object')return self.escape(value.join('、'));
                    var keys=[];value.forEach(function(r){Object.keys(r).forEach(function(k){if(keys.indexOf(k)<0)keys.push(k);});});
                    var h='<div class="table-responsive"><table class="table table-striped table-bordered"><thead><tr>';
                    keys.forEach(function(k){h+='<th>'+self.escape(self.detailLabels[k]||k)+'</th>';});h+='</tr></thead><tbody>';
                    value.forEach(function(r){h+='<tr>';keys.forEach(function(k){h+='<td>'+render(r[k],k)+'</td>';});h+='</tr>';});return h+'</tbody></table></div>';
                }
                if(typeof value==='object'){var h='<table class="table table-bordered">';Object.keys(value).forEach(function(k){h+='<tr><th style="width:170px">'+self.escape(self.detailLabels[k]||k)+'</th><td>'+render(value[k],k)+'</td></tr>';});return h+'</table>';}
                if(typeof value==='boolean')return value?'是':'否';
                var labels={not_recorded:'未录入，不能视为无过敏原',recorded_unreviewed:'已录入来源，需核实完整性',manual:'直接加购',purchase_list:'餐单采购清单',recommendation_package:'餐单推荐包',cart:'购物车',created:'已创建，未完成支付',unpaid:'未支付',paid:'已支付'};
                return self.escape(labels[value]||self.textValue(key,value,{}));
            }
            var html='<div style="padding:20px;overflow-wrap:anywhere">';Object.keys(data).forEach(function(k){html+='<h4>'+self.escape(self.detailLabels[k]||k)+'</h4>'+render(data[k],k);});html+='</div>';
            Layer.open({type:1,title:'业务查看详情',area:['92%','88%'],content:html});
        },
        showGoodsDetail: function (result, $pane, sourceRow) {
            var self = this, goods = result.goods || {}, skus = result.skus || [], supplierItems = result.supplier_items || [], rows = '', supplierRows = '';
            var image = goods.image ? '<img class="v5-detail-image" src="' + self.escape(goods.image) + '" alt="商品图片">' : '<span class="text-muted">暂无图片</span>';
            skus.forEach(function (sku) {
                rows += '<tr><td>' + self.escape(sku.sku_name || '-') + '</td><td>' + self.escape(sku.specification || '-') + '</td><td>¥' + self.escape(sku.price || '-') + '</td><td>' + self.escape(sku.stocks) + '</td><td>' + self.escape(sku.reserved_stock) + '</td><td>' + self.escape(sku.safety_stock) + '</td><td>' + self.escape(sku.net_content || '-') + '</td><td class="v5-actions"><button class="btn btn-xs btn-primary v5-goods-sku-edit" data-id="' + self.escape(sku.id) + '"><i class="fa fa-pencil"></i> 编辑</button> <button class="btn btn-xs btn-default v5-goods-sku-stock" data-id="' + self.escape(sku.id) + '">调库存</button></td></tr>';
            });
            if (!rows) rows = '<tr><td colspan="8" class="text-center text-muted">暂无SKU，请先导入或新增规格</td></tr>';
            supplierItems.forEach(function (item) {
                supplierRows += '<tr><td>' + self.escape(item.sku_name || '-') + '</td><td>' + self.escape(item.supplier_name || '-') + '</td><td>' + self.escape(item.supplier_goods_code || '-') + '</td><td>' + self.escape(item.supplier_sku_code || '-') + '</td><td>¥' + self.escape(item.supply_price || '-') + '</td><td>' + self.escape(item.stock_quantity) + '</td><td>' + self.escape(item.minimum_order_quantity) + '</td><td>' + self.escape(item.delivery_days) + ' 天</td><td>' + self.escape(item.status || '-') + '</td><td class="v5-note-cell" title="' + self.escape(item.source_note || '-') + '">' + self.escape(item.source_note || '-') + '</td></tr>';
            });
            if (!supplierRows) supplierRows = '<tr><td colspan="10" class="text-center text-muted">暂无供应商供货信息。请通过“供应商导入记录”导入，或在“供应商商品”中维护。</td></tr>';
            var html = '<div class="row v5-goods-summary"><div class="col-sm-2 text-center">' + image + '</div><div class="col-sm-10"><h4>' + self.escape(goods.title || '-') + '</h4><p class="text-muted">货号：' + self.escape(goods.goods_sn || '-') + '　分类：' + self.escape(goods.category || '-') + '</p><p>销售类型：' + self.escape(goods.sale_type || '-') + '　接口可见：' + self.escape(goods.agent_visible || '-') + '　状态：' + self.escape(goods.status || '-') + '</p><p>售价：' + self.escape(goods.price_range || '-') + '　可售SKU：' + self.escape(goods.available_sku_count || 0) + '　总库存：' + self.escape(goods.total_stocks || 0) + '</p></div></div><hr><div class="clearfix" style="margin-bottom:8px"><strong>规格与库存</strong><button type="button" class="btn btn-xs btn-success pull-right v5-add-goods-sku"><i class="fa fa-plus"></i> 新增SKU</button></div><div class="table-responsive"><table class="table table-bordered table-striped"><thead><tr><th>SKU名称</th><th>规格</th><th>售价</th><th>实物库存</th><th>占用库存</th><th>安全库存</th><th>净含量</th><th>操作</th></tr></thead><tbody>' + rows + '</tbody></table></div><hr><div class="clearfix" style="margin-bottom:8px"><strong>供应商供货信息</strong><span class="text-muted small pull-right">供应商供货信息由导入自动同步</span></div><div class="table-responsive"><table class="table table-bordered table-striped v5-supplier-items"><thead><tr><th>平台SKU</th><th>供应商</th><th>供应商商品编码</th><th>供应商SKU编码</th><th>供货价</th><th>可供库存</th><th>最小起订量</th><th>交付天数</th><th>状态</th><th>备注</th></tr></thead><tbody>' + supplierRows + '</tbody></table></div>';
            $('#v5-goods-detail-content').html(html).data({goodsId: goods.id, skus: skus, pane: $pane, sourceRow: result.edit_values || sourceRow || {}});
            $('#v5-goods-detail-modal').modal('show');
            $('.btn-v5-edit-goods').off('click.v5').on('click.v5', function () {
                var meta = $('#v5-goods-detail-content').data();
                $('#v5-goods-detail-modal').modal('hide');
                self.edit(meta.pane, meta.sourceRow || {id: meta.goodsId});
            });
            $('#v5-goods-detail-content').off('click.v5').on('click.v5', '.v5-goods-sku-stock', function () { var sku = skus.filter(function (x) { return String(x.id) === String($(this).data('id')); }.bind(this))[0] || {}; self.prompt('输入库存调整量（可为负数），并用“|”分隔原因，例如 10|盘点入库', '', function (value) { var p=String(value).split('|'); self.post('adjustStock',{sku_id:sku.id,delta:p[0],reason:p.slice(1).join('|')},$pane,function(){ self.reloadGoodsDetail(goods.id,$pane); }); }); }).on('click.v5', '.v5-goods-sku-edit', function () { var sku = skus.filter(function (x) { return String(x.id) === String($(this).data('id')); }.bind(this))[0] || {}; self.editSkuFromDetail(sku, goods.id, $pane); });
            $('#v5-goods-detail-content').on('click.v5', '.v5-add-goods-sku', function () { self.addSkuFromDetail(goods, $pane); });
        },
        addSkuFromDetail: function (goods, $pane) {
            var self=this;
            $.getJSON('shop/v5/workspace/skuOptions').done(function(res){
                if(Number(res.code)!==1){Toastr.error(res.msg||'规格加载失败');return;}
                var data=res.data||{}, specs=data.specs||[], values=data.values||[], specHtml='', valueHtml='';
                specs.forEach(function(s){specHtml+='<option value="'+self.escape(s.id)+'">'+self.escape(s.name)+'</option>';});
                values.forEach(function(v){valueHtml+='<option value="'+self.escape(v.value)+'" data-spec="'+self.escape(v.spec_id)+'">'+self.escape(v.value)+'</option>';});
                var html='<div class="form-group"><label class="col-sm-3 control-label">商品</label><div class="col-sm-8"><input class="form-control" value="'+self.escape(goods.title||'')+'" readonly></div></div><div class="form-group"><label class="col-sm-3 control-label">规格名称 *</label><div class="col-sm-8"><select class="form-control" name="spec_id">'+specHtml+'</select></div></div><div class="form-group"><label class="col-sm-3 control-label">规格值 *</label><div class="col-sm-8"><select class="form-control" name="sku_id">'+valueHtml+'</select></div></div><div class="form-group"><label class="col-sm-3 control-label">售价 *</label><div class="col-sm-8"><input class="form-control" name="price" type="number" min="0" step="0.01" required></div></div><div class="form-group"><label class="col-sm-3 control-label">市场价</label><div class="col-sm-8"><input class="form-control" name="marketprice" type="number" min="0" step="0.01"></div></div><div class="form-group"><label class="col-sm-3 control-label">实物库存 *</label><div class="col-sm-8"><input class="form-control" name="stocks" type="number" min="0" value="0"></div></div><div class="form-group"><label class="col-sm-3 control-label">安全库存</label><div class="col-sm-8"><input class="form-control" name="safety_stock" type="number" min="0" value="0"></div></div><div class="form-group"><label class="col-sm-3 control-label">净含量 *</label><div class="col-sm-8"><input class="form-control" name="net_content_value" type="number" min="0" step="0.01" required><select class="form-control" name="net_content_unit" style="margin-top:6px"><option value="g">克</option><option value="kg">千克</option><option value="ml">毫升</option><option value="piece">件</option><option value="pack">包</option></select></div></div>';
                $('#v5-edit-form').html(html).data({resource:'skus',id:0,pane:$pane,goodsId:goods.id,goods:goods}); $('#v5-edit-modal').addClass('v5-front-modal').modal('show');
                $('.btn-v5-save').off('click').on('click',function(){var formData={},meta=$('#v5-edit-form').data();$('#v5-edit-form').serializeArray().forEach(function(x){formData[x.name]=x.value;});if(!formData.sku_id||formData.price===''||formData.stocks===''||formData.net_content_value===''){Toastr.error('规格值、售价、实物库存和净含量不能为空');return;}formData.goods_id=meta.goodsId;self.post('save',{resource:'skus',id:0,row:formData},meta.pane,function(){$('#v5-edit-modal').modal('hide');self.reloadGoodsDetail(meta.goodsId,meta.pane);});});
                $('#v5-edit-form select[name="spec_id"]').on('change',function(){var id=String(this.value), html='';values.filter(function(v){return String(v.spec_id)===id;}).forEach(function(v){html+='<option value="'+self.escape(v.value)+'">'+self.escape(v.value)+'</option>';});$('#v5-edit-form select[name="sku_id"]').html(html);}).trigger('change');
            }).fail(function(){Toastr.error('规格加载失败');});
        },
        reloadGoodsDetail: function (goodsId, $pane) {
            var self = this;
            $.getJSON('shop/v5/workspace/goodsDetail', {id: goodsId}).done(function (res) { if (Number(res.code) === 1) self.showGoodsDetail(res.data || {}, $pane); });
        },
        editSkuFromDetail: function (sku, goodsId, $pane) {
            var self = this, fields = [{key:'sku_name', title:'SKU名称', value:sku.sku_name || '', type:'text', readonly:true}, {key:'specification', title:'规格', value:sku.specification || '', type:'text', readonly:true}, {key:'price', title:'售价', value:sku.price == null ? '' : sku.price, type:'number'}, {key:'marketprice', title:'市场价', value:sku.marketprice == null ? '' : sku.marketprice, type:'number'}, {key:'stocks', title:'实物库存', value:sku.stocks || 0, type:'number'}, {key:'safety_stock', title:'安全库存', value:sku.safety_stock || 0, type:'number'}, {key:'net_content_value', title:'净含量', value:sku.net_content_value == null ? '' : sku.net_content_value, type:'number'}], html='';
            fields.forEach(function (f) { html += '<div class="form-group"><label class="col-sm-3 control-label">' + self.escape(f.title) + '</label><div class="col-sm-8"><input class="form-control" name="' + f.key + '" type="' + f.type + '" ' + (f.type === 'number' ? 'step="any" ' : '') + 'value="' + self.escape(f.value) + '" ' + (f.readonly ? 'readonly' : '') + '></div></div>'; });
            $('#v5-edit-form').html(html).data({resource:'skus', id:sku.id, pane:$pane, goodsId:goodsId, sku:sku});
            $('#v5-edit-form').off('click.v5upload change.v5upload').on('click.v5upload','.v5-select-image',function(){ $(this).siblings('.v5-image-file').trigger('click'); }).on('change.v5upload','.v5-image-file',function(){ var file=this.files&&this.files[0], $box=$(this).closest('.v5-image-upload'); if(file) self.uploadImage(file,$box); });
            $('#v5-edit-modal').addClass('v5-front-modal').modal('show');
            $('.btn-v5-save').off('click').on('click', function () { var data={}, meta=$('#v5-edit-form').data(); $('#v5-edit-form').serializeArray().forEach(function(x){data[x.name]=x.value;}); data.goods_id=meta.goodsId; data.sku_code=meta.sku.sku_code || ''; data.sku_id=meta.sku.specification || ''; data.net_content_unit=meta.sku.net_content_unit || 'g'; self.post('save',{resource:'skus',id:meta.id,row:data},meta.pane,function(){ $('#v5-edit-modal').modal('hide'); self.reloadGoodsDetail(meta.goodsId,meta.pane); }); });
        },
        edit: function ($pane, row) {
            var cfg = this.tabConfig($pane.data('resource')), fields = cfg.fields || {}, html = '', self = this, editRow = row.__raw || row;
            Object.keys(fields).forEach(function (key) {
                var f=fields[key], value=editRow[key] == null?'':editRow[key], input='';
                if ($pane.data('resource') === 'skus' && key === 'image') return;
                if (['valid_from','valid_to'].indexOf(key)>=0 && /^\d+$/.test(String(value))) value=Number(value)>0?self.textValue('expires_at',value,{}):'';
                if (f.type === 'select') { input='<select class="form-control" name="'+key+'">'; Object.keys(f.options||{}).forEach(function(k){input+='<option value="'+self.escape(k)+'" '+(String(value)===String(k)?'selected':'')+'>'+self.escape(f.options[k])+'</option>';}); input+='</select>'; }
                else if (f.type === 'textarea') input='<textarea class="form-control" rows="4" name="'+key+'">'+self.escape(value)+'</textarea>';
                else if (f.type === 'image') input='<div class="v5-image-upload"><input class="form-control v5-image-value" type="hidden" name="'+key+'" value="'+self.escape(value)+'"><input class="v5-image-file" type="file" accept="image/jpeg,image/png,image/gif,image/webp" data-target="'+key+'"><button type="button" class="btn btn-default v5-select-image"><i class="fa fa-upload"></i> 选择图片</button><span class="v5-upload-status text-muted">未选择文件</span><div class="v5-image-preview">'+(value?'<img src="'+self.escape(value)+'" alt="图片预览">':'')+'</div></div>';
                else input='<input class="form-control" type="'+(f.type==='password'?'password':(f.type==='number'?'number':'text'))+'" '+(f.type==='number'?'step="any" ':'')+'name="'+key+'" value="'+self.escape(value)+'">';
                if ($pane.data('resource')==='suppliers' && editRow.id && key==='supplier_code') input=input.replace('<input ','<input readonly ');
                html+='<div class="form-group"><label class="col-sm-3 control-label">'+self.escape(f.title)+(f.required?' *':'')+'</label><div class="col-sm-8">'+input+'</div></div>';
            });
            $('#v5-edit-form').html(html).data({resource:$pane.data('resource'),id:editRow[cfg.pk]||0,pane:$pane,version:editRow.version||editRow.updatetime||''});
            $('#v5-edit-form').off('click.v5upload change.v5upload').on('click.v5upload','.v5-select-image',function(){ $(this).siblings('.v5-image-file').trigger('click'); }).on('change.v5upload','.v5-image-file',function(){ var file=this.files&&this.files[0], $box=$(this).closest('.v5-image-upload'); if(file) self.uploadImage(file,$box); });
            $('#v5-edit-modal').addClass('v5-front-modal').modal('show');
            $('.btn-v5-save').off('click').on('click', function(){ var data={}, meta=$('#v5-edit-form').data(); $('#v5-edit-form').serializeArray().forEach(function(x){data[x.name]=x.value;}); self.post('save',{resource:meta.resource,id:meta.id,row:data,version:meta.version},meta.pane,function(){$('#v5-edit-modal').modal('hide');}); });
        },
        supplierApiConfig: function ($pane, id) {
            var self=this;
            Fast.api.ajax({url:'shop/v5/workspace/supplierApiConfig',type:'GET',data:{id:id}},function(data){self.showSupplierApiConfig(data,$pane);return false;});
        },
        showSupplierApiConfig: function (data, $pane) {
            var self=this, s=data.supplier, out=data.outbound, cb=data.callback, protocol=data.protocol;
            if(data.__token__)self.config.csrfToken=data.__token__;
            function field(label,name,value,type,help){return '<div class="form-group"><label class="control-label" for="v5-api-'+name+'">'+self.escape(label)+'</label>'+(type==='textarea'?'<textarea class="form-control" rows="3" id="v5-api-'+name+'" name="'+name+'">'+self.escape(value)+'</textarea>':'<input class="form-control" id="v5-api-'+name+'" type="'+type+'" name="'+name+'" value="'+self.escape(value)+'" autocomplete="'+(type==='password'?'new-password':'off')+'">')+(help?'<p class="help-block">'+self.escape(help)+'</p>':'')+'</div>';}
            var html='<div class="alert alert-info">'+self.escape(data.notice)+'</div>';
            html+='<p><strong>'+self.escape(s.name)+'</strong> · '+self.escape(s.supplier_code)+'　当前对接：'+self.escape(s.interface_type==='manual'?'人工':'API')+'　回调：'+self.escape(cb.status==='normal'?'已启用':cb.status==='hidden'?'已停用 / 草稿':'未配置')+'</p>';
            if(cb.conflict)html+='<div class="alert alert-danger">供应商编码已被其他类型调用方占用，请先在系统配置中核查。此处不会覆盖该调用方。</div>';
            html+='<form id="v5-supplier-api-form" autocomplete="off"><h4>商城向供应商推单</h4>';
            html+=field('供应商下单接口地址','endpoint_url',out.endpoint_url,'url','填写供应商真实地址；建议HTTPS。保存不会测试接口或发送订单。');
            html+=field('推单共享签名密钥','outbound_password','','password',(out.secret_configured?'已配置。':'未配置。')+'留空保留原值，新密钥16至256字符。使用商城HMAC-SHA256协议；其他协议需先适配。');
            html+='<hr><h4>供应商回调商城</h4><p>回调调用方编号：<code>'+self.escape(cb.client_id)+'</code>（固定对应供应商编码）</p><p>回调接口：<code>POST '+self.escape(cb.path)+'</code></p><p class="help-block">请结合商城部署前缀和正式域名确认完整外网地址；签名使用实际外部请求路径。</p>';
            html+=field('回调共享签名密钥','callback_password','','password',(cb.secret_configured?'已配置。':'未配置。')+'留空保留原值，新建调用方仅保存为停用草稿，不接受真实回调。');
            html+=field('回调来源IP（每行一个）','allowed_ips',cb.allowed_ips.join('\n'),'textarea','填写供应商真实出口IPv4或IPv6，不支持网段。留空表示尚未设置来源IP限制。');
            html+=field('允许时间偏差（秒）','clock_skew_seconds',cb.clock_skew_seconds,'number','范围30至900秒，默认300秒。');
            html+='</form><hr><h4>尚缺的配置</h4><ul>'+(data.missing_configuration.length?data.missing_configuration.map(function(v){return '<li>'+self.escape(v)+'</li>';}).join(''):'<li>上述配置已填写；供应商协议和真实资料仍需核验，尚不代表联调通过。</li>')+'</ul>';
            html+='<h4>需要供应商提供的真实资料</h4><ul>'+data.materials.map(function(v){return '<li>'+self.escape(v)+'</li>';}).join('')+'</ul>';
            html+='<details><summary>查看商城现有签名与回调协议</summary><p>'+self.escape(protocol.canonical)+'</p><p>请求头：'+self.escape(protocol.headers.join('、'))+'</p><p>推单 X-Client-Id：shop；回调 X-Client-Id：'+self.escape(cb.client_id)+'</p><p>回调必填：'+self.escape(protocol.callback_required_fields.join('、'))+'</p><p>回调状态：'+self.escape(protocol.callback_statuses.join('、'))+'</p><p>'+self.escape(protocol.nonce)+'</p><p>'+self.escape(protocol.notice)+'</p></details>';
            $('#v5-supplier-api-content').html(html);
            $('#v5-supplier-api-form').off('submit.v5api').on('submit.v5api',function(e){e.preventDefault();});
            $('.btn-v5-save-supplier-api').prop('disabled',cb.conflict).off('click.v5api').on('click.v5api',function(){
                var $button=$(this), row={supplier_version:s.version,callback_version:cb.version};
                $('#v5-supplier-api-form').serializeArray().forEach(function(x){row[x.name]=x.value;});
                $button.prop('disabled',true);
                Fast.api.ajax({url:'shop/v5/workspace/saveSupplierApiConfig',type:'POST',data:{id:s.id,row:row,__token__:self.config.csrfToken}},function(result,ret){if(result.__token__)self.config.csrfToken=result.__token__;self.showSupplierApiConfig(result,$pane);self.load($pane,1);Toastr.success(ret.msg);return false;},function(result){if(result&&result.__token__)self.config.csrfToken=result.__token__;return true;}).always(function(){$button.prop('disabled',cb.conflict);});
            });
            $('#v5-supplier-api-modal').modal('show');
        },
        uploadImage: function (file, $box) {
            var self=this, form=new FormData(), $status=$box.find('.v5-upload-status'), $value=$box.find('.v5-image-value');
            form.append('file', file); $status.text('正在上传...'); $box.find('.v5-select-image').prop('disabled', true);
            $.ajax({url:Fast.api.fixurl((Config.upload&&Config.upload.uploadurl)||'ajax/upload'),type:'POST',data:form,processData:false,contentType:false,dataType:'json'}).done(function(res){
                if(Number(res.code)!==1 || !res.data || !res.data.url){ $status.text('上传失败'); Toastr.error((res&&res.msg)||'图片上传失败'); return; }
                var url=Config.upload&&Config.upload.fullmode&&res.data.fullurl?res.data.fullurl:res.data.url; $value.val(url).trigger('change'); $status.text('上传成功'); $box.find('.v5-image-preview').html('<img src="'+self.escape(url)+'" alt="图片预览">');
            }).fail(function(xhr){ $status.text('上传失败'); Toastr.error((xhr.responseJSON&&xhr.responseJSON.msg)||'图片上传失败，请检查文件大小和格式'); }).always(function(){ $box.find('.v5-select-image').prop('disabled', false); });
        },
        selectImportFile: function ($pane, file) {
            var valid = file && /\.xlsx$/i.test(file.name) && Number(file.size) > 0 && Number(file.size) <= 12 * 1024 * 1024;
            $pane.data('v5ImportFile', valid ? file : null);
            $pane.find('.btn-v5-preview-import').prop('disabled', !valid);
            $pane.find('.v5-import-filename').text(valid ? file.name : '尚未选择文件');
            if (file && !valid) Toastr.warning('仅支持不超过 12 MB 的 .xlsx 文件');
        },
        previewImport: function ($pane, file) {
            var self = this;
            if (!file || !file.name || Number(file.size) <= 0) {
                Toastr.warning('请先选择一个 .xlsx Excel 文件');
                return;
            }
            var form = new FormData(); form.append('file', file, file.name);
            var $previewButton = $pane.find('.btn-v5-preview-import').prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> 正在预检');
            $pane.find('.v5-import-picker').addClass('disabled');
            $pane.find('.v5-import-file').prop('disabled', true);
            $.ajax({url:'shop/v5/workspace/previewImport',type:'POST',data:form,processData:false,contentType:false,dataType:'json'})
                .done(function(res){if(Number(res.code)!==1){Toastr.error(res.msg||'预检请求失败，请刷新页面后重试');return;}self.showImportResult(res.data||{},$pane);self.load($pane,1);})
                .fail(function(xhr){Toastr.error((xhr.responseJSON&&xhr.responseJSON.msg)||'文件上传或预检失败，请确认使用新版 .xlsx 模板，图片已直接插入“商品图片”列');})
                .always(function(){
                    $pane.find('.v5-import-picker').removeClass('disabled');
                    $pane.find('.v5-import-file').prop('disabled', false).val('');
                    $pane.removeData('v5ImportFile');
                    $pane.find('.v5-import-filename').text('尚未选择文件');
                    $previewButton.prop('disabled', true).html('<i class="fa fa-check-circle"></i> 开始预检');
                });
        },
        showImportResult: function (result, $pane) {
            var self=this, ok=Number(result.invalid_rows||0)===0, imported=result.status==='imported', summary=result.summary||{}, blocks=[];
            Object.keys(summary).forEach(function(name){var item=summary[name]||{};blocks.push('<span class="label label-default">'+self.escape(name)+' '+Number(item.total||0)+' 行</span>');});
            var notice=imported?'该文件已完成导入。':(ok?'预检通过，可以确认写入业务数据。':'预检发现错误，请按行修正Excel后重新上传。');
            $('.v5-import-summary').html('<div class="alert '+(ok?'alert-success':'alert-danger')+'"><strong>'+self.escape(notice)+'</strong><br>总计 '+Number(result.total_rows||0)+' 行，有效 '+Number(result.valid_rows||0)+' 行，错误 '+Number(result.invalid_rows||0)+' 行</div><div>'+blocks.join(' ')+'</div>');
            if (result.detail_warning) {
                $('.v5-import-summary').append('<div class="alert alert-warning"><strong>'+self.escape(result.detail_warning)+'</strong></div>');
            }
            var html='', errors=result.errors||[], detailRows=result.rows||[];
            if(detailRows.length){
                $('.v5-import-errors thead').html('<tr><th>工作表</th><th>行号</th><th>业务编码</th><th>状态</th><th>处理结果</th><th>错误信息</th></tr>');
                detailRows.forEach(function(row){html+='<tr><td>'+self.escape(row.sheet_name)+'</td><td>'+self.escape(row.row_no)+'</td><td>'+self.escape(row.business_key||'-')+'</td><td>'+self.escape(self.importRowLabel('status', row.status))+'</td><td>'+self.escape(self.importRowLabel('action', row.action))+'</td><td>'+self.escape(row.error_message||'-')+'</td></tr>';});
            }else{
                $('.v5-import-errors thead').html('<tr><th>工作表</th><th>行号</th><th>业务编码</th><th>错误</th></tr>');
                errors.forEach(function(row){html+='<tr><td>'+self.escape(row.sheet_name)+'</td><td>'+self.escape(row.row_no)+'</td><td>'+self.escape(row.business_key||'-')+'</td><td>'+self.escape(row.error_message)+'</td></tr>';});
            }
            if(!html)html='<tr><td colspan="'+(detailRows.length?6:4)+'" class="text-center text-muted">'+self.escape(result.detail_warning||'没有明细')+'</td></tr>';
            $('.v5-import-errors tbody').html(html);
            $('.btn-v5-confirm-import').prop('disabled',!ok||imported).data({batchId:result.batch_id,pane:$pane}).off('click').on('click',function(){var meta=$(this).data();$(this).prop('disabled',true);self.post('confirmImport',{batch_id:meta.batchId},meta.pane,function(){self.load(meta.pane,1);$('#v5-import-modal').modal('hide');});});
            $('#v5-import-modal').modal('show');
        },
        post: function (action, data, $pane, done) { var self=this; if(['save','remove','adjustStock','reviewApplication','reviewAftersale','retrySupplier','resolveException','retryOutbox','retryBatch'].indexOf(action)>=0||(action==='save'&&['ingredient_maps','nutrition','components'].indexOf(data.resource)>=0))data.__token__=self.config.csrfToken; Fast.api.ajax({url:'shop/v5/workspace/'+action,type:'POST',data:data},function(result,ret){if(result&&result.__token__)self.config.csrfToken=result.__token__;if(['save','remove','adjustStock','reviewApplication','reviewAftersale','retrySupplier','resolveException','retryOutbox','retryBatch'].indexOf(action)>=0&&!(result&&result.status==='failed'&&result.failure_message))Toastr.success(ret.msg);if(result&&result.status==='failed'&&result.failure_message)Toastr.warning('退款提交失败，尚未退款成功：'+result.failure_message);if(done)done();self.load($pane,1);return false;},function(result){if(result&&result.__token__)self.config.csrfToken=result.__token__;return true;}); },
        prompt: function (title, value, callback) { Layer.prompt({title:title,value:value,formType:2}, function(v,i){if(!$.trim(v)){Toastr.error('内容不能为空');return;}Layer.close(i);callback(v);}); },
        pagination: function ($pane, page, pages) { var self=this, html=''; if(pages<=1){$pane.find('.v5-pagination').empty();return;} for(var i=Math.max(1,page-2);i<=Math.min(pages,page+2);i++) html+='<li class="'+(i===page?'active':'')+'"><a href="#" data-page="'+i+'">'+i+'</a></li>'; $pane.find('.v5-pagination').html(html).off('click').on('click','a',function(e){e.preventDefault();self.load($pane,$(this).data('page'));}); },
        escape: function (value) { return $('<div>').text(value == null ? '' : String(value)).html(); }
    };
    return Controller;
});
