(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["uview-ui/components/u-mask/u-mask"],{5737:function(t,e,o){"use strict";o.r(e);var s,a=function(){var t=this,e=t.$createElement,o=(t._self._c,t.__get_style([t.maskStyle,t.zoomStyle]));t._isMounted||(t.e0=function(t){t.stopPropagation(),t.preventDefault()}),t.$mp.data=Object.assign({},{$root:{s0:o}})},n=[],l="undefined"===typeof l?{}:l,i={name:"u-mask",props:{show:{type:Boolean,default:!1},zIndex:{type:[Number,String],default:""},customStyle:{type:Object,default(){return{}}},zoom:{type:Boolean,default:!0},duration:{type:[Number,String],default:300},maskClickAble:{type:Boolean,default:!0}},data(){return{zoomStyle:{transform:""},scale:"scale(1.2, 1.2)"}},watch:{show(t){t&&this.zoom?this.zoomStyle.transform="scale(1, 1)":!t&&this.zoom&&(this.zoomStyle.transform=this.scale)}},computed:{maskStyle(){let t={backgroundColor:"rgba(0, 0, 0, 0.6)"};return this.show?t.zIndex=this.zIndex?this.zIndex:this.$u.zIndex.mask:t.zIndex=-1,t.transition=`all ${this.duration/1e3}s ease-in-out`,Object.keys(this.customStyle).length&&(t={...t,...this.customStyle}),t}},methods:{click(){this.maskClickAble&&this.$emit("click")}}},u=i,c=(o("e16f"),o("f0c5")),r=Object(c["a"])(u,a,n,!1,null,"4a660e38",null,!1,l,s);e["default"]=r.exports},cb31:function(t,e,o){},e16f:function(t,e,o){"use strict";var s=o("cb31"),a=o.n(s);a.a}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'uview-ui/components/u-mask/u-mask-create-component',
    {
        'uview-ui/components/u-mask/u-mask-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("5737"))
        })
    },
    [['uview-ui/components/u-mask/u-mask-create-component']]
]);
