(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["components/fa-replys/fa-replys"],{"2b4f":function(t,e,o){"use strict";o.r(e);var s,n=function(){var t=this,e=t.$createElement,o=(t._self._c,{width:"80vw",backgroundColor:t.theme.bgColor,color:t.theme.color});t.$mp.data=Object.assign({},{$root:{a0:o}})},a=[],i="undefined"===typeof i?{}:i,l={name:"fa-replys",props:{value:{type:Boolean,default:!1},pid:{type:[Number,String],default:""}},data(){return{content:""}},methods:{close(){this.$emit("input",!1)},submit(){this.content.trim()?this.$api.commentReply({pid:this.pid,content:this.content}).then(t=>{this.content="",this.$u.toast(t.msg),this.close(),this.$emit("success")}):this.$u.toast("请输入回复内容")}}},c=l,p=o("f0c5"),r=Object(p["a"])(c,n,a,!1,null,null,null,!1,i,s);e["default"]=r.exports}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'components/fa-replys/fa-replys-create-component',
    {
        'components/fa-replys/fa-replys-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("2b4f"))
        })
    },
    [['components/fa-replys/fa-replys-create-component']]
]);
