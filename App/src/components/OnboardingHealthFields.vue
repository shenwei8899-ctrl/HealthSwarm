<script setup>
import { computed, ref } from 'vue'
import { diseaseOptions, preferenceGroups } from '../utils/health.js'

const props = defineProps({ member: { type: Object, required: true } })
const coreGoals = ['控糖', '控压', '控脂', '减脂', '增肌', '饮食均衡']
const coreTastes = ['清淡', '少油', '少盐', '不吃辣', '无特别要求']
const healthStates = [
  { value: 'unknown', label: '暂不填写' },
  { value: 'none', label: '没有已知基础病' },
  { value: 'set', label: '有基础病' },
]
const editor = ref(''), draft = ref([]), draftCuisines = ref([]), custom = ref(''), customCuisine = ref('')
const extraGoals = computed(() => props.member.goals.filter(value => !coreGoals.includes(value)))
const extraTastes = computed(() => props.member.tastePreferences.filter(value => !coreTastes.includes(value)))
const editorTitle = computed(() => editor.value === 'goals' ? '其他饮食目标' : '其他口味与菜系')
const extraOptions = computed(() => {
  const field = editor.value === 'goals' ? 'goals' : 'tastePreferences'
  const core = editor.value === 'goals' ? coreGoals : coreTastes
  return [...new Set([...preferenceGroups[field].items.filter(value => !core.includes(value) && !['其他', '自定义'].includes(value)), ...draft.value])]
})
const cuisineOptions = computed(() => [...new Set([...preferenceGroups.cuisines.items.filter(value => value !== '自定义'), ...draftCuisines.value])])

function toggle(list, value) {
  const index = list.indexOf(value)
  index < 0 ? list.push(value) : list.splice(index, 1)
}
function setHealth(value) {
  props.member.healthStatus = value
  props.member.health = value === 'none' ? '一般成人' : value === 'unknown' ? '未填写' : '用户自述'
}
function openExtras(field) {
  editor.value = field
  draft.value = [...(field === 'goals' ? extraGoals.value : extraTastes.value)]
  draftCuisines.value = [...props.member.cuisines]
  custom.value = ''; customCuisine.value = ''
}
function addCustom(cuisine = false) {
  const input = cuisine ? customCuisine : custom
  const value = input.value.trim()
  if (!value) return
  const list = cuisine ? draftCuisines.value : draft.value
  if (!list.includes(value)) list.push(value)
  input.value = ''
}
function saveExtras() {
  addCustom()
  const field = editor.value === 'goals' ? 'goals' : 'tastePreferences'
  const core = editor.value === 'goals' ? coreGoals : coreTastes
  props.member[field] = [...new Set([...props.member[field].filter(value => core.includes(value)), ...draft.value])]
  if (editor.value === 'tastePreferences') {
    addCustom(true)
    props.member.cuisines = [...draftCuisines.value]
  }
  editor.value = ''
}
</script>

<template>
  <view class="health-card">
    <text class="card-title">基础健康</text>
    <text class="health-question">是否有已知基础病？</text>
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
    <text class="support-copy">根据你的填写提供建议，可随时修改。</text>
    <text v-if="member.healthStatus === 'set'" class="support-copy self-report">基础病信息为用户自述，不是平台确诊。</text>
  </view>

  <view class="health-card">
    <view class="card-heading"><text class="card-title">饮食目标</text><text class="multiple-hint">可多选</text></view>
    <view class="option-grid"><button v-for="item in coreGoals" :key="item" :class="{ selected: member.goals.includes(item) }" :aria-pressed="member.goals.includes(item)" @click="toggle(member.goals, item)">{{ item }}</button></view>
    <button class="other-row" @click="openExtras('goals')"><view><text>其他目标</text><text v-if="extraGoals.length" class="extra-summary">{{ extraGoals.join('、') }}</text></view><text class="chevron">›</text></button>
  </view>

  <view class="health-card">
    <view class="card-heading"><text class="card-title">口味偏好</text><text class="multiple-hint">可多选</text></view>
    <view class="option-grid"><button v-for="item in coreTastes" :key="item" :class="{ selected: member.tastePreferences.includes(item) }" :aria-pressed="member.tastePreferences.includes(item)" @click="toggle(member.tastePreferences, item)">{{ item }}</button><button :class="{ selected: extraTastes.length || member.cuisines.length }" @click="openExtras('tastePreferences')">其他</button></view>
    <text v-if="extraTastes.length || member.cuisines.length" class="extra-summary taste-summary">{{ [...extraTastes, ...member.cuisines].join('、') }}</text>
  </view>

  <view v-if="editor" class="sheet-mask" @click.self="editor = ''">
    <view class="sheet extras-sheet">
      <view class="sheet-heading"><view><text class="support-copy">{{ member.name }} · 可多选</text><text class="card-title">{{ editorTitle }}</text></view><button class="close-sheet" aria-label="关闭其他选项" @click="editor = ''">×</button></view>
      <view class="option-grid"><button v-for="item in extraOptions" :key="item" :class="{ selected: draft.includes(item) }" :aria-pressed="draft.includes(item)" @click="toggle(draft, item)">{{ item }}</button></view>
      <view class="custom-row"><input v-model="custom" class="custom-input" :placeholder="editor === 'goals' ? '补充饮食目标' : '补充口味偏好'" /><button @click="addCustom()">添加</button></view>
      <template v-if="editor === 'tastePreferences'">
        <text class="field-label cuisine-label">菜系偏好，可稍后补充</text>
        <view class="option-grid"><button v-for="item in cuisineOptions" :key="item" :class="{ selected: draftCuisines.includes(item) }" :aria-pressed="draftCuisines.includes(item)" @click="toggle(draftCuisines, item)">{{ item }}</button></view>
        <view class="custom-row"><input v-model="customCuisine" class="custom-input" placeholder="补充菜系偏好" /><button @click="addCustom(true)">添加</button></view>
      </template>
      <view class="sheet-actions"><button @click="editor = ''">取消</button><button class="selected" @click="saveExtras">保存</button></view>
    </view>
  </view>
</template>

<style scoped>
.health-card{padding:24rpx;background:#fff;border:1rpx solid #e7e7ed;border-radius:24rpx;margin-bottom:20rpx;color:#1d1d1f}
.card-title{display:block;font-size:34rpx;line-height:1.35;font-weight:600}.card-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:20rpx}.multiple-hint,.support-copy{font-size:24rpx;color:#92929c}.health-question{display:block;font-size:28rpx;margin:18rpx 0 20rpx}.health-options{display:flex;flex-direction:column;gap:10rpx}.health-option{display:flex;align-items:center;gap:28rpx;width:100%;min-height:64rpx;padding:12rpx 26rpx;border:1rpx solid #e3e3e9;border-radius:14rpx;font-size:27rpx;line-height:1.4;text-align:left}.health-option.chosen{background:#f5f5f7;border-color:#f5f5f7}.radio-mark{width:32rpx;height:32rpx;flex-shrink:0;border:2rpx solid #9a9a9c;border-radius:50%;display:flex;align-items:center;justify-content:center}.chosen .radio-mark{border-color:#1d1d1f}.radio-mark view{width:22rpx;height:22rpx;border-radius:50%;background:#1d1d1f}.support-copy{display:block;line-height:1.6;margin-top:20rpx}.self-report{font-size:22rpx;margin-top:6rpx}.option-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14rpx}.option-grid button{display:flex;justify-content:center;align-items:center;min-width:0;min-height:62rpx;padding:10rpx 6rpx;border:1rpx solid #dedee5;border-radius:14rpx;font-size:26rpx;line-height:1.4;overflow-wrap:anywhere;color:#1d1d1f}.option-grid .selected,.sheet-actions .selected{background:#1d1d1f;border-color:#1d1d1f;color:#fff}.other-row{display:flex;align-items:center;justify-content:space-between;width:100%;border:1rpx solid #e3e3e9;border-radius:14rpx;padding:16rpx 24rpx;margin-top:18rpx;text-align:left;font-size:27rpx}.other-row>view{min-width:0}.chevron{font-size:36rpx;line-height:1;color:#8e8e93;margin-left:16rpx}.extra-summary{display:block;font-size:22rpx;line-height:1.6;color:#86868f;overflow-wrap:anywhere}.taste-summary{margin-top:16rpx}.condition-area{margin-top:22rpx}.field-label{display:block;font-size:25rpx;margin-bottom:14rpx}.condition-grid button{font-size:23rpx}.custom-input{height:76rpx;padding:0 20rpx;background:#f5f5f7;border:1rpx solid #e3e3e9;border-radius:14rpx;font-size:26rpx;min-width:0;margin-top:16rpx}.extras-sheet{max-height:80vh;overflow-y:auto;color:#1d1d1f}.sheet-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:24rpx}.sheet-heading .support-copy{margin:0 0 8rpx}.close-sheet{font-size:40rpx;width:64rpx;height:64rpx}.custom-row{display:grid;grid-template-columns:minmax(0,1fr) 70rpx;gap:14rpx;align-items:center}.custom-row button{font-size:25rpx;margin-top:16rpx}.cuisine-label{margin-top:28rpx}.sheet-actions{display:grid;grid-template-columns:1fr 1fr;gap:16rpx;margin-top:28rpx}.sheet-actions button{border:1rpx solid #dedee5;border-radius:16rpx;padding:18rpx;font-size:28rpx}
</style>
