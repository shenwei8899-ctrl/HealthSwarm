define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/supplier_delivery_region/index' + location.search,
                    add_url: 'shop/supplier_delivery_region/add',
                    edit_url: 'shop/supplier_delivery_region/edit',
                    del_url: 'shop/supplier_delivery_region/del',
                    multi_url: 'shop/supplier_delivery_region/multi',
                    import_url: 'shop/supplier_delivery_region/import',
                    table: 'shop_supplier_delivery_region',
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
                        {field: 'province_id', title: __('Province_id')},
                        {field: 'city_id', title: __('City_id')},
                        {field: 'area_id', title: __('Area_id')},
                        {field: 'shipping_fee', title: __('Shipping_fee'), operate:'BETWEEN'},
                        {field: 'free_shipping_amount', title: __('Free_shipping_amount'), operate:'BETWEEN'},
                        {field: 'delivery_days', title: __('Delivery_days')},
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
