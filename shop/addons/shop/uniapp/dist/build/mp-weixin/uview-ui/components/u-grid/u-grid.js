(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["uview-ui/components/u-grid/u-grid"],{"9e29":function(t,e,a){},a962:function(t,e,a){"use strict";a.r(e);var n,r=function(){var t=this,e=t.$createElement,a=(t._self._c,t.__get_style([t.gridStyle]));t.$mp.data=Object.assign({},{$root:{s0:a}})},i=[],s="undefined"===typeof s?{}:s,l={name:"u-grid",props:{col:{type:[Number,String],default:3},border:{type:Boolean,default:!0},align:{type:String,default:"left"},hoverClass:{type:String,default:"u-hover-class"}},data(){return{index:0}},watch:{parentData(){this.children.length&&this.children.map(t=>{"function"==typeof t.updateParentData&&t.updateParentData()})}},created(){this.children=[]},computed:{parentData(){return[this.hoverClass,this.col,this.size,this.border]},gridStyle(){let t={};switch(this.align){case"left":t.justifyContent="flex-start";break;case"center":t.justifyContent="center";break;case"right":t.justifyContent="flex-end";break;default:t.justifyContent="flex-start"}return t}},methods:{click(t){this.$emit("click",t)}}},c=l,u=(a("c33e"),a("f0c5")),o=Object(u["a"])(c,r,i,!1,null,"20f7f062",null,!1,s,n);e["default"]=o.exports},c33e:function(t,e,a){"use strict";var n=a("9e29"),r=a.n(n);r.a}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'uview-ui/components/u-grid/u-grid-create-component',
    {
        'uview-ui/components/u-grid/u-grid-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("a962"))
        })
    },
    [['uview-ui/components/u-grid/u-grid-create-component']]
]);
