(global["webpackJsonp"]=global["webpackJsonp"]||[]).push([["uview-ui/components/u-notice-bar/u-notice-bar"],{"294e":function(e,t,o){},3011:function(e,t,o){"use strict";var n=o("294e"),l=o.n(n);l.a},"330e":function(e,t,o){"use strict";o.r(t);var n,l=function(){var e=this,t=e.$createElement;e._self._c},a=[],i="undefined"===typeof i?{}:i,u={name:"u-notice-bar",props:{list:{type:Array,default(){return[]}},type:{type:String,default:"warning"},volumeIcon:{type:Boolean,default:!0},volumeSize:{type:[Number,String],default:34},moreIcon:{type:Boolean,default:!1},closeIcon:{type:Boolean,default:!1},autoplay:{type:Boolean,default:!0},color:{type:String,default:""},bgColor:{type:String,default:""},mode:{type:String,default:"horizontal"},show:{type:Boolean,default:!0},fontSize:{type:[Number,String],default:28},duration:{type:[Number,String],default:2e3},speed:{type:[Number,String],default:160},isCircular:{type:Boolean,default:!0},playState:{type:String,default:"play"},disableTouch:{type:Boolean,default:!0},borderRadius:{type:[Number,String],default:0},padding:{type:[Number,String],default:"18rpx 24rpx"},noListHidden:{type:Boolean,default:!0}},computed:{isShow(){return 0!=this.show&&(1!=this.noListHidden||0!=this.list.length)}},methods:{click(e){this.$emit("click",e)},close(){this.$emit("close")},getMore(){this.$emit("getMore")},end(){this.$emit("end")}}},r=u,d=(o("3011"),o("f0c5")),p=Object(d["a"])(r,l,a,!1,null,"358116f6",null,!1,i,n);t["default"]=p.exports}}]);
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'uview-ui/components/u-notice-bar/u-notice-bar-create-component',
    {
        'uview-ui/components/u-notice-bar/u-notice-bar-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('543d')['createComponent'](__webpack_require__("330e"))
        })
    },
    [['uview-ui/components/u-notice-bar/u-notice-bar-create-component']]
]);
