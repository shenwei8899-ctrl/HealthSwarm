define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/ingredient_product_map/index' + location.search,
                    add_url: 'shop/ingredient_product_map/add',
                    edit_url: 'shop/ingredient_product_map/edit',
                    del_url: 'shop/ingredient_product_map/del',
                    multi_url: 'shop/ingredient_product_map/multi',
                    import_url: 'shop/ingredient_product_map/import',
                    table: 'shop_ingredient_product_map',
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
                        {field: 'ingredient_id', title: __('Ingredient_id')},
                        {field: 'goods_id', title: __('Goods_id')},
                        {field: 'goods_sku_id', title: __('Goods_sku_id')},
                        {field: 'content_quantity', title: __('Content_quantity'), operate:'BETWEEN'},
                        {field: 'content_unit', title: __('Content_unit'), operate: 'LIKE'},
                        {field: 'conversion_rate', title: __('Conversion_rate'), operate:'BETWEEN'},
                        {field: 'priority', title: __('Priority')},
                        {field: 'is_substitute', title: __('Is_substitute')},
                        {field: 'status', title: __('Status'), searchList: {"normal":__('Normal'),"hidden":__('Hidden')}, formatter: Table.api.formatter.status},
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
