$(function () {


    //领取优惠券
    $(document).on('click', '.btn-exchange', function () {
        let id = $(this).data('id');
        let type = $(this).data('type');
        let html = $('#exchangetpl').html();

        layer.open({
            title: '兑换商品',
            type: 1,
            area: ['450px', type == 'reality' ? '300px' : '250px'], //宽高
            content: html,
            success: function () {
                $(document).on('click', '.btn-submit-exchange', function () {
                    let form = $('#exchange-form').serializeArray();
                    let data = {exchange_id:id};
                    form.forEach(item => {
                        data[item.name] = item.value;
                    })
                    SHOP.api.ajax({
                        url: "/addons/shop/exchange/exchange",
                        data: data
                    }, function (res) {
                        setTimeout(() => {
                            window.location.reload();
                        }, 1500)
                    });

                })
            }
        })
    })

    // 增减数量
    $(document).on("click", ".quantity > div", function () {
        var input = $(this).siblings("input");
        var value = parseInt(input.val());
        var max = input.attr("max");
        var min = input.attr("min");
        var stocks = 0;
        value = $(this).text() == '-' ? value - 1 : value + 1;
        stocks = parseInt(input.data("stocks"));
        if (value >= stocks) {
            input.val(stocks);
            layer.msg("最多可以购买" + stocks + "件");
            return;
        }
        value = min != '' ? Math.max(min, value) : value;
        value = max != '' ? Math.min(max, value) : value;

        input.val(value);
        return false;
    });

})
