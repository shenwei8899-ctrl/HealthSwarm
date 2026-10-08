define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/order_goods/index' + location.search,
                    add_url: 'shop/order_goods/add',
                    edit_url: 'shop/order_goods/edit',
                    del_url: 'shop/order_goods/del',
                    multi_url: 'shop/order_goods/multi',
                    import_url: 'shop/order_goods/import',
                    table: 'shop_order_goods',
                }
            });

            var table = $("#table");

            // 初始化表格
            table.bootstrapTable({
                url: $.fn.bootstrapTable.defaults.extend.index_url,
                pk: 'id',
                sortName: 'id',
                columns: [
                    [
                        {checkbox: true},
                        {field: 'id', title: __('Id')},
                        {field: 'order_sn', title: __('Order_sn'), operate: 'LIKE'},
                        {field: 'goods_id', title: __('Goods_id')},
                        {field: 'goods_sku_id', title: __('Goods_sku_id')},
                        {field: 'title', title: __('Title'), operate: 'LIKE'},
                        {field: 'nums', title: __('Nums')},
                        {field: 'marketprice', title: __('Marketprice'), operate:'BETWEEN'},
                        {field: 'price', title: __('Price'), operate:'BETWEEN'},
                        {field: 'aftersalestate', title: __('Aftersalestate'), searchList: {"0":__('Aftersalestate 0'),"1":__('Aftersalestate 1')}, formatter: Table.api.formatter.normal},
                        {field: 'commentstate', title: __('Commentstate'), searchList: {"0":__('Commentstate 0'),"1":__('Commentstate 1')}, formatter: Table.api.formatter.normal},
                        {field: 'attrdata', title: __('Attrdata'), operate: 'LIKE'},
                        {field: 'shippingfee', title: __('Shippingfee'), operate:'BETWEEN'},
                        {field: 'image', title: __('Image'), operate: false, events: Table.api.events.image, formatter: Table.api.formatter.image},
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