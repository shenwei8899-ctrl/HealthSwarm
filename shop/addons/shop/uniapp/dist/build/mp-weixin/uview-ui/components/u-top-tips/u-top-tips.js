(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["uview-ui/components/u-top-tips/u-top-tips"],{"56ef":function(t,e,i){"use strict";i.r(e);var n,s=function(){var t=this,e=t.$createElement;t._self._c},u=[],r="undefined"===typeof r?{}:r,o={name:"u-top-tips",props:{navbarHeight:{type:[Number,String],default:0},zIndex:{type:[Number,String],default:""}},data(){return{timer:null,isShow:!1,title:"",type:"primary",duration:2e3}},computed:{uZIndex(){return this.zIndex?this.zIndex:this.$u.zIndex.topTips}},methods:{show(t={}){clearTimeout(this.timer),t.duration&&(this.duration=t.duration),t.type&&(this.type=t.type),this.title=t.title,this.isShow=!0,this.timer=setTimeout(()=>{this.isShow=!1,clearTimeout(this.timer),this.timer=null},this.duration)}}},a=o,p=(i("5cd6"),i("f0c5")),d=Object(p["a"])(a,s,u,!1,null,"34de15dd",null,!1,r,n);e["default"]=d.exports},"5cd6":function(t,e,i){"use strict";var n=i("f0db"),s=i.n(n);s.a},f0db:function(t,e,i){}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'uview-ui/components/u-top-tips/u-top-tips-create-component',
    {
        'uview-ui/components/u-top-tips/u-top-tips-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("56ef"))
        })
    },
    [['uview-ui/components/u-top-tips/u-top-tips-create-component']]
]);
