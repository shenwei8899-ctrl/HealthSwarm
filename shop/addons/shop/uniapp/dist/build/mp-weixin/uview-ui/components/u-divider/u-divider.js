(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["uview-ui/components/u-divider/u-divider"],{"2a64":function(t,e,i){"use strict";var r=i("c808"),l=i.n(r);l.a},"7b48":function(t,e,i){"use strict";i.r(e);var r,l=function(){var t=this,e=t.$createElement,i=(t._self._c,t.__get_style([t.lineStyle])),r=t.__get_style([t.lineStyle]);t.$mp.data=Object.assign({},{$root:{s0:i,s1:r}})},o=[],n="undefined"===typeof n?{}:n,a={name:"u-divider",props:{halfWidth:{type:[Number,String],default:150},borderColor:{type:String,default:"#dcdfe6"},type:{type:String,default:"primary"},color:{type:String,default:"#909399"},fontSize:{type:[Number,String],default:26},bgColor:{type:String,default:"#ffffff"},height:{type:[Number,String],default:"auto"},marginTop:{type:[String,Number],default:0},marginBottom:{type:[String,Number],default:0},useSlot:{type:Boolean,default:!0}},computed:{lineStyle(){let t={};return-1!=String(this.halfWidth).indexOf("%")?t.width=this.halfWidth:t.width=this.halfWidth+"rpx",this.borderColor&&(t.borderColor=this.borderColor),t}},methods:{click(){this.$emit("click")}}},d=a,u=(i("2a64"),i("f0c5")),f=Object(u["a"])(d,l,o,!1,null,"381df0b4",null,!1,n,r);e["default"]=f.exports},c808:function(t,e,i){}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'uview-ui/components/u-divider/u-divider-create-component',
    {
        'uview-ui/components/u-divider/u-divider-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("7b48"))
        })
    },
    [['uview-ui/components/u-divider/u-divider-create-component']]
]);
