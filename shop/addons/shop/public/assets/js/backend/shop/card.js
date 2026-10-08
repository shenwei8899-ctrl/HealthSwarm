define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {

    var Controller = {
        index: function () {
            // 初始化表格参数配置
            Table.api.init({
                extend: {
                    index_url: 'shop/card/index' + location.search,
                    add_url: 'shop/card/add',
                    edit_url: 'shop/card/edit',
                    del_url: 'shop/card/del',
                    multi_url: 'shop/card/multi',
                    import_url: 'shop/card/import',
                    table: 'shop_card',
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
                        {field: 'title', title: __('Title'), operate: 'LIKE'},
                        {field: 'type', title: __('Type'), searchList: {"0": __('Type 0'), "1": __('Type 1')}, formatter: Table.api.formatter.normal},
                        {field: 'createtime', title: __('Createtime'), operate: 'RANGE', addclass: 'datetimerange', autocomplete: false, formatter: Table.api.formatter.datetime},
                        {field: 'updatetime', title: __('Updatetime'), operate: 'RANGE', addclass: 'datetimerange', autocomplete: false, formatter: Table.api.formatter.datetime},
                        {field: 'status', title: __('Status'), searchList: {"normal": __('Normal'), "hidden": __('Hidden')}, formatter: Table.api.formatter.status},
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
                Controller.api.preview();
                $(document).on('input', '#c-content', function () {
                    Controller.api.preview();
                });
                Form.api.bindevent($("form[role=form]"));
            },
            bindcardevent: function () {
                //替换内容
                let formatHtml = function (oldHtml, newHtml) {
                    let html;
                    if (oldHtml && /<div\sdata\-id="placeholder">(\s|[\r\n]|&nbsp;)*<\/div>/.test(oldHtml)) {
                        html = oldHtml.replace(/<div\sdata\-id="placeholder">(\s|[\r\n]|&nbsp;)*<\/div>/g, newHtml);
                    } else {
                        html = oldHtml + '<p><br></p>' + newHtml;
                    }
                    let str = html.substring(html.length - 10);
                    if (!str.includes('<br')) {
                        html += '<p><br></p>';
                    }
                    return html;
                };

                //插入商品卡片
                let insertHtml = function (html, insert = false) {
                    let editor;
                    if (typeof KindEditor !== 'undefined') {
                        if (insert) {
                            KindEditor.sync("#c-content");
                            KindEditor.html('#c-content', formatHtml(KindEditor('#c-content').val(), html));
                        } else {
                            KindEditor.insertHtml("#c-content", html);
                        }
                    } else if (typeof UM !== 'undefined' && typeof UM.list["c-content"] !== 'undefined') {
                        editor = UM.list["c-content"];
                        if (insert) {
                            editor.setContent(formatHtml(editor.getContent(), html));
                        } else {
                            editor.execCommand("insertHtml", html);
                        }
                    } else if (typeof UE !== 'undefined' && typeof UE.list["c-content"] !== 'undefined') {
                        editor = UE.list["c-content"];
                        if (insert) {
                            editor.setContent(formatHtml(editor.getContent(), html));
                        } else {
                            editor.execCommand("insertHtml", html);
                        }
                    } else if ($("#c-content").data("summernote")) {
                        editor = $('#c-content');
                        if (insert) {
                            editor.summernote('code', formatHtml(editor.summernote('code'), html))
                        } else {
                            editor.summernote('pasteHTML', html);
                        }
                    } else if (typeof Simditor !== 'undefined' && typeof Simditor.list['c-content'] !== 'undefined') {
                        editor = Simditor.list['c-content'];
                        if (insert) {
                            editor.setValue(formatHtml(editor.getValue(), html));
                        } else {
                            editor.setValue(editor.getValue() + html);
                        }
                    } else if (typeof tinymce !== 'undefined' && typeof tinymce.get('c-content') !== 'undefined') {
                        editor = tinymce.get('c-content');
                        if (insert) {
                            editor.setContent(formatHtml(editor.getContent(), html));
                        } else {
                            editor.insertContent(html);
                        }
                    } else if (html && insert) {
                        Layer.open({
                            content: "你的编辑器暂不支持插入HTML代码，请手动复制以下代码到你的编辑器" + "<textarea class='form-control' rows='5'>" + html + "</textarea>", title: "温馨提示"
                        });
                    }
                };

                //点击插入卡片按钮
                $(document).on('click', '.btn-card', function () {
                    insertHtml('<div data-id="placeholder"></div>');
                    let cancelCallback = function () {
                        insertHtml('', 1);
                    };
                    Layer.open({
                        id: 'goods-tpl-select',
                        type: 1,
                        title: '请选择卡片模板',
                        area: ['600px', '210px'],
                        content: Template('tplselect', {}),
                        zIndex: 99,
                        shade: 0,
                        btn: ["确定", "取消"],
                        success: function (layero, index) {
                            Form.events.selectpage($(".c-select-goods", layero));
                            require(['selectpage'], function () {
                                $('.selectpage', $('.select-template', layero)).selectPage({
                                    eAjaxSuccess: function (data) {
                                        data.totalRow = data.total;
                                        return data;
                                    },
                                    eSelect: function (row) {
                                        switch (row.type) {
                                            case 0://商品
                                                $('.c-select-goods', layero).html(Template('goodstemplte', {}));
                                                break;
                                            case 1://优惠券
                                                $('.c-select-goods', layero).html(Template('coupontemplte', {}));
                                                break;
                                        }
                                        setTimeout(function () {
                                            Form.events.selectpage($(".c-select-goods", layero));
                                        }, 100);
                                    }
                                });
                            });
                        },
                        yes: function (index, layero) {
                            let tpl = $('#c-template', layero).val();
                            let source_id = $('#c-source_id', layero).val();
                            if (!tpl) {
                                Toastr.error('请选择卡片模板');
                                return;
                            }
                            if (!source_id) {
                                Toastr.error('请选择资源数据');
                                return;
                            }
                            Fast.api.ajax({
                                url: 'shop/ajax/get_tpl',
                                data: {
                                    tpl_id: tpl,
                                    source_id
                                }
                            }, function (html) {
                                insertHtml(html, 1);
                                Layer.close(index);
                                return false;
                            })
                        },
                        cancel: cancelCallback,
                        btn2: cancelCallback
                    });
                });
            },
            preview: function () {
                let content = $('#c-content').val();

                content = content.replace(/\{\$.*?title\s{0,}\}/g, '标题')
                    .replace(/\{\$.*?name\s{0,}\}/g, '名称')
                    .replace(/\{\$.*?price\s{0,}\}|\{\$.*?marketprice\s{0,}\}|\{\$.*?number\s{0,}\}/g, '0.0')
                    .replace(/\{\$.*?result_tips\s{0,}\}/g, '满?减?')
                    .replace(/\{\$.*?expire_time\s{0,}\}/g, '过期时间')
                    .replace(/\{if.*?\/if\}/g, '?')
                    .replace(/\{.*?\}/g, '--');

                let dom = $(content)
                dom.find('img').attr('src', '/assets/addons/shop/img/swiper2.jpg')
                dom.find('a').attr('href', 'javascript:;').attr('target', '');

                $('#preview').html(dom.html());
            }
        }
    };
    return Controller;
});
