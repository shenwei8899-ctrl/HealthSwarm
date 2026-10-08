$(function () {

    // 购物车刷新事件
    $(document).on("shop.event.refresh", ".table-cart", function () {
        $(".cart-selected-nums").text($("input[name='ids[]']:checked").length);
        var amount = 0;
        $("input[name='ids[]']:checked", this).each(function () {
            amount += (parseFloat($(this).closest("tr").data("price")) * parseInt($(this).closest("tr").find("input[name=quantity]").val()));
        });
        $(".cart-selected-amount", this).text(amount.toFixed(2));
    });

    // 选中全部
    $(document).on("click", ".checkall", function () {
        $("input[name='ids[]']").prop("checked", $(this).prop("checked"));
        $(".checkall").not(this).prop("checked", $(this).prop("checked"));
        $(".table-cart > tbody > tr").toggleClass("active", $(this).prop("checked"));

        $(".table-cart").trigger("shop.event.refresh");
    });

    //手动变更数量
    $(document).on("change", ".quantity input", function () {
        var input = $(this);
        var value = parseFloat($(this).val());
        var tr = $(this).closest("tr");
        SHOP.api.ajax({
            url: "/addons/shop/cart/set_nums",
            data: {id: tr.data("id"), nums: value}
        }, function (data, ret) {
            input.val(value);
            tr.find(".cart-item-subtotal").text(value * parseFloat(tr.data("price")));
            if (!$("input[name='ids[]']", tr).prop("checked")) {
                $("input[name='ids[]']", tr).prop("checked", true);
                tr.addClass("active");
            }
            $(".table-cart").trigger("shop.event.refresh");
            layer.msg(ret.msg);
            return false;
        });
    });

    // 增减数量
    $(document).on("click", ".quantity > div", function () {
        var input = $(this).siblings("input");
        var value = parseInt(input.val());
        var max = input.attr("max");
        var min = input.attr("min");
        var stocks = parseInt(input.data("stocks"));
        value = $(this).text() == '-' ? value - 1 : value + 1;
        if (value >= stocks) {
            layer.msg("最多可以购买" + stocks + "件");
            return;
        }
        value = min != '' ? Math.max(min, value) : value;
        value = max != '' ? Math.min(max, value) : value;

        var tr = $(this).closest("tr");
        if (tr.length == 0) {
            return;
        }

        SHOP.api.ajax({
            url: "/addons/shop/cart/set_nums",
            data: {id: tr.data("id"), nums: value}
        }, function (data, ret) {
            input.val(value);
            var subtotal = value * parseFloat(tr.data("price"));
            tr.find(".cart-item-subtotal").text(subtotal.toFixed(2));
            if (!$("input[name='ids[]']", tr).prop("checked")) {
                $("input[name='ids[]']", tr).prop("checked", true);
                tr.addClass("active");
            }
            $(".table-cart").trigger("shop.event.refresh");
            layer.msg(ret.msg);
            return false;
        });
    });

    // 删除选中
    $(document).on("click", ".btn-delete-selected", function () {
        layer.confirm("确认删除所选择的商品?", function () {
            var ids = [];
            $("input[name='ids[]']:checked").each(function () {
                ids.push($(this).val());
            });
            if (ids.length == 0) {
                layer.msg('请选择需要删除的商品');
                return false;
            }
            SHOP.api.ajax({
                url: "/addons/shop/cart/del",
                data: {id: ids}
            }, function (data, ret) {
                $("input[name='ids[]']:checked").each(function () {
                    $(this).closest("tr").remove();
                });

                $(".table-cart").trigger("shop.event.refresh");
                layer.closeAll();
                layer.msg(ret.msg);
                return false;
            });

        });
    });

    //删除单个
    $(document).on("click", ".btn-delete", function () {
        var that = this;
        SHOP.api.ajax({
            url: "/addons/shop/cart/del",
            data: {id: $(this).data("id")}
        }, function (data, ret) {
            $(that).closest("tr").remove();
            $(".table-cart").trigger("shop.event.refresh");
            layer.msg(ret.msg);
            return false;
        });
    });

    // 选中复选框
    $(document).on("click", "input[name='ids[]']", function () {
        $(this).closest("tr").toggleClass("active", $(this).prop("checked"));
        $(".table-cart").trigger("shop.event.refresh");
    });

    $(document).on("submit", "#cart-form", function () {
        var ids = [];
        $("input[name='ids[]']:checked", this).each(function () {
            ids.push($(this).val());
        });
        if (ids.length == 0) {
            layer.msg('请选择需要结算的商品');
            return false;
        }
    });
});
