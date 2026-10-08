define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/supplier/index' + location.search,
                    add_url: 'shop/supplier/add',
                    edit_url: 'shop/supplier/edit',
                    del_url: 'shop/supplier/del',
                    multi_url: 'shop/supplier/multi',
                    import_url: 'shop/supplier/import',
                    table: 'shop_supplier',
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
                        {field: 'code', title: __('Code'), operate: 'LIKE'},
                        {field: 'name', title: __('Name'), operate: 'LIKE'},
                        {field: 'company_name', title: __('Company_name'), operate: 'LIKE'},
                        {field: 'contact_name', title: __('Contact_name'), operate: 'LIKE'},
                        {field: 'contact_mobile', title: __('Contact_mobile'), operate: 'LIKE'},
                        {field: 'fulfillment_mode', title: __('Fulfillment_mode'), searchList: {"PLATFORM_WAREHOUSE":__('PLATFORM_WAREHOUSE'),"SUPPLIER_DIRECT":__('SUPPLIER_DIRECT'),"MIXED":__('MIXED')}, formatter: Table.api.formatter.normal},
                        {field: 'settlement_mode', title: __('Settlement_mode'), operate: 'LIKE'},
                        {field: 'api_type', title: __('Api_type'), searchList: {"NONE":__('NONE'),"HTTP":__('HTTP'),"MANUAL":__('MANUAL'),"FILE":__('FILE')}, formatter: Table.api.formatter.normal},
                        {field: 'priority', title: __('Priority')},
                        {field: 'status', title: __('Status'), searchList: {"normal":__('Normal'),"disabled":__('Disabled')}, formatter: Table.api.formatter.status},
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
