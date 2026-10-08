define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/warehouse_sku/index' + location.search,
                    table: 'shop_warehouse_sku',
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
                        {field: 'warehouse_id', title: __('Warehouse_id')},
                        {field: 'supplier_id', title: __('Supplier_id')},
                        {field: 'supplier_sku_id', title: __('Supplier_sku_id')},
                        {field: 'goods_id', title: __('Goods_id')},
                        {field: 'goods_sku_id', title: __('Goods_sku_id')},
                        {field: 'on_hand_qty', title: __('On_hand_qty')},
                        {field: 'locked_qty', title: __('Locked_qty')},
                        {field: 'unavailable_qty', title: __('Unavailable_qty')},
                        {field: 'available_qty', title: __('Available_qty'), operate: false},
                        {field: 'in_transit_qty', title: __('In_transit_qty')},
                        {field: 'version', title: __('Version')},
                        {field: 'last_sync_time', title: __('Last_sync_time'), operate:'RANGE', addclass:'datetimerange', autocomplete:false, formatter: Table.api.formatter.datetime},
                        {field: 'createtime', title: __('Createtime'), operate:'RANGE', addclass:'datetimerange', autocomplete:false, formatter: Table.api.formatter.datetime},
                        {field: 'updatetime', title: __('Updatetime'), operate:'RANGE', addclass:'datetimerange', autocomplete:false, formatter: Table.api.formatter.datetime},
                        {field: 'operate', title: __('Operate'), table: table, events: {'click .btn-adjust': function (e, value, row) { Controller.api.adjust(row, table); }}, formatter: function () { return '<a class="btn btn-xs btn-warning btn-adjust"><i class="fa fa-sliders"></i> 库存调整</a>'; }}
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
            adjust: function (row, table) {
                var html = '<form class="form-horizontal" style="padding:20px">' +
                    '<div class="form-group"><label class="col-xs-4 control-label">实物库存变化</label><div class="col-xs-8"><input id="on-hand-delta" type="number" value="0" class="form-control"></div></div>' +
                    '<div class="form-group"><label class="col-xs-4 control-label">不可售库存变化</label><div class="col-xs-8"><input id="unavailable-delta" type="number" value="0" class="form-control"></div></div>' +
                    '<div class="form-group"><label class="col-xs-4 control-label">在途库存变化</label><div class="col-xs-8"><input id="in-transit-delta" type="number" value="0" class="form-control"></div></div>' +
                    '<div class="form-group"><label class="col-xs-4 control-label">调整原因</label><div class="col-xs-8"><textarea id="adjust-remark" class="form-control" required></textarea></div></div></form>';
                Layer.open({type: 1, title: '库存调整 #' + row.id, area: ['520px','430px'], content: html, btn: ['确认调整','取消'], yes: function (index) {
                    var remark = $('#adjust-remark').val().trim(); if (!remark) { Toastr.error('必须填写调整原因'); return; }
                    Fast.api.ajax({url: 'shop/warehouse_sku/adjust/ids/' + row.id, data: {on_hand_delta: $('#on-hand-delta').val(), unavailable_delta: $('#unavailable-delta').val(), in_transit_delta: $('#in-transit-delta').val(), remark: remark}}, function () { Layer.close(index); table.bootstrapTable('refresh'); return false; });
                }});
            },
            bindevent: function () {
                Form.api.bindevent($("form[role=form]"));
            }
        }
    };
    return Controller;
});
