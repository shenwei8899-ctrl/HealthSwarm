(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["components/fa-download/fa-download"],{a4a9:function(e,t,n){"use strict";(function(e){t["a"]={name:"fa-download",props:{item:{type:Object,default:{}}},computed:{fileType(){return e=>{var t=e.lastIndexOf("."),n=e.length;return e.substring(t,n)}}},data(){return{downtips:!1,description:""}},methods:{click(t){let n=this;e.downloadFile({url:t,success:t=>{200===t.statusCode&&e.saveFile({tempFilePath:t.tempFilePath,success:function(e){n.downtips=!0,n.description=e.savedFilePath},fail(e){}})},fail:function(e){}})}}}}).call(this,n("543d")["default"])},cf52:function(e,t,n){"use strict";n.r(t);var a,i=function(){var e=this,t=e.$createElement,n=(e._self._c,"files"==e.item.type?e.__map(e.item.value,(function(t,n){var a=e.__get_orig(t),i=e.fileType(t);return{$orig:a,m0:i}})):null),a="files"!=e.item.type?e.fileType(e.item.value):null;e._isMounted||(e.e0=function(t){e.downtips=!1}),e.$mp.data=Object.assign({},{$root:{l0:n,m1:a}})},l=[],o="undefined"===typeof o?{}:o,s=n("a4a9"),u=s["a"],c=n("f0c5"),f=Object(c["a"])(u,i,l,!1,null,"77ff1004",null,!1,o,a);t["default"]=f.exports}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'components/fa-download/fa-download-create-component',
    {
        'components/fa-download/fa-download-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("cf52"))
        })
    },
    [['components/fa-download/fa-download-create-component']]
]);
