(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["components/fa-navbar/fa-navbar"],{"9b4d":function(t,e,a){"use strict";(function(t){e["a"]={name:"fa-navbar",props:{title:{type:String,default:"标题"},borderBottom:{type:Boolean,default:!0},backIndex:{type:Number,default:1}},computed:{navbar(){return this.vuex_config.navbar?this.vuex_config.navbar:{}},tabbar(){return this.vuex_config.tabbar?this.vuex_config.tabbar:{isshow:!1,list:[]}},isBack(){let t=!0;return this.tabbar.list.some(e=>{let a=this.$util.getPath(e.path);if(a==this.pageUrl||a=="/"+this.pageUrl)return t=!1,!0}),t},isShow(){return!0}},created(){let t=getCurrentPages();this.pageUrl=t[t.length-1].route,this.pageNum=t.length},data(){return{pageUrl:"",pageNum:0}},methods:{goBack(){let e=!1,a=this.vuex_config.tabbar;a.list.forEach(t=>{let a=this.$util.getPath(t.path);a!=this.pageUrl&&a!="/"+this.pageUrl||(e=!0)}),e||(1==this.pageNum?t.$u.route({url:"/pages/index/index"}):t.$u.route({type:"back",delta:this.backIndex}))}}}}).call(this,a("543d")["default"])},ff31:function(t,e,a){"use strict";a.r(e);var r,n=function(){var t=this,e=t.$createElement;t._self._c},i=[],l="undefined"===typeof l?{}:l,u=a("9b4d"),s=u["a"],o=a("f0c5"),h=Object(o["a"])(s,n,i,!1,null,null,null,!1,l,r);e["default"]=h.exports}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'components/fa-navbar/fa-navbar-create-component',
    {
        'components/fa-navbar/fa-navbar-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("ff31"))
        })
    },
    [['components/fa-navbar/fa-navbar-create-component']]
]);
