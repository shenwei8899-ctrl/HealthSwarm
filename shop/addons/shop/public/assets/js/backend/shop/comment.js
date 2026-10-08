define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/comment/index' + location.search,
                    add_url: 'shop/comment/add',
                    edit_url: 'shop/comment/edit',
                    del_url: 'shop/comment/del',
                    multi_url: 'shop/comment/multi',
                    import_url: 'shop/comment/import',
                    table: 'shop_comment',
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
                        {field: 'user.nickname', title: __('Nickname')},
                        {field: 'order_id', title: __('Order_id')},
                        // {field: 'pid', title: __('Pid')},
                        {field: 'goods.title', title: __('Goods')},
                        {field: 'star', title: __('Star')},
                        {field: 'content', title: __('Content'), formatter: Controller.api.content},
                        {field: 'images', title: __('Images'), operate: false, events: Table.api.events.image, formatter: Table.api.formatter.images},
                        // {field: 'subscribe', title: __('Subscribe')},
                        {field: 'createtime', title: __('Createtime'), operate: 'RANGE', addclass: 'datetimerange', autocomplete: false, formatter: Table.api.formatter.datetime},
                        {field: 'updatetime', title: __('Updatetime'), operate: 'RANGE', addclass: 'datetimerange', autocomplete: false, formatter: Table.api.formatter.datetime, visible: false},
                        {field: 'status', title: __('Status'), searchList: {"normal": __('Normal'), "hidden": __('Hidden')}, formatter: Table.api.formatter.status},
                        {
                            field: 'operate', title: __('Operate'), table: table, events: Table.api.events.operate, formatter: Table.api.formatter.operate, buttons: [{
                                name: '回复',
                                title: function (row) {
                                    return '回复（' + (row.user ? row.user.nickname : '未知') + '）';
                                },
                                classname: 'btn btn-xs btn-primary btn-dialog',
                                text: function (row) {
                                    return '回复（' + row.comments + '）';
                                },
                                icon: 'fa fa-comment',
                                url: 'shop/comment/reply/pid/{id}'
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
        reply: function () {
            let refresh = function () {
                window.location.reload();
                parent.$("#table").bootstrapTable('refresh', {});
            }
            $(document).on('click', '.btn-reply', function () {
                Form.api.submit($("form[role=form]"));
                setTimeout(refresh, 1500)
            })
            $('.btn-delone').data('success', refresh)
            $('.btn-dialog').data('end', refresh)
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
