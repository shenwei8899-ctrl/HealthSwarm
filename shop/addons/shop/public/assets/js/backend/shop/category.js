define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/category/index' + location.search,
                    add_url: 'shop/category/add',
                    edit_url: 'shop/category/edit',
                    del_url: 'shop/category/del',
                    multi_url: 'shop/category/multi',
                    import_url: 'shop/category/import',
                    table: 'shop_category',
                }
            });

            var table = $("#table");

            // 初始化表格
            table.bootstrapTable({
                url: $.fn.bootstrapTable.defaults.extend.index_url,
                pk: 'id',
                sortName: 'weigh',
                pagination: false,
                commonSearch: false,
                columns: [
                    [
                        {checkbox: true},
                        {field: 'id', title: __('Id')},
                        {field: 'pid', title: __('Pid')},
                        {
                            field: 'name', title: __('Name'), align: 'left', formatter: function (value, row, index) {
                                return value.toString().replace(/(&|&amp;)nbsp;/g, '&nbsp;');
                            }
                        },
                        {field: 'nickname', title: __('Nickname'), operate: 'LIKE', visible: false},
                        {field: 'flag', title: __('Flag'), searchList: {"hot": __('Hot'), "index": __('Index'), "recommend": __('Recommend')}, operate: 'FIND_IN_SET', formatter: Table.api.formatter.label},
                        {field: 'image', title: __('Image'), operate: false, events: Table.api.events.image, formatter: Table.api.formatter.image},
                        {field: 'keywords', title: __('Keywords'), operate: 'LIKE', visible: false},
                        {field: 'description', title: __('Description'), operate: 'LIKE', visible: false},
                        {field: 'icon', title: __('Icon'), operate: 'LIKE', formatter: Controller.api.formatter.icon},
                        {
                            field: 'url', title: __('Url'), formatter: function (value, row, index) {
                                return '<a href="' + value + '" target="_blank" class="btn btn-default btn-xs"><i class="fa fa-link"></i></a>';
                            }
                        },
                        {field: 'diyname', title: __('Diyname'), operate: 'LIKE', visible: false},
                        {field: 'createtime', title: __('Createtime'), operate: 'RANGE', addclass: 'datetimerange', autocomplete: false, formatter: Table.api.formatter.datetime},
                        {field: 'updatetime', title: __('Updatetime'), operate: 'RANGE', visible: false, addclass: 'datetimerange', autocomplete: false, formatter: Table.api.formatter.datetime},
                        {field: 'isnav', title: __('Isnav'), searchList: {"1": __('Yes'), "0": __('No')}, table: table, formatter: Table.api.formatter.toggle},
                        {field: 'weigh', title: __('Weigh'), operate: false},
                        {field: 'status', title: __('Status'), operate: 'LIKE', formatter: Table.api.formatter.status},
                        {field: 'operate', title: __('Operate'), table: table, events: Table.api.events.operate, formatter: Table.api.formatter.operate, buttons: [{
                            name: 'goods_attribute',
                            title: __('属性名称'),
                            classname: 'btn btn-xs btn-primary btn-dialog',
                            text: '商品属性',                         
                            extend: 'data-area=\'["90%","90%"]\'',
                            url: 'shop/attribute/index/category_id/{id}',
                            icon:'fa fa-plus',
                            hidden(row){
                               return !!row.attribute;
                            }
                        },{
                            name: 'goods_attribute',
                            title: __('属性名称'),
                            classname: 'btn btn-xs btn-success btn-dialog',
                            text: '商品属性',                         
                            extend: 'data-area=\'["90%","90%"]\'',
                            url: 'shop/attribute/index/category_id/{id}',
                            icon:'fa fa-plus',
                            hidden(row){
                                return !row.attribute;
                            }
                        }]}
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
            formatter: {
                icon: function (value, row, index) {
                    value = value === null ? '' : value.toString();
                    value = value.indexOf(" ") > -1 ? value : "fa fa-" + value;
                    //渲染fontawesome图标
                    return '<i class="' + value + '"></i>';
                },
            },
            bindevent: function () {
                //获取分类拼音
                var si;
                $(document).on("keyup", "#c-name", function () {
                    var value = $(this).val();
                    if (value != '' && !value.match(/\n/)) {
                        clearTimeout(si);
                        si = setTimeout(function () {
                            Fast.api.ajax({
                                loading: false,
                                url: "shop/ajax/get_title_pinyin",
                                data: {title: value}
                            }, function (data, ret) {
                                $("#c-diyname").val(data.pinyin.substr(0, 100));
                                return false;
                            }, function (data, ret) {
                                return false;
                            });
                        }, 200);
                    }
                });

                var iconlist = [];
                var iconfunc = function () {
                    Layer.open({
                        type: 1,
                        area: ['99%', '98%'], //宽高
                        content: Template('chooseicontpl', {iconlist: iconlist})
                    });
                };
                Form.api.bindevent($("form[role=form]"));
                $(document).on('click', ".btn-search-icon", function () {
                    if (iconlist.length == 0) {
                        $.getJSON(Config.site.cdnurl + "/assets/addons/shop/shopicon/iconfont.json", function (ret) {
                            iconlist = ret.glyphs;
                            iconfunc();
                        });
                    } else {
                        iconfunc();
                    }
                });
                $(document).on('click', '#chooseicon ul li', function () {
                    $("input[name='row[icon]']").val($(this).data("font"));
                    Layer.closeAll();
                });
                $(document).on('keyup', 'input.js-icon-search', function () {
                    $("#chooseicon ul li").show();
                    if ($(this).val() != '') {
                        $("#chooseicon ul li:not([data-keyword*='" + $(this).val() + "'])").hide();
                    }
                });
            }
        }
    };
    return Controller;
});
