(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["uview-ui/components/u-radio-group/u-radio-group"],{"0232":function(t,e,a){},4763:function(t,e,a){"use strict";a.r(e);var i,n=function(){var t=this,e=t.$createElement;t._self._c},u=[],r="undefined"===typeof r?{}:r,l=a("c65b"),s={name:"u-radio-group",mixins:[l["a"]],props:{disabled:{type:Boolean,default:!1},value:{type:[String,Number],default:""},activeColor:{type:String,default:"#2979ff"},size:{type:[String,Number],default:34},labelDisabled:{type:Boolean,default:!1},shape:{type:String,default:"circle"},iconSize:{type:[String,Number],default:20},width:{type:[String,Number],default:"auto"},wrap:{type:Boolean,default:!1}},created(){this.children=[]},watch:{parentData(){this.children.length&&this.children.map(t=>{"function"==typeof t.updateParentData&&t.updateParentData()})}},computed:{parentData(){return[this.value,this.disabled,this.activeColor,this.size,this.labelDisabled,this.shape,this.iconSize,this.width,this.wrap]}},methods:{setValue(t){this.children.map(e=>{e.parentData.value!=t&&(e.parentData.value="")}),this.$emit("input",t),this.$emit("change",t),setTimeout(()=>{this.dispatch("u-form-item","on-form-change",t)},60)}}},o=s,p=(a("bd35"),a("f0c5")),d=Object(p["a"])(o,n,u,!1,null,"36fc4b42",null,!1,r,i);e["default"]=d.exports},bd35:function(t,e,a){"use strict";var i=a("0232"),n=a.n(i);n.a}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'uview-ui/components/u-radio-group/u-radio-group-create-component',
    {
        'uview-ui/components/u-radio-group/u-radio-group-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("4763"))
        })
    },
    [['uview-ui/components/u-radio-group/u-radio-group-create-component']]
]);
