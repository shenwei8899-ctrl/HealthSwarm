define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/exchange/index' + location.search,
                    add_url: 'shop/exchange/add',
                    edit_url: 'shop/exchange/edit',
                    del_url: 'shop/exchange/del',
                    multi_url: 'shop/exchange/multi',
                    import_url: 'shop/exchange/import',
                    table: 'shop_exchange',
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
                        {field: 'type', title: __('Type'), searchList: {"virtual":__('Type virtual'),"reality":__('Type reality')}, formatter: Table.api.formatter.normal},
                        {field: 'title', title: __('Title'), operate: 'LIKE', formatter: Controller.api.content},
                        {field: 'description', title: __('Description'), operate: 'LIKE', formatter: Controller.api.content},
                        {field: 'image', title: __('Image'), operate: false, events: Table.api.events.image, formatter: Table.api.formatter.image},
                        {field: 'score', title: __('Score')},
                        {field: 'stocks', title: __('Stocks')},
                        {field: 'sales', title: __('Sales')},
                        {field: 'weigh', title: __('Weigh'), operate: false},
                        {field: 'createtime', title: __('Createtime'), operate:'RANGE', addclass:'datetimerange', autocomplete:false, formatter: Table.api.formatter.datetime},
                        {field: 'updatetime', title: __('Updatetime'), operate:'RANGE', addclass:'datetimerange', autocomplete:false, formatter: Table.api.formatter.datetime},
                        {field: 'status', title: __('Status'), searchList: {"normal":__('Normal'),"hidden":__('Hidden')}, formatter: Table.api.formatter.status},
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
            },
            content: function (value, row, index) {
                var width = this.width != undefined ? (this.width.match(/^\d+$/) ? this.width + "px" : this.width) : "250px";
                return "<div style='white-space: nowrap; text-overflow:ellipsis; overflow: hidden; max-width:" + width + ";' title='" + value + "' data-toggle='tooltip' data-placement='right'>" + value + "</div>";
            },
        }
    };
    return Controller;
});