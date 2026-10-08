define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/order_aftersales/index' + location.search,
                    edit_url: 'shop/order_aftersales/edit',
                    multi_url: 'shop/order_aftersales/multi',
                    import_url: 'shop/order_aftersales/import',
                    table: 'shop_order_aftersales',
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
                        {field: 'user_id', title: __('User_id'), formatter: Table.api.formatter.search},
                        {field: 'user.nickname', title: __('User')},
                        {field: 'order_id', title: __('Order_id'), formatter: Table.api.formatter.search},
                        {field: 'order_goods.order_sn', title: __('Order_sn'), formatter: Table.api.formatter.search},
                        {field: 'order_goods.title', title: __('Order_goods')},
                        {field: 'type', title: __('Type'), searchList: {"1": __('Type 1'), "2": __('Type 2'), "3": __('Type 3')}, formatter: Table.api.formatter.normal},
                        {field: 'nums', title: __('Nums'), sortable: true},
                        {field: 'realprice', title: __('Realprice'), operate: 'BETWEEN', sortable: true},
                        {field: 'shippingfee', title: __('Shippingfee'), operate: 'BETWEEN', sortable: true},
                        {field: 'refund', title: __('Refund'), operate: 'BETWEEN', sortable: true},
                        {field: 'reason', title: __('Reason'), operate: 'LIKE'},
                        {field: 'images', title: __('Images'), operate: false, events: Table.api.events.image, formatter: Table.api.formatter.images},
                        {field: 'mark', title: __('Mark'), operate: 'LIKE'},
                        {field: 'expressname', title: __('Expressname')},
                        {field: 'expressno', title: __('Expressno')},
                        {field: 'status', title: __('Status'), searchList: {"1": __('Status 1'), "2": __('Status 2'), "3": __('Status 3')}, formatter: Table.api.formatter.status},
                        {field: 'createtime', title: __('Createtime'), operate: 'RANGE', addclass: 'datetimerange', autocomplete: false, formatter: Table.api.formatter.datetime},
                        {field: 'updatetime', title: __('Updatetime'), operate: 'RANGE', addclass: 'datetimerange', autocomplete: false, formatter: Table.api.formatter.datetime},
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

            $(document).on('click', '.btn-refresh', function () {
                parent.$(".btn-refresh").trigger("click");
            });
            $(document).on('click', '.btn-confirmexpress', function () {
                var that = this;
                Layer.confirm('您确定已收到货吗？', {
                    btn: ['确定', '取消'] //按钮
                }, function (index, layero) {
                    Fast.api.ajax({
                        url: 'shop/order/refund',
                        data: {type: 3, order_goods_id: $(that).data("id")}
                    }, function (data, ret) {
                        Layer.close(index);
                        parent.Toastr.success(ret.msg);
                        parent.$(".btn-refresh").trigger("click");
                        var index = parent.Layer.getFrameIndex(window.name);
                        parent.Layer.close(index);
                    });
                });
            });
        },
        api: {
            bindevent: function () {
                Form.api.bindevent($("form[role=form]"));
            }
        }
    };
    return Controller;
});
