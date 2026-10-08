define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/stock_reservation/index' + location.search,
                    table: 'shop_stock_reservation',
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
                        {field: 'reservation_sn', title: __('Reservation_sn'), operate: 'LIKE'},
                        {field: 'biz_key', title: __('Biz_key'), operate: 'LIKE'},
                        {field: 'order_sn', title: __('Order_sn'), operate: 'LIKE'},
                        {field: 'supplier_order_sn', title: __('Supplier_order_sn'), operate: 'LIKE'},
                        {field: 'warehouse_sku_id', title: __('Warehouse_sku_id')},
                        {field: 'goods_id', title: __('Goods_id')},
                        {field: 'goods_sku_id', title: __('Goods_sku_id')},
                        {field: 'quantity', title: __('Quantity')},
                        {field: 'status', title: __('Status'), searchList: {"LOCKED":__('LOCKED'),"RELEASED":__('RELEASED'),"DEDUCTED":__('DEDUCTED')}, formatter: Table.api.formatter.status},
                        {field: 'expiretime', title: __('Expiretime'), operate:'RANGE', addclass:'datetimerange', autocomplete:false, formatter: Table.api.formatter.datetime},
                        {field: 'released_at', title: __('Released_at'), formatter: Table.api.formatter.datetime},
                        {field: 'deducted_at', title: __('Deducted_at'), formatter: Table.api.formatter.datetime},
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
