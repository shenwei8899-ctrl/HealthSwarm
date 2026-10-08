define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/supplier_sku/index' + location.search,
                    add_url: 'shop/supplier_sku/add',
                    edit_url: 'shop/supplier_sku/edit',
                    del_url: 'shop/supplier_sku/del',
                    multi_url: 'shop/supplier_sku/multi',
                    import_url: 'shop/supplier_sku/import',
                    table: 'shop_supplier_sku',
                }
            });

            var table = $("#table");

            // 初始化表格
            table.bootstrapTable({
                url: $.fn.bootstrapTable.defaults.extend.index_url,
                pk: 'id',
                sortName: 'id',
                fixedColumns: true,
                fixedRightNumber: 1,
                columns: [
                    [
                        {checkbox: true},
                        {field: 'id', title: __('Id')},
                        {field: 'supplier_id', title: __('Supplier_id')},
                        {field: 'goods_id', title: __('Goods_id')},
                        {field: 'goods_sku_id', title: __('Goods_sku_id')},
                        {field: 'supplier_goods_code', title: __('Supplier_goods_code'), operate: 'LIKE'},
                        {field: 'supplier_sku_code', title: __('Supplier_sku_code'), operate: 'LIKE'},
                        {field: 'supply_price', title: __('Supply_price'), operate:'BETWEEN'},
                        {field: 'min_order_qty', title: __('Min_order_qty')},
                        {field: 'delivery_days', title: __('Delivery_days')},
                        {field: 'fulfillment_mode', title: __('Fulfillment_mode'), searchList: {"PLATFORM_WAREHOUSE":__('PLATFORM_WAREHOUSE'),"SUPPLIER_DIRECT":__('SUPPLIER_DIRECT')}, formatter: Table.api.formatter.normal},
                        {field: 'priority', title: __('Priority')},
                        {field: 'last_sync_time', title: __('Last_sync_time'), operate:'RANGE', addclass:'datetimerange', autocomplete:false, formatter: Table.api.formatter.datetime},
                        {field: 'sync_status', title: __('Sync_status'), searchList: {"PENDING":__('PENDING'),"SUCCESS":__('SUCCESS'),"FAILED":__('FAILED')}, formatter: Table.api.formatter.status},
                        {field: 'status', title: __('Status'), searchList: {"normal":__('Normal'),"paused":__('Paused'),"offline":__('Offline')}, formatter: Table.api.formatter.status},
                        {field: 'createtime', title: __('Createtime'), operate:'RANGE', addclass:'datetimerange', autocomplete:false, formatter: Table.api.formatter.datetime},
                        {field: 'updatetime', title: __('Updatetime'), operate:'RANGE', addclass:'datetimerange', autocomplete:false, formatter: Table.api.formatter.datetime},
                        {field: 'operate', title: __('Operate'), table: table, events: Table.api.events.operate, formatter: Table.api.formatter.operate}
                    ]
                ]
            });

            // 为表格绑定事件
            Table.api.bindevent(table);
        },
        add: function () {
            Controller.api.bindevent();
        },
        edit: function () {
            Controller.api.bindevent();
        },
        api: {
            bindevent: function () {
                Form.api.bindevent($("form[role=form]"));
            }
        }
    };
    return Controller;
});
