define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/stock_flow/index' + location.search,
                    table: 'shop_stock_flow',
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
                        {field: 'id', title: __('Id')},
                        {field: 'flow_sn', title: __('Flow_sn'), operate: 'LIKE'},
                        {field: 'warehouse_sku_id', title: __('Warehouse_sku_id')},
                        {field: 'supplier_id', title: __('Supplier_id')},
                        {field: 'warehouse_id', title: __('Warehouse_id')},
                        {field: 'goods_id', title: __('Goods_id')},
                        {field: 'goods_sku_id', title: __('Goods_sku_id')},
                        {field: 'biz_type', title: __('Biz_type'), operate: 'LIKE'},
                        {field: 'biz_no', title: __('Biz_no'), operate: 'LIKE'},
                        {field: 'change_on_hand', title: __('Change_on_hand')},
                        {field: 'change_locked', title: __('Change_locked')},
                        {field: 'before_on_hand', title: __('Before_on_hand')},
                        {field: 'after_on_hand', title: __('After_on_hand')},
                        {field: 'before_locked', title: __('Before_locked')},
                        {field: 'after_locked', title: __('After_locked')},
                        {field: 'operator_type', title: __('Operator_type'), operate: 'LIKE'},
                        {field: 'operator_id', title: __('Operator_id')},
                        {field: 'remark', title: __('Remark'), operate: 'LIKE', table: table, class: 'autocontent', formatter: Table.api.formatter.content},
                        {field: 'createtime', title: __('Createtime'), operate:'RANGE', addclass:'datetimerange', autocomplete:false, formatter: Table.api.formatter.datetime}
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
