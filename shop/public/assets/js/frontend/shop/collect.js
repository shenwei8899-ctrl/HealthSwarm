define(['jquery', 'bootstrap', 'frontend'], function ($, undefined, Frontend) {

    var Controller = {
        index: function () {
            //删除地址
            $(document).on("click", ".btn-delcollect", function () {
                var that = this;
                Layer.confirm("确认删除?", {icon: 3}, function (index, layero) {
                    Fast.api.ajax({
                        url: "shop.collect/del",
                        data: {id: $(that).data('id')}
                    }, function (data) {
                        Layer.close(index);
                        Layer.msg("删除成功");
                        $(that).closest(".media").remove();
                        return false;
                    });
                });
                return false;
            });
        }
    };
    return Controller;
});
