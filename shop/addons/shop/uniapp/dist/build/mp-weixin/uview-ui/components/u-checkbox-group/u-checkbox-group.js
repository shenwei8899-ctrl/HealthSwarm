(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["uview-ui/components/u-checkbox-group/u-checkbox-group"],{"360b":function(e,t,a){"use strict";a.r(t);var n,u=function(){var e=this,t=e.$createElement;e._self._c},i=[],o="undefined"===typeof o?{}:o,l=a("c65b"),r={name:"u-checkbox-group",mixins:[l["a"]],props:{max:{type:[Number,String],default:999},disabled:{type:Boolean,default:!1},name:{type:[Boolean,String],default:""},labelDisabled:{type:Boolean,default:!1},shape:{type:String,default:"square"},activeColor:{type:String,default:"#2979ff"},size:{type:[String,Number],default:34},width:{type:String,default:"auto"},wrap:{type:Boolean,default:!1},iconSize:{type:[String,Number],default:20}},data(){return{}},created(){this.children=[]},methods:{emitEvent(){let e=[];this.children.map(t=>{t.value&&e.push(t.name)}),this.$emit("change",e),setTimeout(()=>{this.dispatch("u-form-item","on-form-change",e)},60)}}},c=r,p=(a("5807"),a("f0c5")),s=Object(p["a"])(c,u,i,!1,null,"f05e581c",null,!1,o,n);t["default"]=s.exports},5807:function(e,t,a){"use strict";var n=a("732a"),u=a.n(n);u.a},"732a":function(e,t,a){}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'uview-ui/components/u-checkbox-group/u-checkbox-group-create-component',
    {
        'uview-ui/components/u-checkbox-group/u-checkbox-group-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("360b"))
        })
    },
    [['uview-ui/components/u-checkbox-group/u-checkbox-group-create-component']]
]);
