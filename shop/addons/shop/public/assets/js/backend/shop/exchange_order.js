define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/exchange_order/index' + location.search,
                    add_url: 'shop/exchange_order/add',
                    edit_url: 'shop/exchange_order/edit',
                    del_url: 'shop/exchange_order/del',
                    multi_url: 'shop/exchange_order/multi',
                    import_url: 'shop/exchange_order/import',
                    table: 'shop_exchange_order',
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
                        {field: 'user_id', title: __('User_id'), formatter: Table.api.formatter.search},
                        {field: 'user.nickname', title: __('昵称')},
                        {field: 'orderid', title: __('Orderid'), operate: 'LIKE'},
                        {field: 'exchange_id', title: __('Exchange_id')},
                        {field: 'exchange.title', title: __('物品'),formatter: Controller.api.content},
                        {field: 'type', title: __('Type'),searchList: {"virtual":__('Type virtual'),"reality":__('Type reality')}, formatter: Table.api.formatter.normal},
                        {field: 'nums', title: __('Nums')},
                        {field: 'score', title: __('Score')},
                        {field: 'receiver', title: __('Receiver'), operate: 'LIKE'},
                        {field: 'mobile', title: __('Mobile'), operate: 'LIKE'},
                        {field: 'address', title: __('Address'), operate: 'LIKE'},
                        {field: 'memo', title: __('Memo'), operate: 'LIKE'},
                        {field: 'reason', title: __('Reason'), operate: 'LIKE'},
                        {field: 'expressname', title: __('Expressname'), operate: 'LIKE'},
                        {field: 'expressno', title: __('Expressno'), operate: 'LIKE'},
                        {field: 'status', title: __('Status'), searchList: {"created":__('Created'),"inprogress":__('Inprogress'),"rejected":__('Rejected'),"delivered":__('Delivered'),"completed":__('Completed')}, formatter: Table.api.formatter.status},
                        {field: 'ip', title: __('Ip'), operate: 'LIKE'},
                        // {field: 'useragent', title: __('Useragent'), operate: 'LIKE'},
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
            },
            content: function (value, row, index) {
                var width = this.width != undefined ? (this.width.match(/^\d+$/) ? this.width + "px" : this.width) : "250px";
                return "<div style='white-space: nowrap; text-overflow:ellipsis; overflow: hidden; max-width:" + width + ";' title='" + value + "' data-toggle='tooltip' data-placement='right'>" + value + "</div>";
            },
        }
    };
    return Controller;
});
