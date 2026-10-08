<script setup>
import { ref, watch } from 'vue'
const props=defineProps({open:Boolean,members:Array,selected:Array,meal:String})
const emit=defineEmits(['close','confirm'])
const draft=ref([])
watch(()=>props.open,value=>{if(value)draft.value=[...(props.selected||[])]})
function toggle(id){const i=draft.value.indexOf(id);i<0?draft.value.push(id):draft.value.splice(i,1)}
</script>
<template><view v-if="open" class="sheet-mask" @click.self="emit('close')"><view class="sheet diner-sheet"><view class="picker-head"><text class="section-title">{{meal}}就餐成员</text><button @click="emit('close')">×</button></view><button v-for="m in members" :key="m.id" class="member-choice" @click="toggle(m.id)"><text>{{m.name}}</text><text :class="{checked:draft.includes(m.id)}">{{draft.includes(m.id)?'✓':'○'}}</text></button><text class="helper">{{meal==='默认'?'设置后用于未单独调整餐次的默认成员，不修改已支付计划。':'只调整本餐，早餐、午餐和晚餐可以不同。'}}</text><view class="picker-actions"><button class="secondary-button" @click="emit('close')">取消</button><button class="primary-button" :disabled="!draft.length" @click="emit('confirm',[...draft])">确认</button></view></view></view></template>
<style scoped>.diner-sheet{max-height:65vh;overflow:auto}.picker-head,.member-choice{display:flex;align-items:center;justify-content:space-between}.picker-head button{font-size:40rpx}.member-choice{width:100%;padding:24rpx 4rpx;border-bottom:1rpx solid #dae2d4;text-align:left;font-size:26rpx}.checked{color:#246b50;font-weight:900}.picker-actions{display:grid;grid-template-columns:1fr 1fr;gap:16rpx;margin-top:24rpx}.primary-button[disabled]{opacity:.4}.helper{display:block;margin-top:20rpx;color:#687a72;font-size:21rpx}</style>
