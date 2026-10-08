define(['jquery', 'bootstrap', 'frontend', 'form'], function ($, undefined, Frontend, Form) {

    var Controller = {
        index: function () {
            //删除地址
            $(document).on("click", ".btn-deladdress", function () {
                var that = this;
                Layer.confirm("确认删除?", {icon: 3}, function (index, layero) {
                    Fast.api.ajax({
                        url: "shop.address/del",
                        data: {id: $(that).data('id')}
                    }, function (data) {
                        Layer.close(index);
                        Layer.msg("删除成功");
                        $(that).closest(".col-xs-12").remove();
                        return false;
                    });
                });
                return false;
            });
            //设置为默认
            $(document).on("click", ".btn-setdefault", function () {
                var that = this;
                Layer.confirm("确认设为默认地址?", {icon: 3}, function (index, layero) {
                    Fast.api.ajax({
                        url: "shop.address/setdefault",
                        data: {id: $(that).data('id')}
                    }, function (data) {
                        Layer.close(index);
                        Layer.msg("设置成功");
                        $("address.address").removeClass("active");
                        $(that).closest("address").addClass("active");
                        return false;
                    });
                });
                return false;
            });
        },
        add: function () {
            this.addedit();
        },
        edit: function () {
            this.addedit();
        },
        addedit: function () {
            $(document).on('change', '[data-toggle="cxselect"] select', function (a, b) {
                var arr = [];
                $('[data-toggle="cxselect"] select').each(function () {
                    arr.push($.trim($("option:selected", this).text()));
                });
                var address = arr.join('');
                if ($.trim($("input[name='address']").val()).indexOf(address) !== 0) {
                    $("input[name='address']").val(address);
                }
            });
            Form.events.cxselect($("#cityselect"));

            $(document).on("click", ".btn-saveaddress", function () {
                console.log($(this).closest(".row"));
                Fast.api.ajax({
                    url: "shop.address/save",
                    data: $(this).closest("form").serialize()
                }, function (data, ret) {
                    Layer.alert(ret.msg, function () {
                        location.href = ret.url;
                    });
                    return false;
                });
                return false;
            });

            $(document).on('click', "address", function () {
                $("input[name=area_id]").val($(this).data("id"));
                $("address").removeClass("active");
                $(this).addClass("active");
            });
        }
    };
    return Controller;
});
