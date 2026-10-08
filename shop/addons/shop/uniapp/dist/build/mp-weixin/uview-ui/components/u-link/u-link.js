(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["uview-ui/components/u-link/u-link"],{"3a72":function(t,e,n){"use strict";var a=n("cafb"),i=n.n(a);i.a},"916f":function(t,e,n){"use strict";n.r(e);var a,i=function(){var t=this,e=t.$createElement;t._self._c},u=[],l="undefined"===typeof l?{}:l,s=n("d788"),o=s["a"],f=(n("3a72"),n("f0c5")),c=Object(f["a"])(o,i,u,!1,null,"55e071ea",null,!1,l,a);e["default"]=c.exports},cafb:function(t,e,n){},d788:function(t,e,n){"use strict";(function(t){e["a"]={name:"u-link",props:{color:{type:String,default:"#2979ff"},fontSize:{type:[String,Number],default:28},underLine:{type:Boolean,default:!1},href:{type:String,default:""},mpTips:{type:String,default:"链接已复制，请在浏览器打开"},lineColor:{type:String,default:""}},methods:{openLink(){t.setClipboardData({data:this.href,success:()=>{t.hideToast(),this.$nextTick(()=>{this.$u.toast(this.mpTips)})}})}}}}).call(this,n("543d")["default"])}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'uview-ui/components/u-link/u-link-create-component',
    {
        'uview-ui/components/u-link/u-link-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("916f"))
        })
    },
    [['uview-ui/components/u-link/u-link-create-component']]
]);
