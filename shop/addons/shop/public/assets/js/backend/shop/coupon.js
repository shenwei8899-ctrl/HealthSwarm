define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/coupon/index' + location.search,
                    add_url: 'shop/coupon/add',
                    edit_url: 'shop/coupon/edit',
                    del_url: 'shop/coupon/del',
                    multi_url: 'shop/coupon/multi',
                    import_url: 'shop/coupon/import',
                    table: 'shop_coupon',
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
                            field: 'condition_name',
                            title: __('Condition'),
                            operate: false
                        },
                        {
                            field: 'result',
                            title: __('Result'),
                            visible: false,
                            searchList: {
                                "0": __('Result 0'),
                                "1": __('Result 1')
                            },
                            formatter: Table.api.formatter.normal
                        },
                        {
                            field: 'result_data',
                            title: __('Result'),
                            operate: false,
                            formatter: function (value, row) {
                                if (row.result == 0) {
                                    return '订单满' + row.result_data.money + '元，打' + row.result_data.number + '折';
                                } else {
                                    return '订单满' + row.result_data.money + '元，减' + row.result_data.number + '元';
                                }
                            }
                        },
                        // {
                        //     field: 'result_data',
                        //     title: __('Result_data'),
                        //     operate: 'LIKE'
                        // },
                        {
                            field: 'give_num',
                            title: __('Give_num'),
                            operate: 'BETWEEN'
                        },
                        {
                            field: 'allow_num',
                            title: __('Allow_num'),
                            operate: 'BETWEEN'
                        },
                        {
                            field: 'received_num',
                            title: __('Received_num'),
                            operate: 'BETWEEN'
                        },
                        {
                            field: 'is_private',
                            title: __('Is_private'),
                            searchList: {
                                "yes": __('Is_private yes'),
                                "no": __('Is_private no')
                            },
                            formatter: Table.api.formatter.normal
                        },
                        {
                            field: 'is_open',
                            title: __('Is_open'),
                            searchList: {
                                "0": __('Is_open 0'),
                                "1": __('Is_open 1')
                            },
                            formatter: Table.api.formatter.normal
                        },
                        {
                            field: 'url', title: __('Url'), operate: false, formatter: function (value, row, index) {
                                return '<a href="' + row.url + '" target="_blank" class="btn btn-default btn-xs"><i class="fa fa-link"></i></a>';
                            }
                        },
                        {
                            field: 'status', title: __('Status'), operate: false, formatter: function (value, row, index) {
                                return row.expired ? "<span class='text-danger'>已过期</span>" : "<span class='text-success'>正常</span>";
                            }
                        },
                        {
                            field: 'receive_times',
                            title: __('Receive_times'),
                            operate: 'RANGE',
                            addclass: 'datetimerange',
                            autocomplete: false
                        },
                        {
                            field: 'use_times',
                            title: __('Use_times'),
                            operate: 'RANGE',
                            addclass: 'datetimerange',
                            autocomplete: false,
                            formatter: function (value, row) {
                                if (row.mode == 'fixation') {
                                    return value + '天';
                                } else {
                                    return value;
                                }
                            }
                        },
                        {
                            field: 'createtime',
                            title: __('Createtime'),
                            operate: 'RANGE',
                            addclass: 'datetimerange',
                            autocomplete: false,
                            visible: false,
                            formatter: Table.api.formatter.datetime
                        },
                        {
                            field: 'updatetime',
                            title: __('Updatetime'),
                            operate: 'RANGE',
                            addclass: 'datetimerange',
                            autocomplete: false,
                            visible: false,
                            operate: false,
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
        result: function () {
            //优惠模式切换
            $('#c-result').on('change', function () {
                if ($(this).val() == 0) {
                    $('#text-a').html('打');
                    $('#text-b').html('折');
                } else {
                    $('#text-a').html('减');
                    $('#text-b').html('元');
                }
            })
            //去掉日期的选项
            $('#c-receive_times').data('ranges', 1);
            $('#c-use_times').data('ranges', 1);

            let receive_times1 = '';
            let receive_times2 = '';
            let use_times1 = '';
            let use_times2 = '';

            //有效期模式切换
            $('.modes').click(function () {
                var value = $(this).val()  //获取选中的radio的值

                if (value != 'fixation') {//固定日期
                    receive_times2 = $('#c-receive_times').val();
                    use_times2 = $('#c-use_times').val();
                    $('#modetpl').html(Template('datestpl', {receive_times: receive_times1, use_times: use_times1}));
                    //去掉日期的选项
                    $('#c-receive_times').data('ranges', 1);
                    $('#c-use_times').data('ranges', 1);
                    Form.events.daterangepicker($("form[role=form]"));
                } else {//天数
                    receive_times1 = $('#c-receive_times').val();
                    use_times1 = $('#c-use_times').val();
                    $('#modetpl').html(Template('fixationtpl', {receive_times: receive_times2, use_times: use_times2}));
                }
            });
        },
        add: function () {
            this.result();
            Controller.api.bindevent();
        },
        edit: function () {
            this.result();
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
