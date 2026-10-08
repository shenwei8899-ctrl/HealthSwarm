define(['jquery', 'bootstrap', 'frontend', 'form'], function ($, undefined, Frontend, Form) {

    var Controller = {
        index: function () {
        },
        post: function () {
            $(document).on("click", ".rating-star", function (e) {
                var container = $(this).closest(".rating");
                var name = container.data("name");
                var value = $(this).data("value");
                $("span", container).removeClass("checked");
                $(this).addClass("checked");
                container.data("value", value);
                $("input[name='" + name + "']").val(value);
            });

            Form.api.bindevent("#postform", function (data, ret) {
                setTimeout(function () {
                    location.href = ret.url;
                }, 1500);
            });
        }
    };
    return Controller;
});
