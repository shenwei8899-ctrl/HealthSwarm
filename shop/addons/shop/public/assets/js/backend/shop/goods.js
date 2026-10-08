define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    //设置弹窗宽高
    Fast.config.openArea = ['80%', '80%'];

    var vm, si;

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/goods/index' + location.search,
                    add_url: 'shop/goods/add',
                    edit_url: 'shop/goods/edit',
                    del_url: 'shop/goods/del',
                    multi_url: 'shop/goods/multi',
                    import_url: 'shop/goods/import',
                    table: 'shop_goods',
                }
            });
            Table.config.dragsortfield = '';
            var table = $("#table");

            // 初始化表格
            table.bootstrapTable({
                url: $.fn.bootstrapTable.defaults.extend.index_url,
                pk: 'id',
                sortName: 'id',
                fixedColumns: true,
                fixedRightNumber: 2,
                columns: [
                    [
                        {checkbox: true},
                        {field: 'id', title: __('Id')},
                        {field: 'spectype', title: __('Spectype'), searchList: {0: "单规格", 1: "多规格"}, formatter: Table.api.formatter.label},
                        {
                            field: 'category.name', title: __('Category'), operate: false,
                            formatter: function (value, row, index) {
                                return '<a href="javascript:;" class="searchit" data-field="category_id" data-value="' + row.category_id + '">' + value + '</a>';
                            }
                        },
                        {
                            field: 'category_id', title: __('Category'), visible: false, searchList: $.getJSON("shop/category/getList")
                        },
                        {field: 'image', title: __('Image'), operate: false, events: Table.api.events.image, formatter: Table.api.formatter.image},
                        {field: 'images', title: __('Images'), visible: false, operate: false, events: Table.api.events.image, formatter: Table.api.formatter.images},
                        {field: 'title', title: __('Title'), operate: 'LIKE', formatter: Controller.api.content},
                        {
                            field: 'url', title: __('Url'), formatter: function (value, row, index) {
                                return '<a href="' + row.url + '" target="_blank" class="btn btn-default btn-xs"><i class="fa fa-link"></i></a>';
                            }
                        },

                        {
                            field: 'freight.name', title: __('Freight'), operate: false,
                            formatter: function (value, row, index) {
                                return '<a href="javascript:;" class="searchit" data-field="freight_id" data-value="' + row.freight_id + '">' + value + '</a>';
                            }
                        },
                        {field: 'freight_id', title: __('Freight'), visible: false, searchList: $.getJSON("shop/freight/getList")},
                        {
                            field: 'brand.name', title: __('Brand'), operate: false,
                            formatter: function (value, row, index) {
                                return '<a href="javascript:;" class="searchit" data-field="brand_id" data-value="' + row.brand_id + '">' + (value || '无') + '</a>';
                            }
                        },
                        {field: 'brand_id', title: __('Brand'), visible: false, searchList: $.getJSON("shop/brand/getList")},
                        {field: 'goods_sn', title: __('Goods_sn'), operate: 'LIKE', formatter: Table.api.formatter.search},
                        {field: 'flag', title: __('Flag'), searchList: {"recommend": __('Recommend'), "hot": __('Hot'), "new": __('New'), "best": __('Best'), "index": __('Index')}, operate: 'FIND_IN_SET', formatter: Table.api.formatter.label},
                        {field: 'keywords', title: __('Keywords'), operate: 'LIKE', visible: false},
                        {field: 'marketprice', title: __('Marketprice'), operate: 'BETWEEN', sortable: true},
                        {field: 'price', title: __('Price'), operate: 'BETWEEN', sortable: true},
                        {field: 'stocks', title: __('Stocks'), sortable: true},
                        {field: 'sales', title: __('Sales'), sortable: true},
                        {field: 'views', title: __('Views'), sortable: true},
                        {field: 'comments', title: __('Comments'), sortable: true},
                        // {field: 'shares', title: __('Shares'), sortable: true},
                        // {field: 'corner', title: __('Corner'), operate: 'LIKE'},
                        {field: 'weight', title: __('Weight'), operate: 'BETWEEN', sortable: true},
                        {field: 'weigh', title: __('Weigh'), operate: false},
                        {field: 'createtime', title: __('Createtime'), operate: 'RANGE', addclass: 'datetimerange', autocomplete: false, formatter: Table.api.formatter.datetime},
                        {field: 'updatetime', title: __('Updatetime'), operate: 'RANGE', addclass: 'datetimerange', autocomplete: false, formatter: Table.api.formatter.datetime},
                        {field: 'status', title: __('Status'), searchList: {"normal": __('Normal'), "hidden": __('Hidden'), "soldout": __('Soldout')}, formatter: Table.api.formatter.status},
                        {
                            field: 'operate', title: __('Operate'), table: table, events: Table.api.events.operate, formatter: Table.api.formatter.operate,
                            // buttons: [{
                            //     name: 'goods_sku',
                            //     title: __('商品规格'),
                            //     classname: 'btn btn-xs btn-primary btn-dialog',
                            //     text: '商品规格',
                            //     extend: 'data-area=\'["90%","90%"]\'',
                            //     url: 'shop/goods_sku/add/goods_id/{id}',
                            //     icon: 'fa fa-plus',
                            //     hidden: function (row) {
                            //         return !!row.spectype;
                            //     }
                            // }, {
                            //     name: 'goods_sku',
                            //     title: __('商品规格'),
                            //     classname: 'btn btn-xs btn-success btn-dialog',
                            //     text: '商品规格',
                            //     extend: 'data-area=\'["90%","90%"]\'',
                            //     url: 'shop/goods_sku/add/goods_id/{id}',
                            //     icon: 'fa fa-plus',
                            //     hidden: function (row) {
                            //         return !row.spectype;
                            //     }
                            // }]
                        }
                    ]
                ]
            });

            // 为表格绑定事件
            Table.api.bindevent(table);
        },
        select: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/goods/index' + location.search,
                    // add_url: 'shop/goods/add',
                    // edit_url: 'shop/goods/edit',
                    // del_url: 'shop/goods/del',
                    // multi_url: 'shop/goods/multi',
                    // import_url: 'shop/goods/import',
                    table: 'shop_goods',
                }
            });
            Table.config.dragsortfield = '';
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
                        {field: 'category.name', title: __('Category'), operate: false},
                        {field: 'category_id', title: __('Category'), visible: false, searchList: $.getJSON("shop/category/getList")},
                        {field: 'brand.name', title: __('Brand'), operate: false},
                        {field: 'brand_id', title: __('Brand'), visible: false, searchList: $.getJSON("shop/brand/getList")},
                        {field: 'goods_sn', title: __('Goods_sn'), operate: 'LIKE'},
                        {field: 'title', title: __('Title'), operate: 'LIKE', formatter: Controller.api.content},
                        {field: 'marketprice', title: __('Marketprice'), operate: 'BETWEEN'},
                        {field: 'price', title: __('Price'), operate: 'BETWEEN'},
                        {field: 'stocks', title: __('Stocks')},
                        {field: 'sales', title: __('Sales')},
                        {field: 'views', title: __('Views')},
                        {field: 'comments', title: __('Comments')},
                        {field: 'image', title: __('Image'), operate: false, events: Table.api.events.image, formatter: Table.api.formatter.image},
                        {field: 'images', title: __('Images'), operate: false, events: Table.api.events.image, formatter: Table.api.formatter.images},
                        {field: 'corner', title: __('Corner'), operate: 'LIKE', visible: false},
                        {field: 'flag', title: __('Flag'), searchList: {"recommend": __('Recommend'), "hot": __('Hot'), "new": __('New'), "best": __('Best'), "index": __('Index')}, operate: 'FIND_IN_SET', formatter: Table.api.formatter.label},
                        {field: 'weight', title: __('Weight'), operate: 'BETWEEN'},
                        {field: 'weigh', title: __('Weigh'), operate: false},
                        {field: 'createtime', title: __('Createtime'), operate: 'RANGE', addclass: 'datetimerange', autocomplete: false, formatter: Table.api.formatter.datetime},
                        {field: 'status', title: __('Status'), searchList: {"normal": __('Normal'), "hidden": __('Hidden'), "soldout": __('Soldout')}, formatter: Table.api.formatter.status},

                    ]
                ]
            });
            //选中商品
            $(document).on('click', '.btn-goods-select', function () {
                let goods_ids = Table.api.selectedids(table);
                parent.Layer.prompt({title: '输入积分', formType: 3, zIndex: 198910216}, function (score, index) {
                    parent.Layer.close(index);
                    parent.Fast.api.ajax({
                        url: 'shop/exchange/creategoods',
                        data: {
                            goods_ids,
                            score
                        }
                    }, function (res) {
                        parent.Layer.close(parent.Layer.getFrameIndex(window.name));
                        parent.$("#table").bootstrapTable('refresh', {});
                    })
                });
            });
            // 为表格绑定事件
            Table.api.bindevent(table);
        },
        recyclebin: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    'dragsort_url': ''
                }
            });

            var table = $("#table");

            // 初始化表格
            table.bootstrapTable({
                url: 'shop/goods/recyclebin' + location.search,
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
                            field: 'title',
                            title: __('Title'),
                            align: 'left'
                        },
                        {
                            field: 'deletetime',
                            title: __('Deletetime'),
                            operate: 'RANGE',
                            addclass: 'datetimerange',
                            formatter: Table.api.formatter.datetime
                        },
                        {
                            field: 'operate',
                            width: '130px',
                            title: __('Operate'),
                            table: table,
                            events: Table.api.events.operate,
                            buttons: [{
                                name: 'Restore',
                                text: __('Restore'),
                                classname: 'btn btn-xs btn-info btn-ajax btn-restoreit',
                                icon: 'fa fa-rotate-left',
                                url: 'shop/goods/restore',
                                refresh: true
                            },
                                {
                                    name: 'Destroy',
                                    text: __('Destroy'),
                                    classname: 'btn btn-xs btn-danger btn-ajax btn-destroyit',
                                    icon: 'fa fa-times',
                                    url: 'shop/goods/destroy',
                                    refresh: true
                                }
                            ],
                            formatter: Table.api.formatter.operate
                        }
                    ]
                ]
            });

            // 为表格绑定事件
            Table.api.bindevent(table);
        },
        getAttribute: function (category_id, attribute_ids = []) {
            $.get('shop/attribute/attrs?category_id=' + category_id, function (res) {
                const {code, data, msg} = res;
                if (code) {
                    $('#attributes').html(data.length ? Template('attributetpl', {row: data, attribute_ids}) : ' <input name="row[attribute_ids][0][]" type="hidden" value="">');
                    var instance = $("form[data-toggle='validator']").data("validator");
                    $('#attributes input').each(function () {
                        instance._parse(this);
                    });
                } else {
                    Toastr.error(msg);
                }
            })
        },
        add: function () {
            let that = this;
            $('#c-category_id').on('change', function () {
                let category_id = $('#c-category_id').val();
                that.getAttribute(category_id);
            });
            Controller.api.bindevent();
            Controller.api.add_sku();
        },
        edit: function () {
            let that = this;
            $('#c-category_id').on('change', function () {
                let category_id = $('#c-category_id').val();
                that.getAttribute(category_id);
            });
            if (Config.goods && Config.goods.category_id) {
                this.getAttribute(Config.goods.category_id, Config.goods.attribute_ids ? Config.goods.attribute_ids.split(',') : []);
            }
            Controller.api.bindevent();
            Controller.api.add_sku();
        },
        api: {
            bindevent: function () {

                $(document).on("click", ".btn-legal", function (a) {
                    Fast.api.ajax({
                        url: "shop/ajax/check_content_islegal",
                        data: {content: $("#c-content").val()}
                    }, function (data, ret) {

                    }, function (data, ret) {
                        if ($.isArray(data)) {
                            Layer.alert(__('Banned words') + "：" + data.join(","));
                        }
                    });
                });
                $(document).on("click", ".btn-keywords", function (a) {
                    Fast.api.ajax({
                        url: "shop/ajax/get_content_keywords",
                        data: {title: $("#c-title").val(), content: $("#c-content").val()}
                    }, function (data, ret) {
                        $("#c-keywords").val(data.keywords);
                        $("#c-description").val(data.description);
                    });
                });

                Form.api.bindevent($("form[role=form]"), function (data, ret) {

                }, function (data, ret) {

                }, function (success, error) {
                    let skus = '[]', spec = '[]';
                    if (vm && vm.tableData.length) {
                        for (let [key, res] of vm.tableData.entries()) {
                            if (!res.skus || res.skus.some(item => !item)) {
                                Toastr.error('请输入属性名称');
                                return false;
                            }
                            let {marketprice, price, stocks} = res;
                            if ((marketprice > 0 || price > 0 || stocks > 0) && parseFloat(marketprice) <= parseFloat(price)) {
                                Toastr.error('市场价必须大于销售价');
                                return false;
                            }
                            //替换删除的数据
                            if (res.is_del) {
                                vm.$set(vm.tableData[key], 'goods_sn', '');
                                vm.$set(vm.tableData[key], 'price', 0);
                                vm.$set(vm.tableData[key], 'marketprice', 0);
                                vm.$set(vm.tableData[key], 'stocks', 0);
                            }
                        }
                        skus = JSON.stringify(vm.tableData);
                        spec = JSON.stringify(vm.specList);
                    }
                    //绑定商品属性
                    let html = `<textarea id="c-skus" class="form-control hide" rows="5" name="row[skus]" cols="50">${skus}</textarea>
                    <textarea id="c-spec" class="form-control hide" rows="5" name="row[spec]" cols="50">${spec}</textarea>`;
                    this.find('#goods-sku').html(html);
                    //提交表单
                    Form.api.submit(this, success, error);
                    return false;
                });

                require(['backend/shop/card'], function (Card) {
                    Card.api.bindcardevent();
                });
            },
            bindUpload: function () {
                if ($('.goods-sku-table table td.td-img button.faupload:not([initialized])').length === 0) {
                    return;
                }
                clearTimeout(si);
                si = setTimeout(function () {

                    let doms = $('.goods-sku-table table td.td-img').toArray();

                    function uploadButtonTask(deadline) {
                        while ((deadline.timeRemaining() > 0 || deadline.didTimeout) && doms.length > 0) {
                            bindEvent();
                        }
                        if (doms.length > 0)
                            requestIdleCallback(uploadButtonTask);
                    }

                    function bindEvent() {
                        var dom = doms.shift();
                        $(".faselect,.fachoose", dom).off('click');
                        Form.events.plupload(dom);
                        Form.events.faselect(dom);
                    }

                    requestIdleCallback(uploadButtonTask, {timeout: 1000});
                }, 250);
            },
            add_sku: function () {
                //移除属性的
                $('.td-img').find('.faupload').removeAttr('initialized');
                require(['../addons/shop/js/vue.min'], function (Vue) {
                    vm = new Vue({
                        el: '#vue-app',
                        computed: {
                            specValueText() {
                                return (skus, k) => {
                                    return !skus || typeof skus[k] == 'undefined' ? '' : skus[k];
                                }
                            },
                            contentHtml() {
                                return field => {
                                    return `<div class='input-group'>
                                    <input class='form-control' type='text' value=''/>
                                    <div class='input-group-btn'>
                                        <span class='btn btn-success sku-confirm' data-field='${field}'>
                                           确定
                                        </span>
                                    </div>
                                </div>`;
                                }
                            }
                        },
                        watch: {
                            specList: {
                                handler: function (val) {
                                    this.renderTableData(val);
                                },
                                deep: true
                            }
                        },
                        data() {
                            return {
                                spec_name: '',
                                specList: [],
                                tableData: [],
                                result: [],
                                skus: [] //
                            }
                        },
                        mounted() {
                            let that = this;
                            that.init();
                            //批量设置
                            this.$nextTick(function () {
                                $('body').on('click', function (e) {
                                    if (!$(e.target).hasClass('multiple-edit') &&
                                        $(e.target).parents('.multiple-edit').length === 0 &&
                                        $(e.target).parents('.popover.in').length === 0) {
                                        $('.multiple-edit').popover('hide');
                                    }
                                });
                                $(".multiple-edit").popover({
                                    sanitize: false,
                                    container: "table",
                                    html: true,
                                    placement: "top",
                                    trigger: 'manual'
                                }).on('click', function (e) {
                                    $(".popover").hide();
                                    $(this).popover('show');
                                });
                                $(document).on('click', '.sku-confirm', function () {
                                    let value = $(this).parent().prev().val().trim();
                                    let field = $(this).data('field');
                                    if (field != 'goods_sn' && Number.isNaN(parseFloat(value))) {
                                        Toastr.error('请输入数字');
                                        return;
                                    }
                                    for (let [index] of that.tableData.entries()) {
                                        that.$set(that.tableData[index], field, value);
                                    }
                                });
                                require(['selectpage'], function () {
                                    $('.selectpage', $('.spec-template')).selectPage({
                                        eAjaxSuccess: function (data) {
                                            data.totalRow = data.total;
                                            return data;
                                        },
                                        eSelect: function (row) {
                                            let spec_names = row.spec_names.split(';');
                                            let spec_values = row.spec_values.split(';');
                                            let list = [];
                                            for (let [i, v] of spec_names.entries()) {
                                                list.push({
                                                    name: v,
                                                    value: spec_values[i].split(',')
                                                });
                                            }
                                            that.tableData = [];
                                            that.skus = [];
                                            setTimeout(function () {
                                                that.specList = list;
                                            }, 100);
                                        }
                                    });
                                });
                            })
                        },
                        methods: {
                            init() {
                                let skus = [];
                                if (Config.goods_skus && Config.goods_skus.length) {
                                    let specList = [];
                                    let specName = {};
                                    for (let item of Config.goods_skus) {
                                        let sku_attr = item.sku_attr.split(',');
                                        let attr = [];
                                        for (let res of sku_attr) {
                                            let sku = res.split(':');
                                            attr.push(sku[1]);
                                            //属性名
                                            if (!specName[sku[0]]) {
                                                specName[sku[0]] = [];
                                            }
                                            if (!specName[sku[0]].includes(sku[1])) {
                                                specName[sku[0]].push(sku[1]);
                                            }
                                        }
                                        skus[attr] = item;
                                    }
                                    for (let i in specName) {
                                        specList.push({
                                            name: i,
                                            value: specName[i]
                                        });
                                    }
                                    this.skus = skus;
                                    this.specList = specList;
                                }
                            },
                            addSpec() {
                                if (!this.spec_name.trim()) {
                                    Toastr.error('请输入规格名称');
                                    return;
                                }
                                if (this.specList.some(item => item.name == this.spec_name)) {
                                    Toastr.error('已存在规格名称');
                                    return;
                                }
                                this.specList.push({
                                    name: this.spec_name,
                                    value: []
                                });
                                this.spec_name = '';
                            },
                            addSpecValue(key) {
                                this.specList[key].value.push('');
                            },
                            removeSpecValue(key, index) {
                                this.specList[key].value.splice(index, 1);
                            },
                            //渲染表格数据
                            renderTableData(list) {
                                const goods_goods_sn = $('#c-goods_sn').val();
                                const goods_marketprice = $('#c-marketprice').val();
                                const goods_price = $('#c-price').val();
                                let columns = [];
                                this.result = [];
                                this.resetSpec(list, 0);
                                //渲染表格数据
                                this.result.forEach((item, index) => {
                                    let su = this.skus[item];
                                    let row = {
                                        skus: item ? item.split(',') : [],
                                        goods_sn: goods_goods_sn,
                                        image: '',
                                        price: goods_price,
                                        marketprice: goods_marketprice,
                                        stocks: 0,
                                        is_del: false
                                    };
                                    //编辑赋值
                                    if (su) {
                                        Object.assign(row, su);
                                    }
                                    let old = this.tableData[index];
                                    //是否用原数据赋值
                                    if (old) {
                                        for (let i in row) {
                                            if (!row[i] && old[i]) {
                                                row[i] = old[i];
                                            }
                                        }
                                    }
                                    //为零的置空
                                    let {marketprice, price, stocks} = row;
                                    if (marketprice == 0 && price == 0 && stocks == 0) {
                                        row.marketprice = row.price = row.stocks = row.goods_sn = '';
                                        row.is_del = true;
                                    }
                                    columns.push(row);
                                });
                                this.tableData = columns;
                                //更新dom，加载事件
                                this.$nextTick(function () {
                                    Controller.api.bindUpload();
                                });
                            },
                            removeSpec(key) {
                                this.specList.splice(key, 1);
                            },
                            del(index) {
                                this.$set(this.tableData[index], 'is_del', true);
                            },
                            restore(index) {
                                this.$set(this.tableData[index], 'is_del', false);
                            },
                            //组合规格属性
                            resetSpec(list, index) {
                                if (list[index] != undefined) {
                                    let value = list[index].value;
                                    if (!index) {
                                        this.result = value;
                                    } else {
                                        let res = [];
                                        for (let i of this.result) {
                                            for (let j of value) {
                                                res.push(i + ',' + j);
                                            }
                                        }
                                        if (res.length) {
                                            this.result = res;
                                        }
                                    }
                                    this.resetSpec(list, ++index);
                                }
                            }
                        }
                    });
                });
                //情况属性
                $(document).on('click', '.btn-del-sku', function () {
                    vm.specList = [];
                    vm.tableData = [];
                });
                //监听图片变化赋值
                $(document).on('change', '.sku-images', function () {
                    let index = $(this).data('index');
                    let value = $(this).val();
                    vm.tableData[index].image = value;
                });

            },
            content: function (value, row, index) {
                var width = this.width != undefined ? (this.width.match(/^\d+$/) ? this.width + "px" : this.width) : "350px";
                return "<div style='white-space: nowrap; text-align:left; text-overflow:ellipsis; overflow: hidden; max-width:" + width + ";' title='" + value + "' data-toggle='tooltip' data-placement='right'>" + value + "</div>";
            },
        }
    };
    return Controller;
});
