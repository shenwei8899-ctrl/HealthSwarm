(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["components/fa-add-my/fa-add-my"],{"4dca":function(t,e,r){},dd16:function(t,e,r){"use strict";r.r(e);var o,a=function(){var t=this,e=t.$createElement,r=(t._self._c,t.__get_style([{bottom:t.bottom+"rpx",right:t.right+"rpx",borderRadius:"circle"==t.mode?"10000rpx":"8rpx",zIndex:t.zIndex},t.customStyle]));t.$mp.data=Object.assign({},{$root:{s0:r}})},n=[],d="undefined"===typeof d?{}:d,u={name:"fa-add-my",props:{type:{type:String,default:""},mode:{type:String,default:"circle"},icon:{type:String,default:"edit-pen"},tips:{type:String,default:""},bottom:{type:[Number,String],default:300},right:{type:[Number,String],default:40},zIndex:{type:[Number,String],default:"9"},iconStyle:{type:Object,default(){return{color:"#909399",fontSize:"38rpx"}}},customStyle:{type:Object,default(){return{}}}},data(){return{}},methods:{goAddMy(){"custom"!=this.type?this.$u.route("/pages/score/order"):this.$emit("custom")}}},i=u,c=(r("e654"),r("f0c5")),p=Object(c["a"])(i,a,n,!1,null,"6f56ba22",null,!1,d,o);e["default"]=p.exports},e654:function(t,e,r){"use strict";var o=r("4dca"),a=r.n(o);a.a}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'components/fa-add-my/fa-add-my-create-component',
    {
        'components/fa-add-my/fa-add-my-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("dd16"))
        })
    },
    [['components/fa-add-my/fa-add-my-create-component']]
]);
