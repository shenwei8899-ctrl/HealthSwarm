define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/coupon_condition/index' + location.search,
                    add_url: 'shop/coupon_condition/add',
                    edit_url: 'shop/coupon_condition/edit',
                    del_url: 'shop/coupon_condition/del',
                    multi_url: 'shop/coupon_condition/multi',
                    import_url: 'shop/coupon_condition/import',
                    table: 'shop_coupon_condition',
                }
            });

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
                        {field: 'name', title: __('Name'), operate: 'LIKE'},
                        {field: 'type', title: __('Type'), searchList: {"0":__('Type 0'),"1":__('Type 1'),"2":__('Type 2'),"3":__('Type 3'),"4":__('Type 4'),"5":__('Type 5'),"6":__('Type 6')}, formatter: Table.api.formatter.normal},
                        {field: 'content', title: __('Content'), operate: 'LIKE'},
                        {field: 'createtime', title: __('Createtime'), operate:'RANGE', addclass:'datetimerange', autocomplete:false, formatter: Table.api.formatter.datetime},
                        {field: 'updatetime', title: __('Updatetime'), operate:'RANGE', addclass:'datetimerange', autocomplete:false, formatter: Table.api.formatter.datetime},
                        {field: 'operate', title: __('Operate'), table: table, events: Table.api.events.operate, formatter: Table.api.formatter.operate}
                    ]
                ]
            });

            // 为表格绑定事件
            Table.api.bindevent(table);
        },
        //条件
        condition: function () {
            $('#c-type').on('change', function () {
                let value = $(this).val();
                console.dir(value)
                if (value == 2 || value == 3) {
                    $('.condition').addClass('hide');
                } else {
                    $('.condition').removeClass('hide');
                }
                let dom = $('#edit-condition-data');
                let data = '';
                if (dom && dom.data('condition') == value) {
                    data = dom.val();
                }
                let html = 'deftpl';
                switch (parseInt(value)) {
                    case 1:
                        html = 'goodstpl';
                        break;    
                    case 4:
                        html = 'categorytpl';
                        break; 
                    case 5:
                        html = 'brandtpl';
                        break; 
                    case 6:
                        html = 'viptpl';
                        break;             
                    }
                $('#condition-data').html(Template(html,{data}));
                setTimeout(()=>{
                    Form.events.selectpage($("form[role=form]"));
                },100)
            })
        },
        add: function () {
            this.condition();
            Controller.api.bindevent();
        },
        edit: function () {
            this.condition();
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