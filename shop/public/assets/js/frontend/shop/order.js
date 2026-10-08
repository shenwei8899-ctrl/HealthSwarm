define(['jquery', 'bootstrap', 'frontend', 'form'], function ($, undefined, Frontend, Form) {

    $(document).on("click", ".btn-received", function () {
        var that = this;
        Layer.confirm("请确认收到货以后再点击确认收货？", {icon: 3}, function (index, layero) {
            Fast.api.ajax({
                url: "shop.order/takedelivery",
                data: {orderid: $(that).data("orderid")}
            }, function (data, ret) {
                Layer.close(index);
                setTimeout(function () {
                    location.reload();
                }, 1500);
            });
        })
    });
    $(document).on("click", ".btn-cancel", function () {
        var that = this;
        Layer.confirm("是否取消订单？", {icon: 3}, function (index, layero) {
            Fast.api.ajax({
                url: "shop.order/cancel",
                data: {orderid: $(that).data("orderid")}
            }, function (data, ret) {
                Layer.close(index);
                setTimeout(function () {
                    location.reload();
                }, 1500);
            });
        })
    });
    $(document).on("click", ".btn-refund", function () {
        var that = this;
        Layer.confirm("确认申请退款？", {icon: 3}, function (index, layero) {
            Fast.api.ajax({
                url: "shop.order/apply",
                data: {id: $(that).data("id"), type: 1}
            }, function (data, ret) {
                Layer.close(index);
                setTimeout(function () {
                    location.reload();
                }, 1500);
            });
        })
    });
    $(document).on("click", ".btn-saveexpress", function () {
        if ($("#expressno").val() == '' || $("#expressname").val() == '') {
            Layer.msg("请填写快递名称和快递单号");
            return false;
        }
        var that = this;
        Layer.confirm("确认物品已经寄回且正确填写快递信息？", {icon: 3}, function (index, layero) {
            Fast.api.ajax({
                url: "shop.order/saveexpress",
                data: {id: $(that).data("id"), expressno: $("#expressno").val(), expressname: $("#expressname").val()}
            }, function (data, ret) {
                Layer.close(index);
                setTimeout(function () {
                    location.reload();
                }, 1500);
            });
        })
    });

    var Controller = {
        index: function () {
        },
        apply: function () {
            Form.api.bindevent($("#applyform"), function (data, ret) {
                setTimeout(function () {
                    location.href = ret.url;
                }, 1500);
            });
        },
        logistics: function () {
            if ($(".timeline").length > 0) {
                Fast.api.ajax({
                    url: '',
                }, function (data, ret) {
                    var html = Template("timelinetpl", data);
                    $(".timeline").removeClass("loading").html(html);
                    return false;
                });
            }
        }
    };
    return Controller;
});
