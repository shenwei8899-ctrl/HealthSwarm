(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["uview-ui/components/u-col/u-col"],{"653f":function(t,e,i){"use strict";var s=i("8b84"),u=i.n(s);u.a},8320:function(t,e,i){"use strict";i.r(e);var s,u=function(){var t=this,e=t.$createElement,i=(t._self._c,Number(t.gutter));t.$mp.data=Object.assign({},{$root:{m0:i}})},n=[],a="undefined"===typeof a?{}:a,r={name:"u-col",props:{span:{type:[Number,String],default:12},offset:{type:[Number,String],default:0},justify:{type:String,default:"start"},align:{type:String,default:"center"},textAlign:{type:String,default:"left"},stop:{type:Boolean,default:!0}},data(){return{gutter:20}},created(){this.parent=!1},mounted(){this.parent=this.$u.$parent.call(this,"u-row"),this.parent&&(this.gutter=this.parent.gutter)},computed:{uJustify(){return"end"==this.justify||"start"==this.justify?"flex-"+this.justify:"around"==this.justify||"between"==this.justify?"space-"+this.justify:this.justify},uAlignItem(){return"top"==this.align?"flex-start":"bottom"==this.align?"flex-end":this.align}},methods:{click(t){this.$emit("click")}}},l=r,f=(i("653f"),i("f0c5")),o=Object(f["a"])(l,u,n,!1,null,null,null,!1,a,s);e["default"]=o.exports},"8b84":function(t,e,i){}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'uview-ui/components/u-col/u-col-create-component',
    {
        'uview-ui/components/u-col/u-col-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("8320"))
        })
    },
    [['uview-ui/components/u-col/u-col-create-component']]
]);
