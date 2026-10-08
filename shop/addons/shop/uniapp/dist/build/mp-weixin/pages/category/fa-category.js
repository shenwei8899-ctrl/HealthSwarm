(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["pages/category/fa-category"],{"50e6":function(t,e,i){},"5aa0":function(t,e,i){"use strict";i.r(e);var s,a=function(){var t=this,e=t.$createElement,i=(t._self._c,t.__get_style([t.height])),s=t.row.id?t.row.goods.length:null;t.$mp.data=Object.assign({},{$root:{s0:i,g0:s}})},n=[],r="undefined"===typeof r?{}:r,c=i("d631"),h=c["a"],u=(i("bc6b"),i("f0c5")),o=Object(u["a"])(h,a,n,!1,null,"ffffe244",null,!1,r,s);e["default"]=o.exports},bc6b:function(t,e,i){"use strict";var s=i("50e6"),a=i.n(s);a.a},d631:function(t,e,i){"use strict";(function(t){e["a"]={name:"fa-category",props:{height:{type:Object,default(){return{}}}},mounted(){this.current=this.vuex_current,this.getCategory()},data(){return{category:[],row:{},scrollTop:0,current:0,menuHeight:0,menuItemHeight:0}},methods:{async swichMenu(t,e){e!=this.current&&(this.row=t,this.current=e,this.$u.vuex("vuex_current",e),0!=this.menuHeight&&0!=this.menuItemHeight||(await this.getElRect("menu-scroll-view","menuHeight"),await this.getElRect("u-tab-item","menuItemHeight")),this.scrollTop=e*this.menuItemHeight+this.menuItemHeight/2-this.menuHeight/2)},getElRect(e,i){new Promise((s,a)=>{const n=t.createSelectorQuery().in(this);n.select("."+e).fields({size:!0},t=>{t?this[i]=t.height:setTimeout(()=>{this.getElRect(e)},10)}).exec()})},getCategory(){this.$api.getCategory({category_mode:1}).then(t=>{1==t.code&&(this.category=t.data,t.data.length>0&&(this.row=void 0==t.data[this.current]?t.data[0]:t.data[this.current]))})}}}}).call(this,i("543d")["default"])}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'pages/category/fa-category-create-component',
    {
        'pages/category/fa-category-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("5aa0"))
        })
    },
    [['pages/category/fa-category-create-component']]
]);
