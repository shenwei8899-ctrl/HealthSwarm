(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["uview-ui/components/u-switch/u-switch"],{"0510":function(t,e,i){},"565f":function(t,e,i){"use strict";i.r(e);var a,l=function(){var t=this,e=t.$createElement,i=(t._self._c,t.__get_style([t.switchStyle])),a=t.$u.addUnit(this.size),l=t.$u.addUnit(this.size);t.$mp.data=Object.assign({},{$root:{s0:i,g0:a,g1:l}})},n=[],o="undefined"===typeof o?{}:o,u=i("8370"),s=u["a"],c=(i("c1e2"),i("f0c5")),r=Object(c["a"])(s,l,n,!1,null,"c54dc83c",null,!1,o,a);e["default"]=r.exports},8370:function(t,e,i){"use strict";(function(t){e["a"]={name:"u-switch",props:{loading:{type:Boolean,default:!1},disabled:{type:Boolean,default:!1},size:{type:[Number,String],default:50},activeColor:{type:String,default:"#2979ff"},inactiveColor:{type:String,default:"#ffffff"},value:{type:Boolean,default:!1},vibrateShort:{type:Boolean,default:!1},activeValue:{type:[Number,String,Boolean],default:!0},inactiveValue:{type:[Number,String,Boolean],default:!1}},data(){return{}},computed:{switchStyle(){let t={};return t.fontSize=this.size+"rpx",t.backgroundColor=this.value?this.activeColor:this.inactiveColor,t},loadingColor(){return this.value?this.activeColor:null}},methods:{onClick(){this.disabled||this.loading||(this.vibrateShort&&t.vibrateShort(),this.$emit("input",!this.value),this.$nextTick(()=>{this.$emit("change",this.value?this.activeValue:this.inactiveValue)}))}}}}).call(this,i("543d")["default"])},c1e2:function(t,e,i){"use strict";var a=i("0510"),l=i.n(a);l.a}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'uview-ui/components/u-switch/u-switch-create-component',
    {
        'uview-ui/components/u-switch/u-switch-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("565f"))
        })
    },
    [['uview-ui/components/u-switch/u-switch-create-component']]
]);
