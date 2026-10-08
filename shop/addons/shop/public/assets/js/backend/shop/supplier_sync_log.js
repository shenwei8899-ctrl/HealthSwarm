define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/supplier_sync_log/index' + location.search,
                    table: 'shop_supplier_sync_log',
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
                        {field: 'supplier_id', title: __('Supplier_id')},
                        {field: 'sync_type', title: __('Sync_type'), searchList: {"PRODUCT":__('PRODUCT'),"PRICE":__('PRICE'),"STOCK":__('STOCK'),"DELIVERY":__('DELIVERY'),"ORDER":__('ORDER'),"AFTERSALE":__('AFTERSALE')}, formatter: Table.api.formatter.normal},
                        {field: 'biz_key', title: __('Biz_key'), operate: 'LIKE'},
                        {field: 'request_id', title: __('Request_id'), operate: 'LIKE'},
                        {field: 'request_json', title: __('Request_json')},
                        {field: 'response_json', title: __('Response_json')},
                        {field: 'status', title: __('Status'), searchList: {"SUCCESS":__('SUCCESS'),"FAILED":__('FAILED')}, formatter: Table.api.formatter.status},
                        {field: 'error_message', title: __('Error_message'), operate: 'LIKE', table: table, class: 'autocontent', formatter: Table.api.formatter.content},
                        {field: 'retry_count', title: __('Retry_count')},
                        {field: 'createtime', title: __('Createtime'), operate:'RANGE', addclass:'datetimerange', autocomplete:false, formatter: Table.api.formatter.datetime}
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
