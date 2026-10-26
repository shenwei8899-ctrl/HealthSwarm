<script setup>
import { memberAge, shanghaiDate } from '../utils/member-age.js'
defineProps({ member: { type: Object, required: true } })
</script>
<template>
  <view class="basic-fields">
    <label class="basic-row"><text>姓名／称呼</text><input v-model="member.name" aria-label="姓名或称呼" placeholder="请输入" maxlength="40" /></label>
    <view class="basic-row"><text>性别</text><picker :range="['女','男','未填写']" @change="member.gender=['女','男','未填写'][$event.detail.value]"><view class="picker-value"><text>{{member.gender||'未填写'}}</text><text class="chevron">›</text></view></picker></view>
    <label class="basic-row"><text>与我的关系</text><input v-model="member.relation" aria-label="与我的关系" placeholder="请输入" maxlength="30" /></label>
    <view class="basic-row"><text>出生日期</text><picker mode="date" :end="shanghaiDate()" :value="member.birthDate" @change="member.birthDate=$event.detail.value;member.age=memberAge(member).years"><view class="picker-value" :class="{placeholder:!member.birthDate}"><text>{{member.birthDate||'请选择'}}</text><text class="chevron">›</text></view></picker></view>
    <view class="measurements">
      <label class="measure"><text>身高 <text class="unit">cm</text></text><input v-model="member.height" type="digit" aria-label="身高厘米，可后补" placeholder="可后补" /></label>
      <label class="measure"><text>体重 <text class="unit">kg</text></text><input v-model="member.weight" type="digit" aria-label="体重公斤，可后补" placeholder="可后补" /></label>
    </view>
  </view>
</template>
<style scoped>
.basic-fields{border:1rpx solid #e9ebef;border-radius:24rpx;padding:0 24rpx;background:#fff;color:#22252b}.basic-row{display:flex;align-items:center;gap:24rpx;min-height:50px;border-bottom:1rpx solid #f0f1f4;font-size:30rpx}.basic-row>text{color:#777d8d;flex-shrink:0}.basic-row input{flex:1;min-width:0;text-align:right;height:48px;font-size:30rpx;color:#24262c}.basic-row picker{flex:1;min-width:0}.picker-value{display:flex;align-items:center;justify-content:flex-end;gap:20rpx;min-height:48px}.placeholder{color:#969dab}.chevron{color:#9299a8;font-size:36rpx}.measurements{display:grid;grid-template-columns:1fr 1fr;gap:20rpx;padding:20rpx 0 24rpx}.measure{padding:16rpx 20rpx 4rpx;border:1rpx solid #ebedf2;border-radius:18rpx;font-size:27rpx;color:#777d8d}.unit{font-size:24rpx;margin-left:6rpx}.measure input{height:44px;font-size:30rpx;color:#24262c;min-width:0}
</style>
