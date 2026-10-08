define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {
    var vm;
    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/sku_template/index' + location.search,
                    add_url: 'shop/sku_template/add',
                    edit_url: 'shop/sku_template/edit',
                    del_url: 'shop/sku_template/del',
                    multi_url: 'shop/sku_template/multi',
                    import_url: 'shop/sku_template/import',
                    table: 'shop_sku_template',
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
                            field: 'name',
                            title: __('Name'),
                            operate: 'LIKE'
                        },
                        {
                            field: 'spec_names',
                            title: __('Spec_names'),
                            operate: 'LIKE'
                        },
                        {
                            field: 'spec_values',
                            title: __('Spec_values'),
                            operate: 'LIKE'
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
        vue: function (url, callback) {
            callback = callback || $.noop();
            require(['../addons/shop/js/vue.min'], function (Vue) {
                vm = new Vue({
                    el: '#app',
                    data() {
                        return {
                            spec_name: '',
                            specList: [],
                        }
                    },
                    mounted() {
                        this.$nextTick(callback);
                    },
                    methods: {
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
                            if (this.specList[key] && this.specList[key].value.indexOf()) ;
                            this.specList[key].value.push('');
                        },
                        removeSpecValue(key, index) {
                            this.specList[key].value.splice(index, 1);
                        },
                        removeSpec(key) {
                            this.specList.splice(key, 1);
                        },
                    }
                })
            });
            //提交数据
            $(document).on('click', '.btn-add-sku', function () {
                if (vm.specList.length) {
                    for (let item of vm.specList) {
                        for (let val of item.value) {
                            if (!val.trim()) {
                                Toastr.error('请输入' + item.name + '的属性值');
                                return;
                            }
                        }
                    }
                }
                let name = $('#c-name').val();
                if (!name.trim()) {
                    Toastr.error('请输入模板名称');
                    return;
                }
                $.post(url, {
                    spec: vm.specList,
                    name: name
                }, function (res) {
                    if (res.code == 1) {
                        parent.Toastr.success(res.msg);
                        var index = parent.Layer.getFrameIndex(window.name);
                        parent.Layer.close(index);
                        parent.$("#table").bootstrapTable('refresh', {});
                    } else {
                        Toastr.error(res.msg);
                    }
                });
            });
        },
        add: function () {
            this.vue('shop/sku_template/add');
            Controller.api.bindevent();
        },
        edit: function () {
            $('#c-name').val(Config.row.name);
            this.vue('shop/sku_template/edit/ids/' + Config.row.id, function () {
                let spec_names = Config.row.spec_names.split(';');
                let spec_values = Config.row.spec_values.split(';');
                let list = [];
                for (let [i, v] of spec_names.entries()) {
                    list.push({
                        name: v,
                        value: spec_values[i].split(',')
                    });
                }
                vm.specList = list;
            });
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
