(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["components/fa-fields/fa-fields"],{"06be":function(e,t,n){"use strict";(function(e){t["a"]={props:{fields:{type:Array,default(){return[]}}},computed:{listSelects(){return e=>{if(!e)return e;let t=[],n=e.value.split(",");return n.forEach(n=>{t.push(e.content_list[n])}),t.join(",")}},fileType(){return e=>{var t=e.lastIndexOf("."),n=e.length;return e.substring(t,n)}}},data(){return{}},methods:{lookMap(t){t&&e.openLocation({latitude:parseFloat(t.lat),longitude:parseFloat(t.lng),success:function(){}})},swipers(t){e.previewImage({current:t,urls:this.detail.images_text,longPressActions:{itemList:["发送给朋友","保存图片","收藏"],success:function(e){},fail:function(e){}}})}}}}).call(this,n("543d")["default"])},"14c5":function(e,t,n){"use strict";var s=n("23ea"),i=n.n(s);i.a},"23ea":function(e,t,n){},e7d8:function(e,t,n){"use strict";n.r(t);var s,i=function(){var e=this,t=e.$createElement,n=(e._self._c,e.__map(e.fields,(function(t,n){var s=e.__get_orig(t),i=["string","text","number","selectpage"].indexOf(t.type),a=["files","file"].indexOf(t.type),l="selectpages"==t.type?t.value.join(","):null,r="selects"==t.type||"checkbox"==t.type?e.listSelects(t):null,u=["images","image"].indexOf(t.type),c=["date","time","datetime","datetimerange"].indexOf(t.type);return{$orig:s,g0:i,g1:a,g2:l,m0:r,g3:u,g4:c}})));e.$mp.data=Object.assign({},{$root:{l0:n}})},a=[],l="undefined"===typeof l?{}:l,r=n("06be"),u=r["a"],c=(n("14c5"),n("f0c5")),o=Object(c["a"])(u,i,a,!1,null,"404b8a56",null,!1,l,s);t["default"]=o.exports}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'components/fa-fields/fa-fields-create-component',
    {
        'components/fa-fields/fa-fields-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("e7d8"))
        })
    },
    [['components/fa-fields/fa-fields-create-component']]
]);
