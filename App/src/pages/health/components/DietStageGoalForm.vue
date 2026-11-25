<script setup>
const props = defineProps({selected:{type:Array,default:()=>[]},note:{type:String,default:''},options:{type:Array,default:()=>[]},disabled:Boolean})
const emit = defineEmits(['update:selected','update:note'])
function choose(goal) {
  if (props.disabled) return
  if (props.selected.includes(goal)) emit('update:selected',props.selected.filter(item=>item!==goal))
  else if (props.selected.length<2) emit('update:selected',[...props.selected,goal])
  else uni.showToast({title:'先关注一至两个目标',icon:'none'})
}
</script>
<template>
  <view class="goal-form">
    <view class="form-row"><text class="form-label">这段时间，想先做好什么？</text><text class="form-hint">选 1—2 项</text></view>
    <view class="goal-options"><button v-for="goal in options" :key="goal" :disabled="disabled" :class="{chosen:selected.includes(goal)}" :aria-pressed="selected.includes(goal)" @click="choose(goal)">{{goal}}<text v-if="selected.includes(goal)">✓</text></button></view>
    <view class="form-row custom-label"><text class="form-label">也可以写下自己的想法</text><text class="form-hint">选填</text></view>
    <textarea :value="note" :disabled="disabled" class="goal-note" maxlength="1000" :adjust-position="true" :cursor-spacing="24" placeholder="例如：工作忙时常常顾不上吃早餐，想先把早餐规律起来……" @input="emit('update:note',$event.detail.value)"/>
  </view>
</template>
<style scoped>
.form-row{display:flex;align-items:center;justify-content:space-between;gap:10px}.form-label{font-size:14px;color:#4e4b60;font-weight:600;line-height:1.8}.form-hint{flex:none;font-size:11px;color:#a09aab}.goal-options{display:flex;flex-wrap:wrap;gap:9px;margin-top:15px}.goal-options button{margin:0;min-height:44px;padding:11px 13px;border:1px solid #e6e0ec;border-radius:12px;background:#fff;color:#85768e;font-size:13px;line-height:1.6}.goal-options button:after{border:0}.goal-options button.chosen{border-color:#b09ac9;color:#7952a5;background:#eee7f7;font-weight:600}.goal-options button>text{font-size:11px;margin-left:8px}.goal-options button[disabled]{opacity:.65}.custom-label{margin-top:28px}.goal-note{box-sizing:border-box;width:100%;height:110px;margin-top:14px;padding:14px;border:1px solid #e8e3ee;border-radius:13px;background:#fff;color:#62596f;font-size:14px;line-height:1.9}.goal-note[disabled]{opacity:.65}
</style>
