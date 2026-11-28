<script setup>
import { itemPortions } from '../services/meal-item-intake.js'
defineProps({ portion: String, grams: [String, Number], disabled: Boolean })
const emit = defineEmits(['update:portion', 'update:grams', 'keyboard'])
</script>
<template>
  <view class="item-portion-fields">
    <view class="item-portion-options"><button v-for="option in itemPortions" :key="option" :class="{selected:portion===option}" :disabled="disabled" @tap.stop="emit('update:portion',option)">{{option}}</button></view>
    <view class="item-grams"><text>实际克数</text><input :value="grams" type="digit" :disabled="disabled" :adjust-position="false" placeholder="选填" aria-label="实际克数，选填" @input="emit('update:grams',$event.detail.value)" @keyboardheightchange="emit('keyboard',$event)" @blur="emit('keyboard',{detail:{height:0}})"/><text>g</text></view>
  </view>
</template>
<style scoped>
.item-portion-fields{font-weight:400;color:#51465f}.item-portion-options{display:flex;gap:7px;margin-top:10px}.item-portion-options button{display:flex;align-items:center;justify-content:center;flex:1;min-width:0;height:44px;min-height:44px;padding:0;margin:0;box-sizing:border-box;border:1px solid #eee5f4;border-radius:10px;background:#faf7fc;color:#776a84;font-size:14px;font-weight:400;line-height:1.4;text-align:center}.item-portion-options button.selected{border-color:#c7afd8;background:#eee4f6;color:#79528e;font-weight:500}.item-portion-options button:after{border:0}.item-portion-options button[disabled]{opacity:.45}.item-grams{display:flex;gap:10px;align-items:center;margin-top:10px;font-size:14px;line-height:1.5;color:#776a84}.item-grams>text{flex:none}.item-grams input{flex:1;min-width:0;height:44px;line-height:44px;text-align:center;color:#51465f;border:1px solid #e9e0f0;border-radius:10px;padding:0 12px;font-family:inherit;font-size:16px;font-weight:400;background:#fcfafd;box-sizing:border-box}
</style>
