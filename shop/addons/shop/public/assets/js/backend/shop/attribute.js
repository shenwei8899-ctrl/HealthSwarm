define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/attribute/index' + location.search,
                    add_url: 'shop/attribute/add/category_id/' + Config.category_id,
                    edit_url: 'shop/attribute/edit',
                    del_url: 'shop/attribute/del',
                    multi_url: 'shop/attribute/multi',
                    import_url: 'shop/attribute/import',
                    table: 'shop_attribute',
                }
            });

            var table = $("#table");

            // 初始化表格
            table.bootstrapTable({
                url: $.fn.bootstrapTable.defaults.extend.index_url,
                pk: 'id',
                sortName: 'id',
                columns: [
                    [{
                            checkbox: true
                        },
                        {
                            field: 'id',
                            title: __('Id')
                        },
                        {
                            field: 'category_id',
                            title: __('Category_id'),
                            visible: false
                        },
                        {
                            field: 'name',
                            title: __('Name'),
                            operate: 'LIKE'
                        },
                        {
                            field: 'type',
                            title: __('Type'),
                            searchList: {
                                "radio": __('Type radio'),
                                "checkbox": __('Type checkbox')
                            },
                            formatter: Table.api.formatter.normal
                        },                       
                        {
                            field: 'is_must',
                            title: __('Is_must'),
                            searchList: {
                                "1": __('Yes'),
                                "0": __('No')
                            },
                            table: table,
                            formatter: Table.api.formatter.toggle
                        },
                        {
                            field: 'is_search',
                            title: __('Is_search'),
                            searchList: {
                                "1": __('Yes'),
                                "0": __('No')
                            },
                            table: table,
                            formatter: Table.api.formatter.toggle
                        },
                        {
                            field: 'createtime',
                            title: __('Createtime'),
                            operate: 'RANGE',
                            addclass: 'datetimerange',
                            autocomplete: false,
                            formatter: Table.api.formatter.datetime
                        },
                        {
                            field: 'updatetime',
                            title: __('Updatetime'),
                            operate: 'RANGE',
                            addclass: 'datetimerange',
                            autocomplete: false,
                            formatter: Table.api.formatter.datetime
                        },
                        {
                            field: 'operate',
                            title: __('Operate'),
                            table: table,
                            events: Table.api.events.operate,
                            formatter: Table.api.formatter.operate,
                            buttons: [{
                                name: 'goods_attribute',
                                title: __('属性值'),
                                classname: 'btn btn-xs btn-primary btn-dialog',
                                text: '属性值',
                                extend: 'data-area=\'["90%","90%"]\'',
                                url: 'shop/attribute_value/index/attribute_id/{id}',
                                icon: 'fa fa-plus'
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