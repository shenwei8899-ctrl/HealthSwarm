define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/order_shipment/index' + location.search,
                    table: 'shop_order_shipment',
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
                        {field: 'shipment_sn', title: __('Shipment_sn'), operate: 'LIKE'},
                        {field: 'supplier_order_id', title: __('Supplier_order_id')},
                        {field: 'order_id', title: __('Order_id')},
                        {field: 'order_sn', title: __('Order_sn'), operate: 'LIKE'},
                        {field: 'shipper_code', title: __('Shipper_code'), operate: 'LIKE'},
                        {field: 'shipper_name', title: __('Shipper_name'), operate: 'LIKE'},
                        {field: 'logistic_code', title: __('Logistic_code'), operate: 'LIKE'},
                        {field: 'status', title: __('Status'), searchList: {"PENDING":__('PENDING'),"SHIPPED":__('SHIPPED'),"RECEIVED":__('RECEIVED'),"CANCELLED":__('CANCELLED')}, formatter: Table.api.formatter.status},
                        {field: 'shipping_at', title: __('Shipping_at'), formatter: Table.api.formatter.datetime},
                        {field: 'received_at', title: __('Received_at'), formatter: Table.api.formatter.datetime},
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
