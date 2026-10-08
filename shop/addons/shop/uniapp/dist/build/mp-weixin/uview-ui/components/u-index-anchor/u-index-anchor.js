(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["uview-ui/components/u-index-anchor/u-index-anchor"],{2271:function(t,e,n){},3824:function(t,e,n){"use strict";n.r(e);var a,s=function(){var t=this,e=t.$createElement,n=(t._self._c,t.__get_style([t.wrapperStyle])),a=t.$u.guid(),s=t.__get_style([t.customAnchorStyle]);t.$mp.data=Object.assign({},{$root:{s0:n,g0:a,s1:s}})},r=[],u="undefined"===typeof u?{}:u,c={name:"u-index-anchor",props:{useSlot:{type:Boolean,default:!1},index:{type:String,default:""},customStyle:{type:Object,default(){return{}}}},data(){return{active:!1,wrapperStyle:{},anchorStyle:{}}},created(){this.parent=!1},mounted(){this.parent=this.$u.$parent.call(this,"u-index-list"),this.parent&&(this.parent.children.push(this),this.parent.updateData())},computed:{customAnchorStyle(){return Object.assign(this.anchorStyle,this.customStyle)}}},i=c,o=(n("52aa"),n("f0c5")),l=Object(o["a"])(i,s,r,!1,null,"b464d6dc",null,!1,u,a);e["default"]=l.exports},"52aa":function(t,e,n){"use strict";var a=n("2271"),s=n.n(a);s.a}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'uview-ui/components/u-index-anchor/u-index-anchor-create-component',
    {
        'uview-ui/components/u-index-anchor/u-index-anchor-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("3824"))
        })
    },
    [['uview-ui/components/u-index-anchor/u-index-anchor-create-component']]
]);
