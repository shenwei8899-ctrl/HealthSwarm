(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["pages/category/fa-category-three"],{"283b":function(t,e,a){"use strict";a.r(e);var r,o=function(){var t=this,e=t.$createElement,a=(t._self._c,t.__get_style([t.height]));t.$mp.data=Object.assign({},{$root:{s0:a}})},c=[],s="undefined"===typeof s?{}:s,n={name:"fa-category-three",props:{height:{type:Object,default(){return{}}}},data(){return{scrollTop:0,current:0,itemId:"",category:[],row:{},scrollRightTop:0}},mounted(){this.getCategory()},methods:{async swichMenu(t){t!=this.current&&(this.row=this.category[t],this.current=t)},getCategory(){this.$api.getCategory().then(t=>{1==t.code&&(this.category=t.data,t.data.length&&(this.row=t.data[0]))})}}},i=n,g=(a("facb"),a("f0c5")),h=Object(g["a"])(i,o,c,!1,null,"7e9f9180",null,!1,s,r);e["default"]=h.exports},d46e:function(t,e,a){},facb:function(t,e,a){"use strict";var r=a("d46e"),o=a.n(r);o.a}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'pages/category/fa-category-three-create-component',
    {
        'pages/category/fa-category-three-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("283b"))
        })
    },
    [['pages/category/fa-category-three-create-component']]
]);
