define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {
    var Controller = {
        index: function () {
            var previewUrl = $("#previewiframe").attr("src");
            $(".btn-color").on("click", function () {
                var currentColor = $(this).parent().prev().val();
                var input = $(this).next();
                if (!input.is("input")) {
                    input = $('<input type="color" value="" style="visibility: hidden;width:1px;height:1px;position:absolute;top:-1px;" />');
                    input.on("input", function () {
                        $(this).closest(".input-group").find("input").val($(this).val());
                    })
                    input.insertAfter(this);
                }
                setTimeout(function () {
                    input.val(currentColor);
                    input.click();
                }, 1);
            }).on("contextmenu", function () {
                $(this).closest(".input-group").find("input").val("");
                return false;
            });
            Form.api.bindevent($("form[role=form]"), function () {
                $("#previewiframe").attr("src", previewUrl + ($("#config-form input[name='preview']").val() == 1 ? "?mode=preview" : ""));
            });
            $(document).on("fa.event.appendfieldlist", ".tabbarlist .btn-append", function (e, obj) {
                if ($(".tabbarlist table tr.tabbarlist-item").length > 5) {
                    $(".tabbarlist table tr.tabbarlist-item:last").remove();
                    Layer.msg("最多允许添加5个");
                }
                Form.events.faselect(obj);
            });
            $(document).on("change", ".tabbarlist .tabbar-img-value", function (e, obj) {
                $(this).next().attr("src", Fast.api.cdnurl($(this).val(), true));
            });
            $(document).on("change", ".tabbarlist .c-tabbar-list-midbutton", function (e, obj) {
                $(".tabbarlist .c-tabbar-list-midbutton").not(this).prop("checked", false);
            });
            $(document).on("click", ".btn-preview", function (e, obj) {
                $("#config-form input[name='preview']").val(1);
            });
            $(document).on("click", ".btn-preview,.btn-save", function (e, obj) {
                $("#config-form input[name='preview']").val($(this).data("preview"));
                $("#config-form").submit();
            });
            $(document).on("click", ".btn-select-page", function (e, obj) {
                var that = this;
                Fast.api.open("shop/ajax/get_page_list", "选择路径", {
                    callback: function (data) {
                        $(that).parent().prev().val(data);
                    }
                })
            });
        },
    };
    return Controller;
});
