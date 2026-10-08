define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/order_supplier/index' + location.search,
                    table: 'shop_order_supplier',
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
                        {field: 'id', title: __('Id')},
                        {field: 'supplier_order_sn', title: __('Supplier_order_sn'), operate: 'LIKE'},
                        {field: 'order_id', title: __('Order_id')},
                        {field: 'order_sn', title: __('Order_sn'), operate: 'LIKE'},
                        {field: 'supplier_id', title: __('Supplier_id')},
                        {field: 'warehouse_id', title: __('Warehouse_id')},
                        {field: 'fulfillment_mode', title: __('Fulfillment_mode'), searchList: {"PLATFORM_WAREHOUSE":__('PLATFORM_WAREHOUSE'),"SUPPLIER_DIRECT":__('SUPPLIER_DIRECT')}, formatter: Table.api.formatter.normal},
                        {field: 'goods_amount', title: __('Goods_amount'), operate:'BETWEEN'},
                        {field: 'shipping_fee', title: __('Shipping_fee'), operate:'BETWEEN'},
                        {field: 'supply_amount', title: __('Supply_amount'), operate:'BETWEEN'},
                        {field: 'status', title: __('Status'), searchList: {"PENDING_ASSIGN":__('PENDING_ASSIGN'),"PENDING_ACCEPT":__('PENDING_ACCEPT'),"ACCEPTED":__('ACCEPTED'),"PREPARING":__('PREPARING'),"PARTIALLY_SHIPPED":__('PARTIALLY_SHIPPED'),"SHIPPED":__('SHIPPED'),"COMPLETED":__('COMPLETED'),"CANCELLED":__('CANCELLED'),"REJECTED":__('REJECTED')}, formatter: Table.api.formatter.status},
                        {field: 'accepted_at', title: __('Accepted_at'), formatter: Table.api.formatter.datetime},
                        {field: 'preparing_at', title: __('Preparing_at'), formatter: Table.api.formatter.datetime},
                        {field: 'shipping_at', title: __('Shipping_at'), formatter: Table.api.formatter.datetime},
                        {field: 'completed_at', title: __('Completed_at'), formatter: Table.api.formatter.datetime},
                        {field: 'cancelled_at', title: __('Cancelled_at'), formatter: Table.api.formatter.datetime},
                        {field: 'createtime', title: __('Createtime'), operate:'RANGE', addclass:'datetimerange', autocomplete:false, formatter: Table.api.formatter.datetime},
                        {field: 'updatetime', title: __('Updatetime'), operate:'RANGE', addclass:'datetimerange', autocomplete:false, formatter: Table.api.formatter.datetime}
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
