(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["components/fa-share/fa-share"],{4997:function(e,t,a){"use strict";a.r(t);var i,n=function(){var e=this,t=e.$createElement;e._self._c},r=[],l="undefined"===typeof l?{}:l,o=(a("26f9"),{name:"fa-app-share",props:{value:{type:Boolean,default:!1},goodsId:{type:[Number,String],default:""},title:{type:String,default:""},summary:{type:String,default:""},href:{type:String,default:""},imageUrl:{type:String,default:""}},data(){let e=[];return e=[{name:"生成海报",icon:"photo",size:60,color:"#2979ff",type:0,provider:"weixin"},{name:"分享好友",icon:"weixin-circle-fill",size:60,color:"#44b549",type:0,provider:"weixin"}],{list:e}},methods:{open(){},hide(){this.$emit("input",!1)},share(e,t){e||this.$emit("shares")}}}),p=o,s=a("f0c5"),f=Object(s["a"])(p,n,r,!1,null,"0b555195",null,!1,l,i);t["default"]=f.exports}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'components/fa-share/fa-share-create-component',
    {
        'components/fa-share/fa-share-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("4997"))
        })
    },
    [['components/fa-share/fa-share-create-component']]
]);
