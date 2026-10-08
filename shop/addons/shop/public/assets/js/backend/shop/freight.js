define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/freight/index' + location.search,
                    add_url: 'shop/freight/add',
                    edit_url: 'shop/freight/edit',
                    del_url: 'shop/freight/del',
                    multi_url: 'shop/freight/multi',
                    import_url: 'shop/freight/import',
                    table: 'shop_freight',
                }
            });

            var table = $("#table");

            // 初始化表格
            table.bootstrapTable({
                url: $.fn.bootstrapTable.defaults.extend.index_url,
                pk: 'id',
                sortName: 'weigh',
                columns: [
                    [
                        {checkbox: true},
                        {field: 'id', title: __('Id')},
                        {field: 'name', title: __('Name'), operate: 'LIKE'},
                        {field: 'type', title: __('Type'), searchList: {"1": __('Type 1'), "2": __('Type 2')}, formatter: Table.api.formatter.normal},
                        {field: 'num', title: __('Num'), operate: 'BETWEEN'},
                        {field: 'price', title: __('Price'), operate: 'BETWEEN'},
                        {field: 'continue_num', title: __('Continue_num'), operate: 'BETWEEN'},
                        {field: 'continue_price', title: __('Continue_price'), operate: 'BETWEEN'},
                        {field: 'createtime', title: __('Createtime'), operate: 'RANGE', addclass: 'datetimerange', autocomplete: false, formatter: Table.api.formatter.datetime},
                        {field: 'updatetime', title: __('Updatetime'), operate: 'RANGE', addclass: 'datetimerange', autocomplete: false, formatter: Table.api.formatter.datetime},
                        {field: 'weigh', title: __('Weigh'), operate: false},
                        {field: 'switch', title: __('Switch'), searchList: {"1": __('Yes'), "0": __('No')}, table: table, formatter: Table.api.formatter.toggle},
                        {
                            field: 'operate', title: __('Operate'), table: table, events: Table.api.events.operate, formatter: Table.api.formatter.operate,
                            buttons: [{
                                name: '运费条件',
                                title: __('运费条件'),
                                classname: 'btn btn-xs btn-primary btn-dialog',
                                text: '运费条件',
                                icon: 'fa fa-sticky-note-o',
                                extend: 'data-area=\'["90%","90%"]\'',
                                url: 'shop/freight_items/index/freight_id/{id}'
                            }]
                        }
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
