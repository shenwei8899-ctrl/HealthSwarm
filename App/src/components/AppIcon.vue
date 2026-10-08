<script setup>
defineProps({ name: { type: String, default: 'grid' }, size: { type: Number, default: 40 } })
</script>
<template><view class="app-icon" :class="'i-'+name" :style="{width:size+'rpx',height:size+'rpx'}"><view class="a"></view><view class="b"></view><view class="c"></view></view></template>
<style scoped>
.app-icon{position:relative;display:inline-block;flex:none;color:inherit;box-sizing:border-box}.app-icon view{position:absolute;box-sizing:border-box}
.i-user .a,.i-family .a{width:36%;height:36%;border:2px solid currentColor;border-radius:50%;top:3%;left:32%}.i-user .b,.i-family .b{width:76%;height:43%;border:2px solid currentColor;border-radius:50% 50% 18% 18%;bottom:4%;left:12%}.i-family .c{width:24%;height:28%;border:2px solid currentColor;border-radius:50%;left:2%;top:22%;background:transparent}
.i-calendar .a,.i-record .a,.i-grid .a{inset:12% 8% 4%;border:2px solid currentColor;border-radius:5px}.i-calendar .b,.i-record .b{left:18%;right:18%;top:37%;height:2px;background:currentColor}.i-calendar .c{left:28%;top:0;width:44%;height:24%;border-left:2px solid currentColor;border-right:2px solid currentColor}
.i-camera .a{inset:20% 3% 10%;border:2px solid currentColor;border-radius:5px}.i-camera .b{inset:37% 31% 22%;border:2px solid currentColor;border-radius:50%}.i-camera .c{top:7%;left:29%;width:42%;height:15%;border:2px solid currentColor;border-bottom:0;border-radius:3px 3px 0 0}
.i-history .a{inset:8%;border:2px solid currentColor;border-radius:50%}.i-history .b{left:47%;top:23%;width:2px;height:29%;background:currentColor}.i-history .c{left:47%;top:49%;width:25%;height:2px;background:currentColor}
.i-chat .a,.i-memory .a{inset:9% 4% 19%;border:2px solid currentColor;border-radius:7px}.i-chat .b,.i-memory .b{width:21%;height:20%;left:18%;bottom:4%;border-left:2px solid currentColor;transform:skewY(-35deg)}.i-chat .c,.i-memory .c{left:25%;right:25%;top:40%;height:2px;background:currentColor}
.i-order .a{inset:12% 14% 4%;border:2px solid currentColor;border-radius:5px}.i-order .b{left:30%;right:30%;top:3%;height:22%;border:2px solid currentColor;border-radius:3px;background:#fff}.i-order .c{left:32%;right:32%;top:52%;height:2px;background:currentColor;box-shadow:0 5px currentColor}
.i-device .a{inset:3% 23%;border:2px solid currentColor;border-radius:6px}.i-device .b{width:14%;height:2px;bottom:15%;left:43%;background:currentColor}
.i-shield .a{inset:4% 15%;border:2px solid currentColor;border-radius:7px 7px 50% 50%}.i-shield .b{width:22%;height:35%;border-right:2px solid currentColor;border-bottom:2px solid currentColor;transform:rotate(45deg);left:38%;top:26%}
.i-supplier .a{inset:19% 8% 7%;border:2px solid currentColor;border-radius:4px}.i-supplier .b{inset:3% 30% 72%;border:2px solid currentColor;border-radius:4px}.i-supplier .c{top:45%;height:2px;left:8%;right:8%;background:currentColor}
.i-mic .a{width:34%;height:59%;border:2px solid currentColor;border-radius:15px;top:2%;left:33%}.i-mic .b{inset:29% 20% 21%;border:2px solid currentColor;border-top:0;border-radius:0 0 16px 16px}.i-mic .c{width:2px;height:22%;bottom:2%;left:48%;background:currentColor}
.i-arrow .a{left:47%;top:14%;width:2px;height:71%;background:currentColor}.i-arrow .b{left:28%;top:15%;width:43%;height:43%;border-top:2px solid currentColor;border-left:2px solid currentColor;transform:rotate(45deg)}
</style>
