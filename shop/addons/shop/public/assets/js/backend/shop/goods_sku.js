define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {
    var vm;
    var Controller = {

        add: function () {

            require(['../addons/shop/js/vue.min'], function (Vue) {
                vm = new Vue({
                    el: '#app',
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
                                    that.$set(that.tableData[index], field, value)
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
                                            })
                                        }
                                        that.tableData = [];
                                        that.skus = [];
                                        setTimeout(function () {
                                            that.specList = list;
                                        }, 100)
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
                                for (let [key, item] of Config.goods_skus.entries()) {
                                    let sku_attr = item.sku_attr.split(',');
                                    let attr = [];
                                    for (let [index, res] of sku_attr.entries()) {
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
                                    })
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
                            let columns = [];
                            this.result = [];
                            this.resetSpec(list, 0);
                            //渲染表格数据
                            this.result.forEach((item, index) => {
                                let su = this.skus[item];
                                let row = {
                                    skus: item ? item.split(',') : [],
                                    goods_sn: Config.goods.goods_sn,
                                    image: '',
                                    price: Config.goods.price,
                                    marketprice: Config.goods.marketprice,
                                    stocks: 0,
                                    is_del:false
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
                                let {marketprice,price,stocks} = row;
                                if(marketprice==0 && price==0 && stocks ==0){
                                    row.marketprice=row.price=row.stocks =row.goods_sn= '';
                                }
                                columns.push(row);
                            });
                            this.tableData = columns;
                            //更新dom，加载事件
                            this.$nextTick(function () {
                                Controller.api.bindUpload();
                            })
                        },
                        removeSpec(key) {
                            this.specList.splice(key, 1);
                        },
                        del(index){
                            this.$set(this.tableData[index],'is_del',true);
                        },
                        restore(index){
                            this.$set(this.tableData[index],'is_del',false);
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
                                            res.push(i + ',' + j)
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
                })
            })
            //情况属性
            $(document).on('click', '.btn-del-sku', function () {
                vm.specList = [];
                vm.tableData = [];
            })
            //监听图片变化赋值
            $(document).on('change', '.sku-images', function () {
                let index = $(this).data('index');
                let value = $(this).val();
                vm.tableData[index].image = value;
            })
            //提交数据
            $(document).on('click', '.btn-add-sku', function () {
                if (vm.tableData.length) {
                    for (let [key, res] of vm.tableData.entries()) {
                        if (!res.skus || res.skus.some(item => !item)) {
                            Toastr.error('请输入属性名称');
                            return;
                        }
                        let {marketprice,price,stocks} = res;
                        if ((marketprice>0 || price >0 || stocks>0) && parseFloat(marketprice) <= parseFloat(price)) {
                            Toastr.error('市场价必须大于销售价');
                            return;
                        }
                        //替换删除的数据
                        if(res.is_del){
                            vm.$set(vm.tableData[key],'goods_sn',0);
                            vm.$set(vm.tableData[key],'price',0);
                            vm.$set(vm.tableData[key],'marketprice',0);
                            vm.$set(vm.tableData[key],'stocks',0);
                        }
                    }
                }
                $.post('shop/goods_sku/add', {
                    skus: vm.tableData,
                    spec: vm.specList,
                    goods_id: Config.goods.id
                }, function (res) {
                    if (res.code == 1) {
                        parent.Toastr.success(res.msg);
                        var index = parent.Layer.getFrameIndex(window.name);
                        parent.$("#table").bootstrapTable('refresh', {});
                        parent.Layer.close(index);
                    } else {
                        Toastr.error(res.msg);
                    }
                })
            })


        },
        api: {
            bindUpload: function () {
                let doms = $('.td-img');
                for (let i = 0, len = doms.length; i < len; i++) {
                    if (!vm.tableData[i].is_bind) {
                        $(".faselect,.fachoose", doms[i]).off('click');
                        Form.events.plupload(doms[i]);
                        Form.events.faselect(doms[i]);
                    }
                }
            }
        }
    };
    return Controller;
});
