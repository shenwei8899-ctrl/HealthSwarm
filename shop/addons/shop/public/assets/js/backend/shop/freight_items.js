define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/freight_items/index/freight_id/'+Config.freight_id + location.search,
                    add_url: 'shop/freight_items/add/freight_id/' + Config.freight_id,
                    edit_url: 'shop/freight_items/edit',
                    del_url: 'shop/freight_items/del',
                    multi_url: 'shop/freight_items/multi',
                    import_url: 'shop/freight_items/import',
                    table: 'shop_freight_items',
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
                            field: 'freight.name',
                            title: __('Freight_id')
                        },
                        {
                            field: 'first_num',
                            title: __('First_num'),
                            operate: 'BETWEEN'
                        },
                        {
                            field: 'first_price',
                            title: __('First_price'),
                            operate: 'BETWEEN'
                        },
                        {
                            field: 'continue_num',
                            title: __('Continue_num'),
                            operate: 'BETWEEN'
                        },
                        {
                            field: 'continue_price',
                            title: __('Continue_price'),
                            operate: 'BETWEEN'
                        },
                        // {
                        //     field: 'area_ids',
                        //     title: __('Area_ids'),
                        //     operate: 'LIKE'
                        // },
                        {
                            field: 'type',
                            title: __('Type'),
                            searchList: {
                                "0": __('Type 0'),
                                "1": __('Type 1'),
                                "2": __('Type 2')
                            },
                            formatter: Table.api.formatter.normal
                        },
                        // {
                        //     field: 'postage_area_ids',
                        //     title: __('Postage_area_ids'),
                        //     operate: 'LIKE'
                        // },
                        {
                            field: 'postage_num',
                            title: __('Postage_num'),
                            operate: 'BETWEEN'
                        },
                        {
                            field: 'postage_price',
                            title: __('Postage_price'),
                            operate: 'BETWEEN'
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
        loadJsTree() {
            require(['jstree'], function () {
                $('.channeltree').on("changed.jstree", function (e, data) {
                    let id = $(this).data('id');
                    $('#' + id).val(data.selected.join(','));
                    return false;
                });
                //渲染默认
                $(".channeltree").on("loaded.jstree", function (event, data) {
                    let id = $(this).data('id');
                    let childNodes = event.target.firstChild.childNodes;
                    for (let i = 0, len = childNodes.length; i < len; i++) {
                        let root = data.instance.get_node(childNodes[i].lastChild);
                        let nodes = root.children_d;
                        for (let j in nodes) {
                            let node = data.instance.get_node(nodes[j]);
                            if (id == 'c-postage_area_ids' && Config.postage_area_ids) {
                                let postage_area_ids = Config.postage_area_ids.split(',');
                                if (postage_area_ids.includes(node.id)) {
                                    data.instance.select_node(node);
                                }
                            } else if (Config.area_ids) {
                                let area_ids = Config.area_ids.split(',');
                                if (area_ids.includes(node.id)) {
                                    data.instance.select_node(node);
                                }
                            }

                        }
                    }
                });
                $('.channeltree').jstree({
                    "themes": {
                        "stripes": true
                    },
                    "checkbox": {
                        "keep_selected_style": false,
                    },
                    "types": {
                        "channel": {
                            "icon": false,
                        },
                        "list": {
                            "icon": false,
                        },
                        "link": {
                            "icon": false,
                        },
                        "disabled": {
                            "check_node": false,
                            "uncheck_node": false
                        }
                    },
                    'plugins': ["types", "checkbox"],
                    "core": {
                        "multiple": true,
                        'check_callback': true,
                        "data": Config.areas
                    }
                });
            })
            $('#c-type').on('change', function () {
                let v = $(this).val();
                if (v == 2) {
                    $('.c-postage_num').addClass('hide');
                    $('.c-postage_price').removeClass('hide');
                } else if (v == 1) {
                    $('.c-postage_price').addClass('hide');
                    $('.c-postage_num').removeClass('hide');
                } else {
                    $('.c-postage_price').addClass('hide');
                    $('.c-postage_num').addClass('hide');
                }
            })
        },
        add: function () {
            this.loadJsTree();
            Controller.api.bindevent();
        },
        edit: function () {
            this.loadJsTree();
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