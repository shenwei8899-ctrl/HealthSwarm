(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["uview-ui/components/u-message-input/u-message-input"],{"33ef":function(e,t,a){},e7e0:function(e,t,a){"use strict";a.r(t);var l,n=function(){var e=this,t=e.$createElement;e._self._c},r=[],i="undefined"===typeof i?{}:i,u={name:"u-message-input",props:{maxlength:{type:[Number,String],default:4},dotFill:{type:Boolean,default:!1},mode:{type:String,default:"box"},value:{type:[String,Number],default:""},breathe:{type:Boolean,default:!0},focus:{type:Boolean,default:!1},bold:{type:Boolean,default:!1},fontSize:{type:[String,Number],default:60},activeColor:{type:String,default:"#2979ff"},inactiveColor:{type:String,default:"#606266"},width:{type:[Number,String],default:"80"},disabledKeyboard:{type:Boolean,default:!1}},watch:{value:{immediate:!0,handler(e){e=String(e),this.valueModel=e.substring(0,this.maxlength)}}},data(){return{valueModel:""}},computed:{animationClass(){return e=>this.breathe&&this.charArr.length==e?"u-breathe":""},charArr(){return this.valueModel.split("")},charArrLength(){return this.charArr.length},loopCharArr(){return new Array(this.maxlength)}},methods:{getVal(e){let{value:t}=e.detail;this.valueModel=t,String(t).length>this.maxlength||(this.$emit("change",t),String(t).length==this.maxlength&&this.$emit("finish",t))}}},o=u,s=(a("f36f"),a("f0c5")),h=Object(s["a"])(o,n,r,!1,null,"770339f0",null,!1,i,l);t["default"]=h.exports},f36f:function(e,t,a){"use strict";var l=a("33ef"),n=a.n(l);n.a}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'uview-ui/components/u-message-input/u-message-input-create-component',
    {
        'uview-ui/components/u-message-input/u-message-input-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("e7e0"))
        })
    },
    [['uview-ui/components/u-message-input/u-message-input-create-component']]
]);
