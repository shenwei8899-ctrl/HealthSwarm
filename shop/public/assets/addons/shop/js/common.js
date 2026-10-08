$(function () {
    window.isMobile = !!("ontouchstart" in window);

    //new LazyLoad({elements_selector: ".lazy"});

    if (!isMobile) {
        // 搜索框
        $("input[name='search']").on("focus", function () {
            $(this).closest(".form-search").addClass("focused");
        }).on("blur", function (e) {
            var that = this;
            setTimeout(function () {
                $(that).closest(".form-search").removeClass("focused");
            }, 500);
        });
    }

    // 点击收藏
    $(".addbookbark").attr("rel", "sidebar").click(function () {
        var url = location.href;
        var title = $(this).attr("title") || document.title;
        if (/firefox/i.test(navigator.userAgent)) {
        } else if (window.external && window.external.addFavorite) {
            window.external.addFavorite(url, title);
        } else if (window.sidebar && window.sidebar.addPanel) {
            window.sidebar.addPanel(title, url, "");
        } else {
            var touch = (navigator.userAgent.toLowerCase().indexOf('mac') != -1 ? 'Command' : 'CTRL');
            layer.msg('请使用 ' + touch + ' + D 添加到收藏夹.');
        }
        return false;
    });

    // 点击收藏
    $(document).on('click', '.btn-collect', function (e) {
        var that = this;
        SHOP.api.ajax({
            url: "/addons/shop/ajax/collect",
            data: {goods_id: $(this).data("id")}
        }, function (data, ret) {
            $("span", that).text("已收藏");
            layer.msg(ret.msg);
            return false;
        });
    });

    if (typeof wx !== 'undefined') {

        //分享参数配置
        var shareConfig = {
            title: $("meta[property='og:title']").attr("content") || document.title,
            description: $("meta[property='og:description']").attr("content") || "",
            url: $("meta[property='og:url']").attr("content") || location.href,
            image: $("meta[property='og:image']").attr("content") || ""
        };

        //微信公众号内分享
        shareConfig.url = location.href;
        SHOP.api.ajax({
                url: "/addons/shop/ajax/share",
                data: {url: shareConfig.url},
                loading: false
            }, function (data, ret) {
                try {
                    wx.config({
                        appId: data.appId,
                        timestamp: data.timestamp,
                        nonceStr: data.nonceStr,
                        signature: data.signature,
                        jsApiList: [
                            'checkJsApi',
                            'updateAppMessageShareData',
                            'updateTimelineShareData',
                        ]
                    });
                    var shareData = {
                        title: shareConfig.title,
                        desc: shareConfig.description,
                        link: shareConfig.url,
                        imgUrl: shareConfig.image,
                        success: function () {
                            layer.closeAll();
                        },
                        cancel: function () {
                            layer.closeAll();
                        }
                    };
                    wx.ready(function () {
                        wx.updateAppMessageShareData(shareData);
                        wx.updateTimelineShareData(shareData);
                    });

                } catch (e) {
                    console.log(e);
                }
                return false;
            }, function () {
                return false;
            }
        );
    }

    // 点击分享
    $(document).on('click', '.btn-share', function (e) {
        var that = this;
        var data = $(that).data();
        if (typeof wx != 'undefined') {
            layer.msg("请点击右上角的●●●进行分享");
        } else {
            layer.open({
                title: '分享',
                content: '<div class="social-share text-center mt-2 mb-1"><div class="share-qrcode"></div><p class="small">请使用微信扫一扫进行分享</p></div>',
                btn: false,
                success: function (layero) {
                    $(".share-qrcode").qrcode({text: $(that).data("url") || location.href});
                    $('.social-share', layero).data(data).share({sites: 'qzone,qq,weibo,douban'});
                }
            });
        }
        return false;
    });

    //领取优惠券
    $(document).on('click', '.btn-coupon', function () {
        let id = $(this).data('name');
        SHOP.api.ajax({
            url: "/addons/shop/coupon/drawCoupon",
            data: {id: id}
        }, function (data, ret) {
            setTimeout(function () {
                window.location.reload();
            }, 1500);
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

    // 倒计时
    $('[data-countdown]').each(function () {
        var that = this;
        var $this = $(this), finalDate = parseInt($(this).data('countdown'));
        if (finalDate > 0) {
            finalDate = isNaN(finalDate) ? finalDate : new Date().getTime() + finalDate * 1000;
            var format = $(that).data("format");
            $this.on('finish.countdown', function () {
                if (typeof $this.data("finish") == 'function') {
                    $this.data("finish").call($this);
                } else {
                    location.reload();
                }
            }).countdown(finalDate, function (event) {
                $this.html(event.strftime(format) || event.strftime('%D天%H时%M分%S秒'));
            });
        }
    });

    var backtotop = $('#back-to-top');
    $(window).scroll(function () {
        if ($(window).scrollTop() >= 200) {
            backtotop.fadeIn();
        } else {
            backtotop.fadeOut();
        }
    });
    $(window).trigger("scroll");

    // 回到顶部
    backtotop.on('click', function (e) {
        e.preventDefault();
        $('html,body').animate({
            scrollTop: 0
        }, 700);
    });

    // 如果是PC则移除navbar的dropdown点击事件
    if (!/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobi/i.test(navigator.userAgent)) {
        $(".nav-bar [data-toggle='dropdown']").removeAttr("data-toggle");
    } else {
        $(".navbar-nav ul li:not(.dropdown-submenu):not(.dropdown) a").removeAttr("data-toggle");
    }

    // 点击支付
    $(document).on("click", ".btn-paynow", function () {
        layer.confirm("请根据支付状态选择下面的操作按钮", {title: "温馨提示", icon: 0, btn: ["支付成功", "支付失败"]}, function () {
            location.reload();
        });
    });

    var $category = $('.category');
    var $topMenu = $('.top-menu');
    var hideTimeout = null;
    var currentSubmenu = null; // 保存当前显示的子菜单

    // 点击顶部菜单
    $(document).on("click", ".nav-item-topmenu", function () {
        $topMenu.toggle();
    });

    // 隐藏原始的子菜单
    $topMenu.find('.dropdown-menu').hide();

    function hideTopMenu(immediate) {
        if ($('.static-menu').length === 0) {
            $topMenu.fadeOut(immediate ? 0 : 200);
        }
    }

    // 清除定时器
    function clearTimer() {
        if (hideTimeout) {
            clearTimeout(hideTimeout);
            hideTimeout = null;
        }
    }

    // 移除动态创建的子菜单
    function removeSubmenu() {
        if (currentSubmenu) {
            currentSubmenu.remove();
            currentSubmenu = null;
        }
    }

    // 延迟隐藏
    function delayHide() {
        clearTimer();
        hideTimeout = setTimeout(function () {
            hideTopMenu();
            removeSubmenu();
        }, 200);
    }

    // 创建动态子菜单
    function createSubmenu($dropdown) {
        // 移除之前的子菜单
        removeSubmenu();

        var $originalMenu = $dropdown.children('.dropdown-menu');
        if (!$originalMenu.length) return;

        // 克隆子菜单内容
        var $clonedMenu = $originalMenu.clone();

        // 获取触发元素的位置
        var $link = $dropdown.children('a');
        var offset = $link.offset();
        var linkWidth = $link.outerWidth();
        var linkHeight = $link.outerHeight();
        var windowWidth = $(window).width();
        var windowHeight = $(window).height();

        // 创建新的子菜单容器
        currentSubmenu = $('<div class="dynamic-submenu float-menu custom-scrollbar"></div>')
            .append($clonedMenu.html())
            .css({
                'position': 'fixed',
                'z-index': 10000,
                'display': 'none',
                'width': '200px',
                'max-height': '500px',
                'overflow-x': 'hidden',
                'overflow-y': 'auto',
                'background': '#fff',
                // 'border': '1px solid #e0e0e0',
                'box-shadow': '2px 2px 10px rgba(0, 0, 0, 0.15)',
            })
            .appendTo('body');

        // 计算子菜单的宽高
        currentSubmenu.show();
        var submenuWidth = currentSubmenu.outerWidth();
        var submenuHeight = currentSubmenu.outerHeight();

        // 计算最佳显示位置
        var left = offset.left + linkWidth;
        var top = offset.top - $(window).scrollTop();

        // 检查右侧空间，如果不够则显示在左侧
        if (left + submenuWidth > windowWidth) {
            left = offset.left - submenuWidth;
            left = Math.max(185, left);
        }

        // 检查底部空间，如果不够则向上调整
        if (top + submenuHeight > windowHeight) {
            top = windowHeight - submenuHeight - 5;
            if (top < 5) top = 5;
        }

        // 设置最终位置
        currentSubmenu.css({
            'left': left + 'px',
            'top': top + 'px'
        });

        // 添加淡入效果
        currentSubmenu.hide().fadeIn(150);

        // 为动态子菜单添加事件
        currentSubmenu.hover(
            function () {
                clearTimer();
            },
            function () {
                removeSubmenu();
                delayHide();
            }
        );

        // 为子菜单中的链接添加点击事件（可选）
        currentSubmenu.find('a').on('click', function () {
            removeSubmenu();
            hideTopMenu(true);
        });

        return currentSubmenu;
    }

    if (!isMobile) {
        // .category 和 .top-menu 的悬停处理
        $category.add($topMenu).hover(
            function () {
                clearTimer();
                //$topMenu.addClass('hovered');
                $topMenu.stop(true).fadeIn(200);
            },
            function () {
                //$topMenu.removeClass('hovered');
                delayHide();
            }
        );
    }

    // 子菜单处理
    $topMenu.find('.dropdown').each(function () {
        var $dropdown = $(this);
        var $dropdownMenu = $dropdown.children('.dropdown-menu');

        if ($dropdownMenu.length) {
            $dropdown.hover(
                function () {
                    clearTimer();
                    createSubmenu($dropdown);
                },
                function (e) {
                    var $relatedTarget = $(e.relatedTarget);
                    // 如果鼠标移动到动态子菜单上，不隐藏
                    if (!$relatedTarget.closest('.dynamic-submenu').length) {
                        clearTimer();
                        hideTimeout = setTimeout(function () {
                            removeSubmenu();
                        }, 200);
                    }
                }
            );
        }
    });

    if (isMobile) {
        $topMenu.on('shown.bs.dropdown', function () {
            $('.dropdown-backdrop').remove();
        });
    }

    // 点击页面其他地方关闭菜单
    $(document).on('click', function (e) {
        if (!$(e.target).closest('.category, .top-menu, .dynamic-submenu, .nav-item-topmenu, .dropdown').length) {
            hideTopMenu(true);
            removeSubmenu();
        }
    });

    // 窗口滚动或调整大小时关闭子菜单
    $(window).on('scroll resize', function () {
        removeSubmenu();
    });

    // 顶部浮动导航
    var headerAction = $(".header-menu");
    if (headerAction.length > 0 && $(window).width() > 1200) {
        var actionOffset = headerAction.offset().top;
        var inNav = false;
        var staticMenu = headerAction.hasClass("static-menu");
        var check_action = function () {
            if ($(window).scrollTop() >= actionOffset) {
                headerAction.addClass("fixed");
                if (staticMenu) {
                    headerAction.removeClass("static-menu");
                }
                inNav = true;
            } else {
                headerAction.removeClass("fixed");
                if (staticMenu) {
                    headerAction.addClass("static-menu");
                }
                inNav = false;
            }
        };
        $(window).scroll(function () {
            check_action();
        });
        check_action();
    }
    if (headerAction.length > 0) {
        $("a[data-toggle='dropdown']", headerAction).on("click", function () {
            $(this).next("ul").find("li:first-child a.btn-download").trigger("click");
        });
    }

    if (!isMobile) {
        $(".search-input").autoComplete({
            minChars: 1,
            cache: false,
            menuClass: 'autocomplete-searchmenu',
            header: '',
            footer: '',
            source: function (term, response) {
                try {
                    xhr.abort();
                } catch (e) {
                }
                xhr = $.getJSON($(this).data("suggestion-url"), {q: term}, function (data) {
                    response(data);
                });
            },
            onSelect: function (e, term, item) {
                if (typeof callback === 'function') {
                    callback.call(elem, term, item);
                } else {
                    $(this).closest("form").trigger("submit");
                }
            }
        });
    }
});
