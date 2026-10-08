define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    if (Config.shop && Config.shop.printtype == 'clodop') {
        require([Config.shop.clodop_ip_port + '/CLodopfuncs.js']);
    }
    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/order/index' + location.search,
                    // add_url: 'shop/order/add',
                    // edit_url: 'shop/order/edit',
                    del_url: 'shop/order/del',
                    multi_url: 'shop/order/multi',
                    import_url: 'shop/order/import',
                    table: 'shop_order',
                }
            });

            var table = $("#table");

            //当双击单元格时
            table.on('dbl-click-row.bs.table', function (e, row, element, field) {
                $(".btn-detail", element).trigger("click");
            });

            // 初始化表格
            table.bootstrapTable({
                url: $.fn.bootstrapTable.defaults.extend.index_url,
                pk: 'id',
                sortName: 'id',
                fixedColumns: true,
                fixedRightNumber: 1,
                columns: [
                    [{
                        checkbox: true
                    },
                        {
                            field: 'id',
                            title: __('Id')
                        },
                        {
                            field: 'order_sn',
                            title: __('Order_sn'),
                            operate: 'LIKE'
                        },
                        {
                            field: 'user_id',
                            title: __('User_id'),
                            operate: false, formatter: Table.api.formatter.search
                        },
                        {
                            field: 'receiver',
                            title: __('Receiver'),
                            operate: 'LIKE'
                        },
                        {
                            field: 'address',
                            title: __('Address'),
                            operate: 'LIKE'
                        },
                        {
                            field: 'zipcode',
                            title: __('Zipcode'),
                            operate: 'LIKE',
                            visible: false,
                        },
                        {
                            field: 'mobile',
                            title: __('Mobile'),
                            operate: 'LIKE'
                        },
                        {
                            field: 'amount',
                            title: __('Amount'),
                            operate: 'BETWEEN'
                        },
                        {
                            field: 'goodsprice',
                            title: __('Goodsprice'),
                            operate: 'BETWEEN'
                        },
                        {
                            field: 'discount',
                            title: __('Discount'),
                            operate: 'BETWEEN'
                        },
                        {
                            field: 'shippingfee',
                            title: __('Shippingfee'),
                            operate: 'BETWEEN'
                        },
                        {
                            field: 'saleamount',
                            title: __('Saleamount'),
                            operate: 'BETWEEN'
                        },
                        {
                            field: 'payamount',
                            title: __('Payamount'),
                            operate: 'BETWEEN'
                        },
                        {
                            field: 'paytype',
                            title: __('Paytype'),
                            operate: 'LIKE'
                        },
                        {
                            field: 'method',
                            title: __('Method'),
                            operate: 'LIKE'
                        },
                        {
                            field: 'transactionid',
                            title: __('Transactionid'),
                            operate: 'LIKE'
                        },
                        {
                            field: 'expressname',
                            title: __('Expressname'),
                            operate: 'LIKE'
                        },
                        {
                            field: 'expressno',
                            title: __('Expressno'),
                            operate: 'LIKE'
                        },
                        {
                            field: 'orderstate',
                            title: __('Orderstate'),
                            searchList: {
                                "0": __('Orderstate 0'),
                                "1": __('Orderstate 1'),
                                "2": __('Orderstate 2'),
                                "3": __('Orderstate 3'),
                                "4": __('Orderstate 4'),
                            },
                            formatter: Table.api.formatter.normal
                        },
                        {
                            field: 'shippingstate',
                            title: __('Shippingstate'),
                            searchList: {
                                "0": __('Shippingstate 0'),
                                "1": __('Shippingstate 1'),
                                "2": __('Shippingstate 2')
                            },
                            formatter: Table.api.formatter.normal
                        },
                        {
                            field: 'paystate',
                            title: __('Paystate'),
                            searchList: {
                                "0": __('Paystate 0'),
                                "1": __('Paystate 1')
                            },
                            formatter: Table.api.formatter.normal
                        },
                        {
                            field: 'memo',
                            title: __('Memo'),
                            operate: 'LIKE'
                        },
                        {
                            field: 'status',
                            title: __('Status'),
                            searchList: {
                                "normal": __('Status normal'),
                                "hidden": __('Status hidden')
                            },
                            formatter: Table.api.formatter.status
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
                            field: 'expiretime',
                            title: __('Expiretime'),
                            operate: 'RANGE',
                            addclass: 'datetimerange',
                            autocomplete: false,
                            formatter: Table.api.formatter.datetime
                        },
                        {
                            field: 'paytime',
                            title: __('Paytime'),
                            operate: 'RANGE',
                            addclass: 'datetimerange',
                            autocomplete: false,
                            formatter: Table.api.formatter.datetime
                        },
                        {
                            field: 'refundtime',
                            title: __('Refundtime'),
                            operate: 'RANGE',
                            addclass: 'datetimerange',
                            autocomplete: false,
                            formatter: Table.api.formatter.datetime
                        },
                        {
                            field: 'shippingtime',
                            title: __('Shippingtime'),
                            operate: 'RANGE',
                            addclass: 'datetimerange',
                            autocomplete: false,
                            formatter: Table.api.formatter.datetime
                        },
                        {
                            field: 'receivetime',
                            title: __('Receivetime'),
                            operate: 'RANGE',
                            addclass: 'datetimerange',
                            autocomplete: false,
                            formatter: Table.api.formatter.datetime
                        },
                        {
                            field: 'canceltime',
                            title: __('Canceltime'),
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
                            formatter: Table.api.formatter.operate,
                            clickToSelect: false,
                            buttons: [{
                                name: '取消电子面单',
                                title: __('取消电子面单'),
                                classname: 'btn btn-xs btn-success btn-ajax',
                                text: '取消电子面单',
                                icon: 'fa fa-sticky-note-o',
                                extend: 'data-area=\'["90%","90%"]\'',
                                url: 'shop/order/cancel_electronics/oe_id/{oe_id}',
                                hidden: function (row) {
                                    return !row.print_template;
                                },
                                success: function () {
                                    table.bootstrapTable('refresh', {});
                                }
                            }, {
                                name: '订单详情',
                                title: __('订单详情'),
                                classname: 'btn btn-xs btn-primary btn-dialog btn-detail',
                                text: '订单详情',
                                icon: 'fa fa-sticky-note-o',
                                extend: 'data-area=\'["90%","90%"]\'',
                                url: 'shop/order/detail'
                            }]
                        }
                    ]
                ]
            });

            var options = table.bootstrapTable('getOptions');
            var queryParams = options.queryParams;
            // 绑定TAB事件
            $('.panel-heading a[data-toggle="tab"]').on('shown.bs.tab', function (e) {
                var value = $(this).data("value");
                options = table.bootstrapTable('getOptions');
                options.pageNumber = 1;
                options.queryParams = function (params) {
                    if (value) {
                        params.filter = JSON.stringify(value);
                        let op = {}
                        for (let i in value) {
                            op[i] = '=';
                        }
                        params.op = JSON.stringify(op);
                    }
                    params = queryParams.call(this, params);
                    return params;
                };
                table.bootstrapTable('refresh', {});
                return false;
            });
            // 批量打印电子面单
            $(document).on('click', '.btn-print-multiple-electronic', function () {
                let ids = Table.api.selectedids(table);
                if (!ids.length) {
                    Toastr.error('请选择需打印的订单');
                    return;
                }
                Layer.index = 0;
                Layer.open({
                    id: 'electronic',
                    title: '请选择电子面单模板',
                    content: Template("electronictpl", {ids: ids}),
                    zIndex: 8,
                    btn: ["开始打印", "取消"],
                    success: function (layero, index) {
                        Form.events.selectpage(layero);
                    },
                    yes: function (index, layero) {
                        let electronics_id = $('#electronics_id', layero).val();
                        if (!electronics_id) {
                            Toastr.error('请选择电子面单模板');
                            return;
                        }
                        Fast.api.ajax(
                            {
                                url: 'shop/order/prints',
                                data: {
                                    ids: ids.join('_'),
                                    electronics_id: electronics_id
                                }
                            }, function (data) {
                                let html = '';
                                data.forEach(item => {
                                    //模板，获取成功
                                    if (item.Success) {
                                        html += '<div style="page-break-after: always">';
                                        html += item.PrintTemplate;
                                        html += '</div>';
                                    }
                                });
                                html && Controller.api.print('电子面单打印', html);
                                return false;
                            }
                        );
                    }
                });
            });
            // 批量打印发货单
            $(document).on('click', '.btn-print-multiple-invoice', function () {
                let order_ids = Table.api.selectedids(table);
                if (!order_ids.length) {
                    Toastr.error('请选择需打印的订单');
                    return;
                }
                Fast.api.ajax({
                    url: 'shop/order/orderList',
                    data: {
                        ids: order_ids
                    }
                }, function (data) {
                    var html = Template("invoicetpl", data);
                    Controller.api.print('发货单打印', html);
                    return false;
                })
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
                url: 'shop/order/recyclebin' + location.search,
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
                            field: 'order_sn',
                            title: __('Order_sn'),
                            operate: 'LIKE'
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
                                url: 'shop/order/restore',
                                refresh: true
                            },
                                {
                                    name: 'Destroy',
                                    text: __('Destroy'),
                                    classname: 'btn btn-xs btn-danger btn-ajax btn-destroyit',
                                    icon: 'fa fa-times',
                                    url: 'shop/order/destroy',
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
        add: function () {
            Controller.api.bindevent();
        },
        edit: function () {
            Controller.api.bindevent();
        },
        detail: function () {
            $(document).on("click", ".btn-refresh", function () {
                setTimeout(function () {
                    location.reload();
                }, 1000);
            });
            //取消，支付
            $(document).on('click', '.btn-status-click', function () {
                let order = $(this).data('order');
                let order_id = $('#order_id').val();
                $.post('shop/order/edit_status', {
                    order_id,
                    ...order
                }, function (res) {
                    if (res.code == 1) {
                        window.location.reload();
                        parent.Toastr.success(res.msg);
                    } else {
                        parent.Toastr.error(res.msg);
                    }
                })
            });

            //发货
            $(document).on('click', '.btn-deliver', function () {
                let expressname = $(this).data('expressname');
                let expressno = $(this).data('expressno');
                let html = Template('expresstpl', {expressname, expressno});
                let type = $(this).data('type');
                layer.open({
                    type: 1,
                    skin: 'layui-layer-demo', //样式类名
                    title: type == 0 ? '发货' : '修改快递信息',
                    anim: 2,
                    area: ['400px', '300px'],
                    shadeClose: 1, //开启遮罩关闭
                    content: html,
                    btn: ['确认', '取消'],
                    zIndex: 10,
                    yes: function (index) {
                        let expressname = ($('#expressname').val()).trim();
                        let expressno = ($('#expressno').val()).trim();
                        if (!expressname) {
                            Toastr.error('请输入快递名称');
                            return;
                        }
                        if (!expressno) {
                            Toastr.error('请输入快递单号');
                            return;
                        }
                        let order_id = $('#order_id').val();
                        $.post('shop/order/deliver', {
                            order_id,
                            expressname,
                            expressno,
                            type
                        }, function (res) {
                            if (res.code == 1) {
                                window.location.reload();
                                Toastr.success(res.msg);
                                Layer.close(index);
                            } else {
                                Toastr.error(res.msg);
                            }
                        })

                    },
                    success: function (layero, index) {
                        Form.api.bindevent($('.shipper'));
                    }
                });
            });

            //编辑备注
            $('#app').delegate('.btn-edit,.btn-cancel,.btn-save', 'click', function () {
                let status = $(this).data('status');
                switch (status) {
                    case 'edit':
                        $(this).nextAll('a').removeClass('hide');
                        $(this).parent().prev().children('div').addClass('hide');
                        $(this).parent().prev().children('input').removeClass('hide');
                        $(this).addClass('hide');
                        break;
                    case 'cancel':
                        $(this).prev().removeClass('hide');
                        $(this).next().addClass('hide');
                        $(this).parent().prev().children('div').removeClass('hide');
                        $(this).parent().prev().children('input').addClass('hide');
                        $(this).addClass('hide');
                        break;
                    case 'save':
                        let val = $(this).parent().prev().children('input').val();
                        let field = $(this).data('field');
                        let id = $(this).data('id');
                        $.post('shop/order/edit_info', {
                            id: id,
                            field: field,
                            value: val
                        }, function (res) {
                            if (res.code == 1) {
                                window.location.reload();
                                parent.Toastr.success(res.msg);
                            } else {
                                parent.Toastr.error(res.msg);
                            }
                        })
                        break;
                }
            });


            function moneyPrompt(value) {
                return new Promise((resolve, reject) => {
                    layer.prompt({
                        title: '确认退款金额',
                        formType: 0,
                        value: value
                    }, function (pass, index) {
                        layer.close(index);
                        resolve(pass)
                    });
                })
            }

            function reasonPrompt() {
                return new Promise((resolve, reject) => {
                    layer.prompt({
                        title: '拒绝原因',
                        formType: 2
                    }, function (pass, index) {
                        layer.close(index);
                        resolve(pass)
                    });
                })
            }

            Form.api.bindevent($('.electronics'));

            // 打印快递电子面单
            $(document).on('click', '.btn-print-electronic', function () {
                let order_id = $(this).data('id');
                let electronics_id = $('#electronics_id').val();
                if (!electronics_id) {
                    Toastr.error('请选择电子面单模板');
                    return;
                }
                Fast.api.ajax('shop/order/electronics?order_id=' + order_id + '&electronics_id=' + electronics_id, function (res) {
                    Controller.api.print('电子面单打印', res.PrintTemplate);
                    return false;
                });
            });


            // 打印发货单
            $(document).on('click', '.btn-print-invoice', function () {
                let order_ids = $(this).data("id");
                Fast.api.ajax({
                    url: 'shop/order/orderList',
                    data: {
                        ids: order_ids
                    }
                }, function (data) {
                    var html = Template("invoicetpl", data);
                    Controller.api.print('发货单打印', html);
                    return false;
                })
            });

            //查询物流
            $(document).on('click', '.btn-logistics', function () {
                parent.layer.open({
                    type: 2,
                    shade: false,
                    zIndex: 9999999999,
                    title: '物流信息',
                    area: ['90%', '90%'],
                    content: 'https://www.kuaidi100.com/all/htky.shtml?mscomnu=' + $(this).data('expressno')
                })
            })
        },
        //批量打印
        prints: function () {
            let that = this;

            let ids = Config.order_ids;


            Controller.api.bindevent();
        },
        api: {
            bindevent: function () {
                Form.api.bindevent($("form[role=form]"));
            },
            print: function (title, html) {
                if (Config.shop.printtype == 'system') {
                    require(['../addons/shop/js/print-html-element.min'], function (PHE) {
                        PHE.printHtml(html, {
                            stylesheets: [],
                            styles: '@page {margin: 5px;}'
                        });
                    });
                } else {
                    if (typeof LODOP == 'undefined') {
                        Toastr.error('请检查C-Lodop打印组件是否安装并启动');
                        return;
                    }
                    LODOP.PRINT_INIT(title); //初始化
                    LODOP.ADD_PRINT_HTM(0, 0, "100%", "100%", html);
                    if (Config.shop.clodop_print_view == '1') {
                        LODOP.PREVIEW();
                    } else if (Config.shop.clodop_print_view == '2') {
                        LODOP.PRINT_DESIGN();
                    } else {
                        LODOP.PRINT();
                    }
                }
                return;
            }
        }
    };
    return Controller;
});
