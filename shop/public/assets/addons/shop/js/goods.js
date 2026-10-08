$(function () {
    // 加载评论
    window.load_comment_list = function (page) {
        SHOP.api.ajax({
            url: "/addons/shop/goods/get_comment_list",
            data: {id: GOODS.id, page: page}
        }, function (data, ret) {
            $("#comment").html(data);
            return false;
        })
    };

    //点击评论图片
    $(document).on("click", "#comment .comment-images img", function () {
        var data = [];
        $.each($(this).closest(".comment-images").find("img"), function (i, j) {
            data.push({
                "src": $(this).attr("src")
            });
        });
        var json = {
            "title": "",
            "start": $(this).parent().index(),
            "data": data
        };
        layer.photos(JSON.parse(JSON.stringify({photos: json})));
    });

    var galleryThumbs = new Swiper('.gallery-thumbs', {
        spaceBetween: 8,
        slidesPerView: 6,
        freeMode: false,
        watchSlidesVisibility: true,
        watchSlidesProgress: true,
    });
    var galleryTop = new Swiper('.gallery-top', {
        spaceBetween: 10,
        noSwipingClass: 'swiper-slide-spec',
        navigation: {
            nextEl: '.swiper-button-next',
            prevEl: '.swiper-button-prev',
        },
        thumbs: {
            swiper: galleryThumbs
        },
    });

    $(document).on('mouseenter', '.gallery-thumbs .swiper-slide', function () {
        $(this).trigger("click");
        galleryTop.slideTo($(this).index(), 0);
    });

    var checkSpecSelected = function () {
        if ($("input[name='spectype']").val() == '1') {
            var sku = $("input[name='skuId']").val();
            if (!sku || sku == '0') {
                layer.msg("请先选中规格");
                return false;
            }
        }
        return true;
    };

    // 增减数量
    $(document).on("click", ".quantity > div", function () {
        var input = $(this).siblings("input");
        var value = parseInt(input.val());
        var max = input.attr("max");
        var min = input.attr("min");
        var stocks = 0;
        value = $(this).text() == '-' ? value - 1 : value + 1;
        if (!checkSpecSelected()) {
            return false;
        }
        if ($("input[name='spectype']").val() == '1') {
            stocks = GOODS['pricelist'][$("input[name='sku']").val()]['stocks'];
        } else {
            stocks = parseInt(input.data("stocks"));
        }
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

    // 加入购物车
    $(document).on("click", ".btn-cart", function () {
        if (!checkSpecSelected()) {
            return false;
        }
        SHOP.api.ajax({
            url: "/addons/shop/cart/add",
            data: {goods_id: $(this).data("id"), goods_sku_id: $("input[name='skuId']").val(), nums: $("input[name='quantity']").val(), sceneval: 1}
        }, function (data, ret) {
            $("#cartnums").text(data.cartnums);
            layer.msg(ret.msg);
            return false;
        }, function (data, ret) {
            if (ret.msg.indexOf("请登录") > -1) {
                layer.alert("请登录后再进行操作", {
                    title: "温馨提示", icon: 0, btn: ["去登录"]
                }, function () {
                    location.href = ret.url;
                });
                return false;
            }
        });
    });

    // 立即购买
    $(document).on("click", ".btn-buynow", function () {
        if (!checkSpecSelected()) {
            return false;
        }
        SHOP.api.ajax({
            url: "/addons/shop/cart/add",
            data: {goods_id: $(this).data("id"), goods_sku_id: $("input[name='skuId']").val(), nums: $("input[name='quantity']").val(), sceneval: 2}
        }, function (data) {
            $("input[name='ids']").val(data.cart_id);
            $("input[name='ids']").closest("form").submit();
            return false;
        }, function (data, ret) {
            if (ret.msg.indexOf("请登录") > -1) {
                layer.alert("请登录后再进行操作", {
                    title: "温馨提示", icon: 0, btn: ["去登录"]
                }, function () {
                    location.href = ret.url;
                });
                return false;
            }
        });
        return false;
    });

    $(document).on("click", ".goods-spec ul > li", function () {
        if ($(this).hasClass("disabled")) {
            return false;
        }
        var item = $(this).closest(".goods-spec");
        if ($(this).hasClass("selected")) {
            $(this).removeClass("selected");
            item.removeAttr("data-value");
        } else {
            $(this).addClass("selected").siblings("li").removeClass("selected");
            item.attr("data-value", $(this).attr("data-id"))
        }
        getattrprice(); //输出价格
    });

    //获取对应属性的价格
    function getattrprice() {
        var defaultstats = true;
        var sku = '';
        var doms = {
            marketprice: ".goods-marketprice",
            price: ".goods-price",
            stocks: ".goods-stocks",
        };

        $(".goods-spec li.disabled").removeClass("disabled");
        let selected = $(".goods-spec li.selected").map(function () {
            return $(this).data("id");
        }).get();
        $.each(GOODS.pricelist, function (i, j) {
            var keys = i.split(/\,/);
            var c = keys.filter(function (v) {
                return selected.indexOf(parseInt(v)) > -1
            });
            if (c.length == keys.length - 1 && parseInt(j.stocks) == 0) {
                $(".goods-spec li:not(.selected)").filter(function () {
                    return keys.indexOf($(this).data("id") + "") > -1;
                }).addClass("disabled");
            }
        });
        var skuArr = [];
        $(".goods-spec").each(function () {
            var i = $(this);
            var v = i.attr("data-value");
            if (!v) {
                defaultstats = false;
            } else {
                skuArr.push(v);
            }
        });
        skuArr.sort(function (a, b) {
            return a - b
        });
        sku = skuArr.join(',');

        var _marketprice, _price, _stocks, _skuid, _image;
        if (!!defaultstats && typeof GOODS['pricelist'][sku] !== 'undefined') {
            _marketprice = GOODS['pricelist'][sku]['marketprice'];
            _price = GOODS['pricelist'][sku]['price'];
            _stocks = GOODS['pricelist'][sku]['stocks'];
            _skuid = GOODS['pricelist'][sku]['id'];
            _image = GOODS['pricelist'][sku]['image'];
        } else {
            _marketprice = GOODS['marketprice'];
            _price = GOODS['price'];
            _stocks = GOODS['stocks'];
            _image = '';
        }

        $(doms.marketprice).text(parseFloat(_marketprice).toFixed(2));
        $(doms.price).text(parseFloat(_price).toFixed(2));
        if (_image) {
            $(".product-gallery .gallery-thumbs .swiper-slide").removeClass("swiper-slide-active swiper-slide-thumb-active");
            $(".product-gallery .gallery-top .swiper-slide:last").clone()
                .addClass("swiper-slide-spec").css("backgroundImage", "url('" + _image + "')")
                .prependTo($(".product-gallery .gallery-top .swiper-wrapper"));
            galleryTop.slideTo(0, 0);
        } else {
            $(".product-gallery .gallery-top .swiper-slide-spec").remove();
        }
        $(document).on("mouseenter", ".product-gallery .gallery-thumbs .swiper-slide", function () {
            $(".product-gallery .gallery-top .swiper-slide-spec").remove();
        });
        $(".btn-cart").data("sku-id", _skuid).data("sku", sku);
        $("input[name='skuId']").val(_skuid);
        $("input[name='sku']").val(sku);
    }

    getattrprice();
});
