define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/template_msg/index' + location.search,
                    add_url: 'shop/template_msg/add',
                    edit_url: 'shop/template_msg/edit',
                    del_url: 'shop/template_msg/del',
                    multi_url: 'shop/template_msg/multi',
                    import_url: 'shop/template_msg/import',
                    table: 'shop_template_msg',
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
                            field: 'type',
                            title: __('Type'),
                            searchList: {
                                "1": __('Type 1'),
                                "2": __('Type 2'),
                                "3": __('Type 3'),
                                "4": __('Type 4'),
                            },
                            formatter: Table.api.formatter.normal
                        },
                        {
                            field: 'event',
                            title: __('Event'),
                            searchList: {
                                "0": __('Event 0'),
                                "1": __('Event 1'),
                                "2": __('Event 2'),
                                "3": __('Event 3'),
                                "4": __('Event 4')
                            },
                            formatter: Table.api.formatter.normal
                        },
                        {
                            field: 'title',
                            title: __('Title'),
                            operate: 'LIKE'
                        },
                        {
                            field: 'tpl_id',
                            title: __('Tpl_id'),
                            operate: 'LIKE'
                        },                      
                     
                        {
                            field: 'page',
                            title: __('Page'),
                            operate: 'LIKE'
                        },
                        {
                            field: 'switch',
                            title: __('Switch'),
                            searchList: {
                                "1": __('Yes'),
                                "0": __('No')
                            },
                            table: table,
                            formatter: Table.api.formatter.toggle
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
        addOrEdit() {
            $(document).on("fa.event.appendfieldlist", "form[role=form] .btn-append", function (e, obj) {
                Form.events.selectpicker(obj);
            });   
              
            $(document).on('change','#c-type',function(){
                let val = $(this).val();
                if([3,4].includes(parseInt(val))){
                    $('.page_path').addClass('hide');                   
                }else{
                    $('.page_path').removeClass('hide');
                }
                if(val==3){
                    $('.template-extend').removeClass('hide');
                }else{
                    $('.template-extend').addClass('hide');
                }
            })
        },
        add: function () {
            this.addOrEdit();
            Controller.api.bindevent();
        },
        edit: function () {
            this.addOrEdit();
            Controller.api.bindevent();
        },
        api: {
            bindevent: function () {
                $(document).on("click", ".btn-select-page", function (e, obj) {
                    var that = this;
                    Fast.api.open("shop/ajax/get_page_list", "选择路径", {
                        callback: function (data) {
                            $(that).parent().prev().val(data).trigger("change");
                        }
                    })
                });
                Form.api.bindevent($("form[role=form]"));
            }
        }
    };
    return Controller;
});