define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/electronics_order/index' + location.search,
                    add_url: 'shop/electronics_order/add',
                    edit_url: 'shop/electronics_order/edit',
                    del_url: 'shop/electronics_order/del',
                    multi_url: 'shop/electronics_order/multi',
                    import_url: 'shop/electronics_order/import',
                    table: 'shop_electronics_order',
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
                        {checkbox: true},
                        {field: 'id', title: __('Id')},
                        {field: 'title', title: __('Title'), operate: 'LIKE'},
                        {field: 'shipper.name', title: __('Shipper')},
                        {field: 'paytype', title: __('Paytype'), searchList: {"1":__('Paytype 1'),"2":__('Paytype 2'),"3":__('Paytype 3'),"4":__('Paytype 4')}, formatter: Table.api.formatter.normal},
                        {field: 'is_notice', title: __('Is_notice'), searchList: {"0":__('Is_notice 0'),"1":__('Is_notice 1')}, formatter: Table.api.formatter.normal},
                        {field: 'is_return_temp', title: __('Is_return_temp'), searchList: {"0":__('Is_return_temp 0'),"1":__('Is_return_temp 1')}, formatter: Table.api.formatter.normal},
                        {field: 'is_send_message', title: __('Is_send_message'), searchList: {"0":__('Is_send_message 0'),"1":__('Is_send_message 1')}, formatter: Table.api.formatter.normal},
                        {field: 'template_size', title: __('Template_size'), operate: 'LIKE'},
                        {field: 'operate_require', title: __('Operate_require'), operate: 'LIKE'},
                        {field: 'exp_type', title: __('Exp_type'),searchList: {"1":__('Exp_type 1')}, formatter: Table.api.formatter.normal},
                        {field: 'is_return_sign_bill', title: __('Is_return_sign_bill'), searchList: {"0":__('Is_return_sign_bill 0'),"1":__('Is_return_sign_bill 1')}, formatter: Table.api.formatter.normal},
                        {field: 'company', title: __('Company'), operate: 'LIKE'},
                        {field: 'province_name', title: __('Province_name'), operate: 'LIKE'},
                        {field: 'city_name', title: __('City_name'), operate: 'LIKE'},
                        {field: 'exp_area_name', title: __('Exp_area_name'), operate: 'LIKE'},
                        {field: 'address', title: __('Address'), operate: 'LIKE'},
                        {field: 'name', title: __('Name'), operate: 'LIKE'},
                        {field: 'tel', title: __('Tel'), operate: 'LIKE'},
                        {field: 'mobile', title: __('Mobile'), operate: 'LIKE'},
                        {field: 'post_code', title: __('Post_code'), operate: 'LIKE'},
                        {field: 'logistic_code', title: __('Logistic_code'), operate: 'LIKE'},                       
                        {field: 'start_date', title: __('Start_date')},
                        {field: 'end_date', title: __('End_date')},
                        {field: 'remark', title: __('Remark'), operate: 'LIKE'},
                        {field: 'customer_name', title: __('Customer_name'), operate: 'LIKE'},
                        {field: 'customer_pwd', title: __('Customer_pwd'), operate: 'LIKE'},
                        {field: 'send_site', title: __('Send_site'), operate: 'LIKE'},
                        {field: 'send_staff', title: __('Send_staff'), operate: 'LIKE'},
                        {field: 'month_code', title: __('Month_code'), operate: 'LIKE'},
                        {field: 'createtime', title: __('Createtime'), operate:'RANGE', addclass:'datetimerange', autocomplete:false, formatter: Table.api.formatter.datetime},
                        {field: 'updatetime', title: __('Updatetime'), operate:'RANGE', addclass:'datetimerange', autocomplete:false, formatter: Table.api.formatter.datetime},
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