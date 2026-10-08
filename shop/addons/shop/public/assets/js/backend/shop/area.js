define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/area/index' + location.search,
                    add_url: 'shop/area/add',
                    edit_url: 'shop/area/edit',
                    del_url: 'shop/area/del',
                    multi_url: 'shop/area/multi',
                    import_url: 'shop/area/import',
                    table: 'shop_area',
                }
            });

            $(document).on("click", ".btn-refresh-area", function () {
                Layer.confirm("更新地区数据将导致现有的地区数据表重置，请谨慎操作<br>数据源采用高德地图行政区划数据，请在配置管理中配置高德地图Web服务API密钥", {icon: 0}, function (index, layero) {
                    Fast.api.ajax({
                        url: 'shop/area/refresh'
                    }, function (data, ret) {
                        Layer.close(index);
                        $(".btn-refresh").trigger("click");
                    });
                });
                return false;
            });

            var table = $("#table");
            table.on('load-success.bs.table', function (e, data) {
                if (!data.initialized) {
                    Layer.confirm("当前地区数据未导入，请点击确定导入地区数据", {}, function (index, layero) {
                        Fast.api.ajax({
                            url: 'shop/area/import'
                        }, function(){
                            Layer.close(index);
                            $(".btn-refresh").trigger("click");
                        });
                    });
                }
            });

            // 初始化表格
            table.bootstrapTable({
                url: $.fn.bootstrapTable.defaults.extend.index_url,
                pk: 'id',
                sortName: 'id',
                sortOrder: 'asc',
                columns: [
                    [
                        {checkbox: true},
                        {field: 'id', title: __('Id')},
                        {field: 'pid', title: __('Pid'), formatter: Table.api.formatter.search},
                        {field: 'level', title: __('Level'), formatter: Table.api.formatter.search},
                        {field: 'name', title: __('Name'), operate: 'LIKE'},
                        {field: 'pinyin', title: __('Pinyin'), operate: 'LIKE'},
                        {field: 'py', title: __('Py'), operate: 'LIKE'},
                        {field: 'adcode', title: __('Adcode'), operate: 'LIKE'},
                        {field: 'lng', title: __('Lng'), operate: 'LIKE'},
                        {field: 'lat', title: __('Lat'), operate: 'LIKE'},
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
