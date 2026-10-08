define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/warehouse/index' + location.search,
                    add_url: 'shop/warehouse/add',
                    edit_url: 'shop/warehouse/edit',
                    del_url: 'shop/warehouse/del',
                    multi_url: 'shop/warehouse/multi',
                    import_url: 'shop/warehouse/import',
                    table: 'shop_warehouse',
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
                        {field: 'owner_type', title: __('Owner_type'), searchList: {"PLATFORM":__('PLATFORM'),"SUPPLIER":__('SUPPLIER')}, formatter: Table.api.formatter.normal},
                        {field: 'owner_id', title: __('Owner_id')},
                        {field: 'warehouse_type', title: __('Warehouse_type'), searchList: {"PHYSICAL":__('PHYSICAL'),"VIRTUAL_DIRECT":__('VIRTUAL_DIRECT')}, formatter: Table.api.formatter.normal},
                        {field: 'province_id', title: __('Province_id')},
                        {field: 'city_id', title: __('City_id')},
                        {field: 'area_id', title: __('Area_id')},
                        {field: 'address', title: __('Address'), operate: 'LIKE', table: table, class: 'autocontent', formatter: Table.api.formatter.content},
                        {field: 'contact_name', title: __('Contact_name'), operate: 'LIKE'},
                        {field: 'contact_mobile', title: __('Contact_mobile'), operate: 'LIKE'},
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
