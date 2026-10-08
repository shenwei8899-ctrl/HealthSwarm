
define(['jquery', 'bootstrap', 'backend', 'table', 'form', 'echarts', 'echarts-theme'], function ($, undefined, Backend, Table, Form, Echarts, undefined) {
    var areaObj = {};
    var Controller = {
        common: function (obj) {
            $(window).resize(function () {
                for (let i in obj) {
                    obj[i].chart.resize();
                }
            });

            //点击刷新
            $(document).on("click", "a.btn-refresh", function () {
                let val = $(this).data('chart');
                obj[val].chart.resize();
                obj[val].refresh();
            });

            //每隔60s定时刷新图表
            setInterval(function () {
                $(".btn-refresh").trigger("click");
            }, 60000);

            //点击按钮
            $(document).on("click", ".btn-filter", function () {
                var label = $(this).text();
                var obj = $(this).closest("form").find(".datetimerange").data("daterangepicker");
                var dates = obj.ranges[label];
                obj.startDate = dates[0];
                obj.endDate = dates[1];
                obj.clickApply();
            });

            //选项卡切入事件
            $(document).on("click", "#resetecharts", function () {
                setTimeout(function () {
                    $(window).trigger("resize");
                }, 50);
            });
        },
        index: function () {
            let obj = {}
            obj.chart1 = this.api.index.myChart1();
            obj.chart2 = this.api.index.myChart2();
            obj.chart4 = this.api.index.myChart4();
            this.common(obj);
            Form.api.bindevent($("#form1"));
            Form.api.bindevent($("#form2"));
            Form.api.bindevent($("#form4"));

        },
        areas: function () {           
            areaObj.chart1 = this.api.areas.myChart1();
            areaObj.chart2 = this.api.areas.myChart2();
            areaObj.chart1.refresh();
            this.common(areaObj);
            //绑定事件
            Form.api.bindevent($("#form1"));
            Form.api.bindevent($("#form2"));
        },
        api: {
            bindevent: function () {
                Form.api.bindevent($("form[role=form]"));
            },
            index: {
                myChart1: function () {
                    // 基于准备好的dom，初始化echarts实例
                    let myChart = Echarts.init($('#echarts1')[0], 'walden');
                    // 指定图表的配置项和数据
                    let option = {
                        title: {
                            text: '订单金额趋势',
                            subtext: ''
                        },
                        tooltip: {
                            trigger: 'axis'
                        },
                        legend: {
                            data: ['订单金额', '退款金额']
                        },
                        toolbox: {
                            show: true,
                            feature: {
                                dataView: {
                                    show: true,
                                    readOnly: false
                                },
                                magicType: {
                                    show: true,
                                    type: ['line', 'bar']
                                },
                                restore: {
                                    show: true
                                },
                                saveAsImage: {
                                    show: true
                                }
                            }
                        },
                        calculable: true,
                        xAxis: {
                            type: 'category',
                            boundaryGap: false,
                            data: Config.orderSaleCategory
                        },
                        yAxis: {},
                        grid: {
                            left: '3%',
                            right: '4%',
                            bottom: '3%',
                            containLabel: true
                        },
                        series: [{
                            name: "订单金额",
                            type: 'line',
                            smooth: true,
                            areaStyle: {
                                normal: {}
                            },
                            lineStyle: {
                                normal: {
                                    width: 1.5
                                }
                            },
                            data: Config.orderSaleAmount
                        }, {
                            name: '退款金额',
                            type: 'line',
                            data: Config.afterSaleAmount,
                            markPoint: {
                                data: [{
                                        type: 'max',
                                        name: '最大值'
                                    },
                                    {
                                        type: 'min',
                                        name: '最小值'
                                    }
                                ]
                            },
                            markLine: {
                                data: [{
                                    type: 'average',
                                    name: '平均值'
                                }]
                            }
                        }]
                    };
                    // 使用刚指定的配置项和数据显示图表。
                    myChart.setOption(option);

                    var date = '';

                    $("#form1 .datetimerange").data("callback", function (start, end) {
                        date = start.format(this.locale.format) + " - " + end.format(this.locale.format);
                        $(this.element).val(date);
                        refresh();
                    });

                    //点击按钮
                    $(document).on("click", ".btn-type", function () {
                        refresh();
                    });


                    var si = null;

                    function refresh() {
                        si && clearTimeout(si);
                        si = setTimeout(function () {
                            Fast.api.ajax({
                                url: 'shop/report/index',
                                data: {
                                    date: date
                                },
                                loading: false
                            }, function (res) {
                                option.xAxis.data = res.orderSaleCategory;
                                option.series[0].data = res.orderSaleAmount;
                                option.series[1].data = res.afterSaleAmount;
                                myChart.clear();
                                myChart.setOption(option, true);
                                if (res.totalOrderAmount != undefined) {
                                    $('#totalOrderAmount').html(res.totalOrderAmount)
                                }
                                if (res.todayOrderAmount != undefined) {
                                    $('#todayOrderAmount').html(res.todayOrderAmount)
                                }
                                if (res.totalProfitAmount != undefined) {
                                    $('#totalProfitAmount').html(res.totalProfitAmount)
                                }
                                if (res.totalRefundAmount != undefined) {
                                    $('#totalRefundAmount').html(res.totalRefundAmount)
                                }
                                if (res.todayRefundAmount != undefined) {
                                    $('#todayRefundAmount').html(res.todayRefundAmount)
                                }
                                if (res.yesterdayRefundAmount != undefined) {
                                    $('#yesterdayRefundAmount').html(res.yesterdayRefundAmount)
                                }
                                if (res.todayOrderRatio != undefined) {
                                    let dom = $('#todayOrderRatio');
                                    dom.html((res.todayOrderRatio > 0 ? '+' : '') + res.todayOrderRatio + '%');
                                    dom.attr('title', '昨天：' + res.yesterdayOrderAmount);
                                    if (res.todayOrderRatio >= 0) {
                                        dom.removeClass('text-danger').addClass('text-success');
                                    } else {
                                        dom.removeClass('text-success').addClass('text-danger');
                                    }
                                }

                                return false;
                            });
                        }, 50);
                    }

                    return {
                        chart: myChart,
                        refresh: refresh
                    };
                },
                myChart2: function () {
                    // 基于准备好的dom，初始化echarts实例
                    let myChart = Echarts.init($('#echarts2')[0], 'walden');
                    // 指定图表的配置项和数据
                    let option = {
                        title: {
                            text: '订单数量趋势',
                            subtext: ''
                        },
                        tooltip: {
                            trigger: 'axis'
                        },
                        legend: {
                            data: ['订单数量', '退款数量']
                        },
                        toolbox: {
                            show: true,
                            feature: {
                                dataView: {
                                    show: true,
                                    readOnly: false
                                },
                                magicType: {
                                    show: true,
                                    type: ['line', 'bar']
                                },
                                restore: {
                                    show: true
                                },
                                saveAsImage: {
                                    show: true
                                }
                            }
                        },
                        calculable: true,
                        xAxis: {
                            type: 'category',
                            boundaryGap: false,
                            data: Config.afterSaleCategory
                        },
                        yAxis: {},
                        grid: {
                            left: '3%',
                            right: '4%',
                            bottom: '3%',
                            containLabel: true
                        },
                        series: [{
                            name: "订单数量",
                            type: 'line',
                            smooth: true,
                            areaStyle: {
                                normal: {}
                            },
                            lineStyle: {
                                normal: {
                                    width: 1.5
                                }
                            },
                            data: Config.orderSaleNums
                        }, {
                            name: '退款数量',
                            type: 'line',
                            data: Config.afterSaleNums,
                            markPoint: {
                                data: [{
                                        type: 'max',
                                        name: '最大值'
                                    },
                                    {
                                        type: 'min',
                                        name: '最小值'
                                    }
                                ]
                            },
                            markLine: {
                                data: [{
                                    type: 'average',
                                    name: '平均值'
                                }]
                            }
                        }]
                    };
                    // 使用刚指定的配置项和数据显示图表。
                    myChart.setOption(option);

                    var date = '';

                    $("#form2 .datetimerange").data("callback", function (start, end) {
                        date = start.format(this.locale.format) + " - " + end.format(this.locale.format);
                        $(this.element).val(date);
                        refresh();
                    });

                    //点击按钮
                    $(document).on("click", ".btn-type", function () {
                        refresh();
                    });


                    var si = null;

                    function refresh() {
                        si && clearTimeout(si);
                        si = setTimeout(function () {
                            Fast.api.ajax({
                                url: 'shop/report/index',
                                data: {
                                    date: date
                                },
                                loading: false
                            }, function (res) {
                                option.xAxis.data = res.afterSaleCategory;
                                option.series[0].data = res.orderSaleNums;
                                option.series[1].data = res.afterSaleNums;
                                myChart.clear();
                                myChart.setOption(option, true);
                                return false;
                            });
                        }, 50);
                    }

                    return {
                        chart: myChart,
                        refresh: refresh
                    };
                },
                myChart3: function () {
                    return;
                },
                myChart4: function () {
                    // 基于准备好的dom，初始化echarts实例
                    let myChart = Echarts.init($('#echarts4')[0], 'walden');
                    let option = {
                        title: {
                            text: '销售商品分类占比',
                            // subtext: '',
                            left: 'left'
                        },
                        tooltip: {
                            trigger: 'item',
                            formatter: function (row) {
                                let {
                                    data
                                } = row;
                                let name = (data && data.name) || '';
                                let value = (data && data.value) || 0;
                                return `${name}:${value}%`
                            }
                        },
                        legend: {
                            type: 'scroll',
                            orient: 'vertical',
                            right: 10,
                            top: 20,
                            bottom: 20,
                            data: Config.legendData,
                        },
                        series: [{
                            name: '名称',
                            type: 'pie',
                            radius: '75%',
                            center: ['40%', '50%'],
                            data: Config.seriesData,
                            label: {
                                formatter: function (row) {
                                    let {
                                        data
                                    } = row;
                                    let name = (data && data.name) || '';
                                    let value = (data && data.value) || 0;
                                    return `${name} : (${value}%)`
                                }
                            },
                            emphasis: {
                                itemStyle: {
                                    shadowBlur: 10,
                                    shadowOffsetX: 0,
                                    shadowColor: 'rgba(0, 0, 0, 0.5)'
                                }
                            }
                        }]
                    };
                    myChart.setOption(option, true);

                    var date = '';

                    $("#form4 .datetimerange").data("callback", function (start, end) {
                        date = start.format(this.locale.format) + " - " + end.format(this.locale.format);
                        $(this.element).val(date);
                        refresh();
                    });

                    //点击按钮
                    $(document).on("click", ".btn-type", function () {
                        refresh();
                    });

                    var si = null;

                    function refresh() {
                        si && clearTimeout(si);
                        si = setTimeout(function () {
                            Fast.api.ajax({
                                url: 'shop/report/index',
                                data: {
                                    date: date
                                },
                                loading: false
                            }, function (res) {
                                option.series[0].data = res.seriesData;
                                option.legend.data = res.legendData;
                                myChart.clear();
                                myChart.setOption(option, true);
                                return false;
                            });
                        }, 50);
                    }
                    return {
                        chart: myChart,
                        refresh: refresh
                    };

                }
            },
            areas: {
                myChart1: function () {
                    let isFirst = false;
                    // 基于准备好的dom，初始化echarts实例
                    let myChart = Echarts.init($('#echarts1')[0], 'walden');
                    var colors = ['#5470C6', '#91CC75', '#EE6666', '#18bc9c'];
                    // 指定图表的配置项和数据
                    let option = {
                        title: {
                            text: '',
                            subtext: ''
                        },
                        color: colors,
                        tooltip: {
                            trigger: 'axis',
                            axisPointer: {
                                type: 'cross'
                            }
                        },
                        grid: {
                            left: '15',
                            right: '4%',
                            bottom: '3%',
                            top: '11%',
                            containLabel: true,
                            y2: 120
                        },
                        toolbox: {
                            show: true,
                            feature: {
                                dataView: {
                                    show: true,
                                    readOnly: false
                                },
                                magicType: {
                                    show: true,
                                    type: ['line', 'bar']
                                },
                                restore: {
                                    show: true
                                },
                                saveAsImage: {
                                    show: true
                                }
                            }
                        },
                        legend: {
                            data: ['订单数量', '商品数量', '订单金额', '订单占比']
                        },
                        xAxis: [{
                            type: 'category',
                            axisTick: {
                                alignWithLabel: true
                            },
                            axisLabel: {
                                interval: 0,
                                rotate: -30, //倾斜度 -90 至 90 默认为0
                                // margin:2,
                                // textStyle: {
                                //     color: '#7c8893',
                                //     fontSize: 12
                                // },
                                // formatter: function(value) {
                                //     return value.split("").join("\n");
                                // }
                            },
                            offset: 10,
                            triggerEvent:true,
                            data: []
                        }],
                        yAxis: [{
                                type: 'value',
                                name: '订单数量',
                                min: 0,
                                max: 50,
                                position: 'right',
                                axisLine: {
                                    show: true,
                                    lineStyle: {
                                        color: colors[0]
                                    }
                                },
                                axisLabel: {
                                    formatter: '{value} 个'
                                }
                            },
                            {
                                type: 'value',
                                name: '商品数量',
                                min: 0,
                                max: 50,
                                position: 'right',
                                offset: 80,
                                axisLine: {
                                    show: true,
                                    lineStyle: {
                                        color: colors[1]
                                    }
                                },
                                axisLabel: {
                                    formatter: '{value} 件'
                                }
                            },
                            {
                                type: 'value',
                                name: '订单金额',
                                min: 0,
                                max: 2500,
                                position: 'left',
                                axisLine: {
                                    show: true,
                                    lineStyle: {
                                        color: colors[2]
                                    }
                                },
                                axisLabel: {
                                    formatter: '{value} 元'
                                }
                            },
                            {
                                type: 'value',
                                name: '订单占比',
                                min: 0,
                                max: 100,
                                position: 'left',
                                offset: 60,
                                axisLine: {
                                    show: true,
                                    lineStyle: {
                                        color: colors[3]
                                    }
                                },
                                axisLabel: {
                                    formatter: '{value} %'
                                }
                            }
                        ],
                        series: [{
                                name: '订单数量',
                                type: 'bar',
                                data: [],
                                markPoint: {
                                    data: [{
                                            type: 'max',
                                            name: '最大值'
                                        },
                                        {
                                            type: 'min',
                                            name: '最小值'
                                        }
                                    ]
                                }
                            },
                            {
                                name: '商品数量',
                                type: 'bar',
                                yAxisIndex: 1,
                                data: [],
                                markPoint: {
                                    data: [{
                                            type: 'max',
                                            name: '最大值'
                                        },
                                        {
                                            type: 'min',
                                            name: '最小值'
                                        }
                                    ]
                                }
                            },
                            {
                                name: '订单金额',
                                type: 'line',
                                yAxisIndex: 2,
                                data: [],
                                markLine: {
                                    data: [{
                                        type: 'average',
                                        name: '平均值'
                                    }]
                                },
                                label: {
                                    show: true
                                },
                            },
                            {
                                name: '订单占比',
                                type: 'line',
                                yAxisIndex: 3,
                                data: [],
                                markLine: {
                                    data: [{
                                        type: 'average',
                                        name: '平均值'
                                    }]
                                },
                                label: {
                                    show: true
                                },
                            }
                        ]
                    };
                    // 使用刚指定的配置项和数据显示图表。
                    myChart.setOption(option);

                    myChart.on('click', 'xAxis', function (res) {
                        areaObj.chart2.refresh(res.value);
                        
                    });
                   
                    myChart.on('click', 'series', function (res) {
                        if(!['最大值','最小值'].includes(res.name)){
                            areaObj.chart2.refresh(res.name);
                        }
                    });

                    var date = '';

                    $("#form1 .datetimerange").data("callback", function (start, end) {
                        date = start.format(this.locale.format) + " - " + end.format(this.locale.format);
                        $(this.element).val(date);
                        refresh();
                    });

                    //点击按钮
                    $(document).on("click", ".btn-type", function () {
                        refresh();
                    });

                    var si = null;

                    function refresh() {
                        si && clearTimeout(si);
                        si = setTimeout(function () {
                            Fast.api.ajax({
                                url: 'shop/report/areas',
                                data: {
                                    date: date,
                                    id: Config.area
                                },
                                loading: false
                            }, function (res) {
                                if(res.name){
                                    option.title.text = res.name;
                                }
                                option.xAxis[0].data = res.xAxis;
                                option.series[0].data = res.orderNums;
                                option.series[1].data = res.goodsNums;
                                let max_nums = Math.max.apply(null, res.goodsNums);
                                option.yAxis[0].max = option.yAxis[1].max = parseInt(max_nums) + 10;
                                option.series[2].data = res.orderMoney;
                                let max_money = Math.max.apply(null, res.orderMoney);
                                option.yAxis[2].max = parseInt(max_money) + 100;
                                if (!res.is_oblique) {
                                    option.xAxis[0].axisLabel.rotate = 0;
                                }
                                option.series[3].data = res.rate;
                                myChart.clear();
                                console.log(option)
                                myChart.setOption(option, true);
                                if(!isFirst){
                                   //渲染区域
                                   isFirst = true;
                                   res.xAxis.length && res.xAxis[0] && areaObj.chart2.refresh(res.xAxis[0])
                                }
                                return false;
                            });
                        }, 50);
                    }
                    return {
                        chart: myChart,
                        refresh: refresh
                    };
                },
                myChart2: function () {
                    // 基于准备好的dom，初始化echarts实例
                    let myChart = Echarts.init($('#echarts2')[0], 'walden');
                    // 指定图表的配置项和数据
                    var colors = ['#5470C6', '#91CC75', '#EE6666', '#18bc9c'];
                    var date = '',area_name='';
                    // 指定图表的配置项和数据
                    let option = {
                        title: {
                            text:'区级统计',
                            subtext: ''
                        },
                        color: colors,
                        tooltip: {
                            trigger: 'axis',
                            axisPointer: {
                                type: 'cross'
                            }
                        },
                        grid: {
                            left: '15',
                            right: '4%',
                            bottom: '3%',
                            top: '11%',
                            containLabel: true,
                            y2: 120
                        },
                        toolbox: {
                            show: true,
                            feature: {
                                dataView: {
                                    show: true,
                                    readOnly: false
                                },
                                magicType: {
                                    show: true,
                                    type: ['line', 'bar']
                                },
                                restore: {
                                    show: true
                                },
                                saveAsImage: {
                                    show: true
                                }
                            }
                        },
                        legend: {
                            data: ['订单数量', '商品数量', '订单金额', '订单占比']
                        },
                        xAxis: [{
                            type: 'category',
                            axisTick: {
                                alignWithLabel: true
                            },
                            axisLabel: {
                                interval: 0,
                                rotate: -30, //倾斜度 -90 至 90 默认为0
                                // margin:2,
                                // textStyle: {
                                //     color: '#7c8893',
                                //     fontSize: 12
                                // },
                                // formatter: function(value) {
                                //     return value.split("").join("\n");
                                // }
                            },
                            offset: 10,
                            data: []
                        }],
                        yAxis: [{
                                type: 'value',
                                name: '订单数量',
                                min: 0,
                                max: 50,
                                position: 'right',
                                axisLine: {
                                    show: true,
                                    lineStyle: {
                                        color: colors[0]
                                    }
                                },
                                axisLabel: {
                                    formatter: '{value} 个'
                                }
                            },
                            {
                                type: 'value',
                                name: '商品数量',
                                min: 0,
                                max: 50,
                                position: 'right',
                                offset: 80,
                                axisLine: {
                                    show: true,
                                    lineStyle: {
                                        color: colors[1]
                                    }
                                },
                                axisLabel: {
                                    formatter: '{value} 件'
                                }
                            },
                            {
                                type: 'value',
                                name: '订单金额',
                                min: 0,
                                max: 2500,
                                position: 'left',
                                axisLine: {
                                    show: true,
                                    lineStyle: {
                                        color: colors[2]
                                    }
                                },
                                axisLabel: {
                                    formatter: '{value} 元'
                                }
                            },
                            {
                                type: 'value',
                                name: '订单占比',
                                min: 0,
                                max: 100,
                                position: 'left',
                                offset: 60,
                                axisLine: {
                                    show: true,
                                    lineStyle: {
                                        color: colors[3]
                                    }
                                },
                                axisLabel: {
                                    formatter: '{value} %'
                                }
                            }
                        ],
                        series: [{
                                name: '订单数量',
                                type: 'bar',
                                data: [],
                                markPoint: {
                                    data: [{
                                            type: 'max',
                                            name: '最大值'
                                        },
                                        {
                                            type: 'min',
                                            name: '最小值'
                                        }
                                    ]
                                }
                            },
                            {
                                name: '商品数量',
                                type: 'bar',
                                yAxisIndex: 1,
                                data: [],
                                markPoint: {
                                    data: [{
                                            type: 'max',
                                            name: '最大值'
                                        },
                                        {
                                            type: 'min',
                                            name: '最小值'
                                        }
                                    ]
                                }
                            },
                            {
                                name: '订单金额',
                                type: 'line',
                                yAxisIndex: 2,
                                data: [],
                                markLine: {
                                    data: [{
                                        type: 'average',
                                        name: '平均值'
                                    }]
                                },
                                label: {
                                    show: true
                                },
                            },
                            {
                                name: '订单占比',
                                type: 'line',
                                yAxisIndex: 3,
                                data: [],
                                markLine: {
                                    data: [{
                                        type: 'average',
                                        name: '平均值'
                                    }]
                                },
                                label: {
                                    show: true
                                },
                            }
                        ]
                    };
                   
                    // 使用刚指定的配置项和数据显示图表。
                    myChart.setOption(option);

                    $("#form2 .datetimerange").data("callback", function (start, end) {
                        date = start.format(this.locale.format) + " - " + end.format(this.locale.format);
                        $(this.element).val(date);
                        refresh();
                    });

                    //点击按钮
                    $(document).on("click", ".btn-type", function () {
                        refresh();
                    });

                    var si = null;

                    function refresh(name='') {
                        if(name){
                            area_name = name;
                        }
                        si && clearTimeout(si);
                        si = setTimeout(function () {
                            Fast.api.ajax({
                                url: 'shop/report/areas',
                                data: {
                                    date: date,
                                    name: area_name
                                },
                                loading: false
                            }, function (res) {
                                if(res.name){
                                    option.title.text = res.name;
                                }
                                option.xAxis[0].data = res.xAxis;
                                option.series[0].data = res.orderNums;
                                option.series[1].data = res.goodsNums;
                                //
                                let max_nums = Math.max.apply(null, res.goodsNums);
                                option.yAxis[0].max = option.yAxis[1].max = parseInt(max_nums) + 10;
                                option.series[2].data = res.orderMoney;

                                let max_money = Math.max.apply(null, res.orderMoney);
                                option.yAxis[2].max = parseInt(max_money) + 100;                              
                                option.xAxis[0].axisLabel.rotate = res.is_oblique && res.orderMoney.length>6?-30:0;
                                
                                console.log(option.xAxis[0].axisLabel.rotate)
                                option.series[3].data = res.rate;
                                myChart.clear();
                                console.log(option)
                                myChart.setOption(option, true);
                                return false;
                            });
                        }, 50);
                    }
                    return {
                        chart: myChart,
                        refresh: refresh
                    };
                },
            }
        }
    };
    return Controller;
});