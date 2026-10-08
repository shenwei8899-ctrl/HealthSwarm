(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["uview-ui/components/u-line/u-line"],{"04b2":function(t,e,i){"use strict";i.r(e);var r,n=function(){var t=this,e=t.$createElement,i=(t._self._c,t.__get_style([t.lineStyle]));t.$mp.data=Object.assign({},{$root:{s0:i}})},o=[],l="undefined"===typeof l?{}:l,a={name:"u-line",props:{color:{type:String,default:"#e4e7ed"},length:{type:String,default:"100%"},direction:{type:String,default:"row"},hairLine:{type:Boolean,default:!0},margin:{type:String,default:"0"},borderStyle:{type:String,default:"solid"}},computed:{lineStyle(){let t={};return t.margin=this.margin,"row"==this.direction?(t.borderBottomWidth="1px",t.borderBottomStyle=this.borderStyle,t.width=this.$u.addUnit(this.length),this.hairLine&&(t.transform="scaleY(0.5)")):(t.borderLeftWidth="1px",t.borderLeftStyle=this.borderStyle,t.height=this.$u.addUnit(this.length),this.hairLine&&(t.transform="scaleX(0.5)")),t.borderColor=this.color,t}}},d=a,s=(i("a50d"),i("f0c5")),u=Object(s["a"])(d,n,o,!1,null,"6b54d216",null,!1,l,r);e["default"]=u.exports},a50d:function(t,e,i){"use strict";var r=i("f3c9"),n=i.n(r);n.a},f3c9:function(t,e,i){}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'uview-ui/components/u-line/u-line-create-component',
    {
        'uview-ui/components/u-line/u-line-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("04b2"))
        })
    },
    [['uview-ui/components/u-line/u-line-create-component']]
]);
