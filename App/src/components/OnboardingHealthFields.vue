<script setup>
import { computed, ref } from 'vue'
import { diseaseOptions, preferenceGroups } from '../utils/health.js'

const props = defineProps({ member: { type: Object, required: true } })
const coreGoals = ['控糖', '控压', '控脂', '减脂', '增肌', '饮食均衡']
const coreTastes = ['清淡', '少油', '少盐', '不吃辣', '不限口味']
const healthStates = [
  { value: 'none', label: '没有已知基础病' },
  { value: 'set', label: '有基础病' },
]
const editor = ref(''), draft = ref([]), custom = ref('')
const extraGoals = computed(() => props.member.goals.filter(value => !coreGoals.includes(value)))
const extraTastes = computed(() => props.member.tastePreferences.filter(value => !coreTastes.includes(value)))
const editorTitle = computed(() => editor.value === 'goals' ? '其他饮食目标' : editor.value === 'cuisines' ? '菜系偏好' : '其他口味')
const extraOptions = computed(() => {
  const field = editor.value === 'goals' ? 'goals' : 'tastePreferences'
  const core = editor.value === 'goals' ? coreGoals : coreTastes
  return [...new Set([...preferenceGroups[field].items.filter(value => !core.includes(value) && !['其他', '自定义'].includes(value)), ...draft.value])]
})
const cuisineOptions = computed(() => [...new Set([...preferenceGroups.cuisines.items.filter(value => value !== '自定义'), ...props.member.cuisines])])

function toggle(list, value) {
  const index = list.indexOf(value)
  if (index >= 0) { list.splice(index, 1); return }
  if (['不限口味', '不限菜系', '无特别要求'].includes(value)) list.splice(0, list.length)
  else for (let i = list.length - 1; i >= 0; i--) if (['不限口味', '不限菜系', '无特别要求'].includes(list[i])) list.splice(i, 1)
  list.push(value)
}
function setHealth(value) {
  props.member.healthStatus = value
  props.member.health = value === 'none' ? '没有已知基础病' : '用户自述'
}
function openExtras(field) {
  editor.value = field
  draft.value = [...(field === 'goals' ? extraGoals.value : field === 'cuisines' ? props.member.cuisines : extraTastes.value)]
  custom.value = ''
}
function addCustom() {
  const value = custom.value.trim()
  if (!value) return
  if (!draft.value.includes(value)) toggle(draft.value, value)
  custom.value = ''
}
function saveExtras() {
  addCustom()
  if (editor.value === 'cuisines') { props.member.cuisines = [...draft.value]; editor.value = ''; return }
  const field = editor.value === 'goals' ? 'goals' : 'tastePreferences'
  const core = editor.value === 'goals' ? coreGoals : coreTastes
  props.member[field] = [...new Set([...props.member[field].filter(value => core.includes(value)), ...draft.value])]
  if (editor.value === 'tastePreferences' && draft.value.some(value => !['不限口味', '无特别要求'].includes(value))) props.member[field] = props.member[field].filter(value => !['不限口味', '无特别要求'].includes(value))
  editor.value = ''
}
</script>

<template>
  <view class="health-card">
    <text class="card-title">基础健康</text>
    <view class="health-options" role="radiogroup" aria-label="基础病情况">
      <button v-for="item in healthStates" :key="item.value" class="health-option" :class="{ chosen: member.healthStatus === item.value }" role="radio" :aria-checked="member.healthStatus === item.value" @click="setHealth(item.value)">
        <view class="radio-mark"><view v-if="member.healthStatus === item.value" /></view><text>{{ item.label }}</text>
      </button>
    </view>
    <view v-if="member.healthStatus === 'set'" class="condition-area">
      <text class="field-label">选择已知基础病，可多选</text>
      <view class="option-grid condition-grid"><button v-for="item in diseaseOptions" :key="item" :class="{ selected: member.conditions.includes(item) }" :aria-pressed="member.conditions.includes(item)" @click="toggle(member.conditions, item)">{{ item }}</button></view>
      <input v-if="member.conditions.includes('其他')" v-model="member.otherCondition" class="custom-input" placeholder="填写具体基础病" aria-label="具体基础病" />
    </view>
    <text v-if="member.healthStatus === 'set'" class="support-copy self-report">基础病信息为用户自述，不是平台确诊。</text>
  </view>

  <view class="health-card">
    <view class="card-heading"><text class="card-title">饮食目标</text><text class="multiple-hint">必填 · 可多选</text></view>
    <view class="option-grid"><button v-for="item in coreGoals" :key="item" :class="{ selected: member.goals.includes(item) }" :aria-pressed="member.goals.includes(item)" @click="toggle(member.goals, item)">{{ item }}</button></view>
    <button class="other-row" @click="openExtras('goals')"><view><text>其他目标</text><text v-if="extraGoals.length" class="extra-summary">{{ extraGoals.join('、') }}</text></view><text class="chevron">›</text></button>
  </view>

  <view class="health-card">
    <view class="card-heading"><text class="card-title">口味偏好</text><text class="multiple-hint">必填 · 可多选</text></view>
    <view class="option-grid"><button v-for="item in coreTastes" :key="item" :class="{ selected: member.tastePreferences.includes(item) }" :aria-pressed="member.tastePreferences.includes(item)" @click="toggle(member.tastePreferences, item)">{{ item }}</button><button :class="{ selected: extraTastes.length }" @click="openExtras('tastePreferences')">其他</button></view>
    <text v-if="extraTastes.length" class="extra-summary taste-summary">{{ extraTastes.join('、') }}</text>
  </view>

  <view class="health-card">
    <button class="cuisine-summary" @click="openExtras('cuisines')"><text class="cuisine-label">菜系偏好<text class="optional-label">可选</text></text><text class="cuisine-value" :class="{'cuisine-placeholder':!member.cuisines.length}">{{member.cuisines.length ? member.cuisines.join('、') : '请选择'}}</text><text class="chevron">›</text></button>
  </view>

  <view v-if="editor" class="sheet-mask" @click="editor = ''">
    <view class="sheet extras-sheet" @click.stop>
      <view class="sheet-heading"><view><text class="support-copy">{{ member.name }} · 可多选</text><text class="card-title">{{ editorTitle }}</text></view><button class="close-sheet" aria-label="关闭其他选项" @click="editor = ''">×</button></view>
      <view class="option-grid"><button v-for="item in editor === 'cuisines' ? cuisineOptions : extraOptions" :key="item" :class="{ selected: draft.includes(item) }" :aria-pressed="draft.includes(item)" @click="toggle(draft, item)">{{ item }}</button></view>
      <view class="custom-row"><input v-model="custom" class="custom-input" :placeholder="editor === 'goals' ? '补充饮食目标' : editor === 'cuisines' ? '补充菜系偏好' : '补充口味偏好'" /><button @click="addCustom()">添加</button></view>
      <view class="sheet-actions"><button @click="editor = ''">取消</button><button class="selected" @click="saveExtras">保存</button></view>
    </view>
  </view>
</template>
<style scoped>
.health-card{padding:0;margin-bottom:20rpx;color:#25272d}.card-title{display:block;font-size:30rpx;font-weight:600;line-height:1.5}.card-heading{display:flex;align-items:center;justify-content:space-between;gap:12rpx;margin-bottom:14rpx}.multiple-hint{font-size:24rpx;color:#8790a2}.health-options{margin-top:12rpx;display:flex;flex-direction:column;gap:8rpx}.health-option{display:flex;align-items:center;gap:22rpx;width:100%;min-height:44px;padding:12rpx 24rpx;border:1rpx solid #e9ecf2;border-radius:16rpx;text-align:left;font-size:29rpx}.health-option.chosen{background:#f5f6f8;border-color:#f5f6f8}.radio-mark{width:32rpx;height:32rpx;flex-shrink:0;border:2rpx solid #b9c2d3;border-radius:50%;display:flex;align-items:center;justify-content:center}.chosen .radio-mark{background:#0879f9;border-color:#0879f9}.radio-mark view{width:12rpx;height:12rpx;border-radius:50%;background:#fff}
.option-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12rpx}.option-grid button{display:flex;align-items:center;justify-content:center;min-width:0;min-height:44px;padding:10rpx 8rpx;border:1rpx solid #e6eaf1;border-radius:16rpx;font-size:28rpx;line-height:1.4;color:#4b556b;overflow-wrap:anywhere}.option-grid .selected{border-color:#589aff;background:#f0f6ff;color:#0674ed}.other-row{display:flex;align-items:center;justify-content:space-between;width:100%;min-height:44px;padding:12rpx 4rpx;border-bottom:1rpx solid #edf0f5;text-align:left;color:#7c879e;font-size:27rpx;margin-top:4rpx}.other-row>view{min-width:0}.chevron{font-size:34rpx;color:#8592ac;flex-shrink:0}.extra-summary{display:block;color:#7e8798;font-size:25rpx;line-height:1.6;overflow-wrap:anywhere}.taste-summary{margin-top:12rpx}.cuisine-summary{display:flex;align-items:center;justify-content:space-between;gap:20rpx;width:100%;min-height:46px;padding:14rpx 22rpx;border:1rpx solid #e6eaf1;border-radius:18rpx;text-align:left;font-size:28rpx;color:#4b556b}.cuisine-label{flex-shrink:0;color:#343944}.optional-label{font-size:23rpx;color:#8790a2;margin-left:10rpx}.cuisine-value{flex:1;min-width:0;overflow-wrap:anywhere;text-align:right}.cuisine-placeholder{color:#8b94a6}.support-copy{display:block;font-size:24rpx;line-height:1.6;color:#858da0;margin-top:14rpx}.condition-area{margin-top:18rpx}.field-label{display:block;margin-bottom:12rpx;font-size:26rpx;color:#6f7a90}.custom-input{min-width:0;height:44px;padding:0 20rpx;background:#f7f8fa;border:1rpx solid #e9ecf2;border-radius:16rpx;font-size:28rpx;margin-top:14rpx}.condition-grid button{font-size:26rpx}
.extras-sheet{max-height:80vh;overflow-y:auto;border-radius:32rpx 32rpx 0 0}.sheet-heading{display:flex;justify-content:space-between;align-items:center;gap:20rpx;margin-bottom:26rpx}.sheet-heading .card-title{font-size:34rpx;font-weight:500}.sheet-heading .support-copy{margin:0 0 6rpx}.close-sheet{width:44px;height:44px;font-size:38rpx;color:#31343b}.custom-row{display:grid;grid-template-columns:minmax(0,1fr) 80rpx;align-items:center;gap:16rpx}.custom-row button{min-height:44px;font-size:28rpx;color:#0674ed;margin-top:14rpx}.sheet-actions{display:grid;grid-template-columns:1fr 1fr;gap:20rpx;margin-top:28rpx}.sheet-actions button{min-height:48px;border:1rpx solid #dfe4ee;border-radius:999rpx;font-size:30rpx}.sheet-actions .selected{background:#25262a;border-color:#25262a;color:#fff}

</style>
