(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["uview-ui/components/u-alert-tips/u-alert-tips"],{"12c3":function(t,e,l){"use strict";var n=l("13ae"),i=l.n(n);i.a},"13ae":function(t,e,l){},"9b1e":function(t,e,l){"use strict";l.r(e);var n,i=function(){var t=this,e=t.$createElement,l=(t._self._c,t.show?t.__get_style([t.uTitleStyle]):null),n=t.show&&t.description?t.__get_style([t.descStyle]):null;t.$mp.data=Object.assign({},{$root:{s0:l,s1:n}})},o=[],s="undefined"===typeof s?{}:s,r={name:"u-alert-tips",props:{title:{type:String,default:""},type:{type:String,default:"warning"},description:{type:String,default:""},closeAble:{type:Boolean,default:!1},closeText:{type:String,default:""},showIcon:{type:Boolean,default:!1},color:{type:String,default:""},bgColor:{type:String,default:""},borderColor:{type:String,default:""},show:{type:Boolean,default:!0},icon:{type:String,default:""},iconStyle:{type:Object,default(){return{}}},titleStyle:{type:Object,default(){return{}}},descStyle:{type:Object,default(){return{}}}},data(){return{}},computed:{uTitleStyle(){let t={};return t.fontWeight=this.description?500:"normal",this.$u.deepMerge(t,this.titleStyle)},uIcon(){return this.icon?this.icon:this.$u.type2icon(this.type)},uIconType(){return Object.keys(this.iconStyle).length?"":this.type}},methods:{click(){this.$emit("click")},close(){this.$emit("close")}}},u=r,c=(l("12c3"),l("f0c5")),a=Object(c["a"])(u,i,o,!1,null,"2dcaa8e8",null,!1,s,n);e["default"]=a.exports}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'uview-ui/components/u-alert-tips/u-alert-tips-create-component',
    {
        'uview-ui/components/u-alert-tips/u-alert-tips-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("9b1e"))
        })
    },
    [['uview-ui/components/u-alert-tips/u-alert-tips-create-component']]
]);
