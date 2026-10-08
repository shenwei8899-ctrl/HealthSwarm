define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/navigation/index' + location.search,
                    add_url: 'shop/navigation/add',
                    edit_url: 'shop/navigation/edit',
                    del_url: 'shop/navigation/del',
                    multi_url: 'shop/navigation/multi',
                    import_url: 'shop/navigation/import',
                    table: 'shop_navigation',
                }
            });

            var table = $("#table");

            // 初始化表格
            table.bootstrapTable({
                url: $.fn.bootstrapTable.defaults.extend.index_url,
                pk: 'id',
                sortName: 'weigh',
                columns: [
                    [{
                            checkbox: true
                        },
                        {
                            field: 'id',
                            title: __('Id')
                        },
                        {
                            field: 'name',
                            title: __('Name'),
                            operate: 'LIKE'
                        },
                        {
                            field: 'size',
                            title: __('Size')
                        },
                        {
                            field: 'image',
                            title: __('Image'),
                            operate: false,
                            events: Table.api.events.image,
                            formatter: Table.api.formatter.image
                        },
                        {
                            field: 'path',
                            title: __('Path'),
                            operate: 'LIKE'
                        },
                        {
                            field: 'switch',
                            title: __('Switch'),
                            searchList: {
                                "1": __('Yes'),
                                "0": __('No')
                            },
                            table: table,
                            formatter: Table.api.formatter.toggle
                        },
                        {
                            field: 'weigh',
                            title: __('Weigh'),
                            operate: false
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
                            formatter: Table.api.formatter.operate
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
                $(document).on("click", ".btn-select-page", function (e, obj) {
                    var that = this;
                    Fast.api.open("shop/ajax/get_page_list", "选择路径", {
                        callback: function (data) {
                            $(that).parent().prev().val(data).trigger("change");
                        }
                    })
                });
                Form.api.bindevent($("form[role=form]"));
            }
        }
    };
    return Controller;
});