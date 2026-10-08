(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["uview-ui/components/u-form/u-form"],{3281:function(e,t,r){"use strict";var l=r("fb14"),n=r.n(l);n.a},cd95:function(e,t,r){"use strict";r.r(t);var l,n=function(){var e=this,t=e.$createElement;e._self._c},s=[],i="undefined"===typeof i?{}:i,a={name:"u-form",props:{model:{type:Object,default(){return{}}},errorType:{type:Array,default(){return["message","toast"]}},borderBottom:{type:Boolean,default:!0},labelPosition:{type:String,default:"left"},labelWidth:{type:[String,Number],default:90},labelAlign:{type:String,default:"left"},labelStyle:{type:Object,default(){return{}}}},provide(){return{uForm:this}},data(){return{rules:{}}},created(){this.fields=[]},methods:{setRules(e){this.rules=e},resetFields(){this.fields.map(e=>{e.resetField()})},validate(e){return new Promise(t=>{let r=!0,l=0,n=[];this.fields.map(s=>{s.validation("",s=>{s&&(r=!1,n.push(s)),++l===this.fields.length&&(t(r),-1===this.errorType.indexOf("none")&&this.errorType.indexOf("toast")>=0&&n.length&&this.$u.toast(n[0]),"function"==typeof e&&e(r))})})})}}},o=a,u=(r("3281"),r("f0c5")),f=Object(u["a"])(o,n,s,!1,null,"63833a15",null,!1,i,l);t["default"]=f.exports},fb14:function(e,t,r){}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'uview-ui/components/u-form/u-form-create-component',
    {
        'uview-ui/components/u-form/u-form-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("cd95"))
        })
    },
    [['uview-ui/components/u-form/u-form-create-component']]
]);
