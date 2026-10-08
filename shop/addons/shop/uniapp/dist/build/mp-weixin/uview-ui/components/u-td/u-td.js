(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["uview-ui/components/u-td/u-td"],{"0c3f":function(t,e,i){},"2e61":function(t,e,i){"use strict";i.r(e);var n,a=function(){var t=this,e=t.$createElement,i=(t._self._c,t.__get_style([t.tdStyle]));t.$mp.data=Object.assign({},{$root:{s0:i}})},r=[],o="undefined"===typeof o?{}:o,s={name:"u-td",props:{width:{type:[Number,String],default:"auto"}},data(){return{tdStyle:{}}},created(){this.parent=!1},mounted(){if(this.parent=this.$u.$parent.call(this,"u-table"),this.parent){let t={};"auto"!=this.width&&(t.flex="0 0 "+this.width),t.textAlign=this.parent.align,t.fontSize=this.parent.fontSize+"rpx",t.padding=this.parent.padding,t.borderBottom="solid 1px "+this.parent.borderColor,t.borderRight="solid 1px "+this.parent.borderColor,t.color=this.parent.color,this.tdStyle=t}}},l=s,d=(i("6819"),i("f0c5")),p=Object(d["a"])(l,a,r,!1,null,"4aa037f0",null,!1,o,n);e["default"]=p.exports},6819:function(t,e,i){"use strict";var n=i("0c3f"),a=i.n(n);a.a}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'uview-ui/components/u-td/u-td-create-component',
    {
        'uview-ui/components/u-td/u-td-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("2e61"))
        })
    },
    [['uview-ui/components/u-td/u-td-create-component']]
]);
