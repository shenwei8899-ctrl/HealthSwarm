(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["uview-ui/components/u-collapse/u-collapse"],{3218:function(e,t,a){},"65b0":function(e,t,a){"use strict";a.r(t);var n,o=function(){var e=this,t=e.$createElement;e._self._c},l=[],r="undefined"===typeof r?{}:r,c={name:"u-collapse",props:{accordion:{type:Boolean,default:!0},headStyle:{type:Object,default(){return{}}},bodyStyle:{type:Object,default(){return{}}},itemStyle:{type:Object,default(){return{}}},arrow:{type:Boolean,default:!0},arrowColor:{type:String,default:"#909399"},hoverClass:{type:String,default:"u-hover-class"}},created(){this.childrens=[]},data(){return{}},methods:{init(){this.childrens.forEach((e,t)=>{e.init()})},onChange(){let e=[];this.childrens.forEach((t,a)=>{t.isShow&&e.push(t.nameSync)}),this.accordion&&(e=e.join("")),this.$emit("change",e)}}},i=c,s=(a("97b8"),a("f0c5")),u=Object(s["a"])(i,o,l,!1,null,"3ad21493",null,!1,r,n);t["default"]=u.exports},"97b8":function(e,t,a){"use strict";var n=a("3218"),o=a.n(n);o.a}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'uview-ui/components/u-collapse/u-collapse-create-component',
    {
        'uview-ui/components/u-collapse/u-collapse-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("65b0"))
        })
    },
    [['uview-ui/components/u-collapse/u-collapse-create-component']]
]);
