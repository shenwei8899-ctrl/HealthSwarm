<script setup>
import AppNavBar from '../../components/AppNavBar.vue'
import { computed, ref } from 'vue'
import { onLoad, onBackPress } from '@dcloudio/uni-app'
import FlowRibbon from '../../components/FlowRibbon.vue'
import { getProfile, saveRecord, backHome } from '../../utils/profile.js'
import { photoEstimate } from '../../utils/demo.js'
import { DIABETES_CASE_ID, getActiveHealthCaseId } from '../../utils/health-cases.js'
import { todayPlan,mealProfile } from '../../utils/meal-state.js'
import { ingredientConflicts,memberNotes } from '../../utils/health.js'
import { mealFromRoute } from '../../utils/meal-flow.js'
import { portionOptions, oilOptions, createPortionDraft, confirmPortionDraft, intakeSummary } from '../../utils/scan-portions.js'
const profile = getProfile()
const memberId = ref(profile.members[0].id)
const memberIds = ref(profile.defaultDiners?.length ? [...profile.defaultDiners] : [profile.members[0].id])
const captureScope = ref('单人餐盘')
const sourceMode = ref('拍照分析')
const caseId = ref('')
const isDiabetesCase = computed(() => caseId.value === DIABETES_CASE_ID)
const meal = ref('晚餐')
const imagePath = ref('')
const status = ref('idle')
const portion = ref('不确定')
const grams = ref(null)
const personalDishes = ref(['杂粮饭','西兰花','香煎鸡腿'])
const personalNoneConfirmed = ref(false)
const oil = ref('不确定')
const recognizedDishes = ref(['杂粮饭','西兰花','香煎鸡腿'])
const familyIntake = ref(Object.fromEntries(profile.members.map(member => [member.id, { dishes: [], portion: '不确定', grams: null, noneConfirmed: false }])))
const portionsConfirmed = ref(false)
const portionDialogOpen = ref(false)
const portionDraft = ref({ oil: '不确定', people: [] })
const portionError = ref('')
const riskExpanded = ref(false)
const recordId = Date.now().toString()
const saving = ref(false)
const saved = ref(false)
function estimateIntake(person, oilChoice) {
  if (!person || person.portion === '不确定' || !person.dishes.length) return null
  const legacyPortion = { '少量': '半份', '一般': '八成', '较多': '全部' }[person.portion]
  const base = photoEstimate(legacyPortion, oilChoice)
  const factor = person.dishes.length / 3
  return Object.fromEntries(Object.entries(base).map(([key, value]) => [key, Math.round(value * factor)]))
}
const estimate = computed(() => estimateIntake({ portion: portion.value, dishes: personalDishes.value }, oil.value))
const draftEstimate = computed(() => captureScope.value === '单人餐盘' ? estimateIntake(portionDraft.value.people[0], portionDraft.value.oil) : null)
const risk=computed(()=>ingredientConflicts(selectedMembers.value,recognizedDishes.value))
const cautions=computed(()=>selectedMembers.value.map(m=>({name:m.name,notes:memberNotes(m)})))
const member = computed(() => profile.members.find(m => m.id === memberId.value))
const selectedMembers = computed(() => captureScope.value === '单人餐盘' ? [member.value] : profile.members.filter(m => memberIds.value.includes(m.id)))
const memberIntake = computed(() => selectedMembers.value.map(item => ({
  memberId: item.id,
  memberName: item.name,
  dishes: [...(familyIntake.value[item.id]?.dishes || [])],
  portion: familyIntake.value[item.id]?.portion || '不确定',
  grams: familyIntake.value[item.id]?.grams ?? null,
  noneConfirmed: Boolean(familyIntake.value[item.id]?.noneConfirmed),
})))
const confirmedIntake = computed(() => captureScope.value === '家庭共享桌菜' ? memberIntake.value : [{
  memberId: member.value.id, memberName: member.value.name, dishes: [...personalDishes.value],
  portion: portion.value, grams: grams.value, noneConfirmed: personalNoneConfirmed.value,
}])
const emptyEstimate = { kcal: null, low: null, high: null, protein: null, carbs: null, fat: null, sugars: null }
onLoad(options => {
  meal.value = mealFromRoute(options.meal)
  const ids=(options.members?options.members.split(',').map(Number):mealProfile(profile,meal.value).defaultDiners).filter(id=>profile.members.some(m=>m.id===id))
  if(ids.length){memberIds.value=ids;memberId.value=ids[0];if(ids.length>1)captureScope.value='家庭共享桌菜'}
  caseId.value = options.case === 'diabetes' || getActiveHealthCaseId() === DIABETES_CASE_ID ? DIABETES_CASE_ID : ''
  if (caseId.value === DIABETES_CASE_ID) {
    const father = profile.members.find(item => item.name === '爸爸')
    if (father) memberId.value = father.id
  }
})
onBackPress(() => {
  if (!portionDialogOpen.value) return false
  closePortions()
  return true
})
function chooseImage(source) {
  uni.chooseImage({ count: 1, sourceType: [source],
    success(res) {
      imagePath.value = res.tempFilePaths[0]
      sourceMode.value = '拍照分析'
      portionsConfirmed.value = false
      analyze()
    },
    fail() { uni.showToast({ title: '未选择图片，可从相册选择或体验演示', icon: 'none' }) },
  })
}
function analyze() {
  if (status.value === 'analyzing') return
  status.value = 'analyzing'
  setTimeout(() => { status.value = 'result' }, 600)
}
function select(field) {
  const choices = field === 'meal' ? ['早餐','午餐','晚餐','加餐'] : profile.members.map(m => m.name)
  uni.showActionSheet({ itemList: choices, success({ tapIndex }) {
    if (field === 'meal') meal.value = choices[tapIndex]
    else {
      memberId.value = profile.members[tapIndex].id
      portion.value = '不确定'
      grams.value = null
      personalDishes.value = [...recognizedDishes.value]
      personalNoneConfirmed.value = false
      portionsConfirmed.value = false
    }
  } })
}
function toggleMember(id) {
  const i = memberIds.value.indexOf(id)
  if (i >= 0) { if (memberIds.value.length === 1) return; memberIds.value.splice(i, 1) }
  else memberIds.value.push(id)
  portionsConfirmed.value = false
}
function openPortions() {
  portionDraft.value = createPortionDraft(confirmedIntake.value, recognizedDishes.value, oil.value)
  portionError.value = ''
  portionDialogOpen.value = true
}
function closePortions() { portionDialogOpen.value = false; portionError.value = '' }
function goBack() { if (portionDialogOpen.value) closePortions(); else backHome() }
function toggleDraftDish(person, dish) {
  person.dishes = person.dishes.includes(dish) ? person.dishes.filter(item => item !== dish) : [...person.dishes, dish]
  person.noneConfirmed = false
  portionError.value = ''
}
function markNotEaten(person) {
  person.dishes = []
  person.noneConfirmed = true
  person.grams = ''
  person.portion = '不确定'
  portionError.value = ''
}
function applyPortions() {
  try {
    const confirmed = confirmPortionDraft(portionDraft.value, recognizedDishes.value)
    oil.value = confirmed.oil
    if (captureScope.value === '家庭共享桌菜') {
      confirmed.people.forEach(person => { familyIntake.value[person.memberId] = person })
    } else {
      const person = confirmed.people[0]
      personalDishes.value = person.dishes
      portion.value = person.portion
      grams.value = person.grams
      personalNoneConfirmed.value = person.noneConfirmed
    }
    portionsConfirmed.value = true
    closePortions()
  } catch (error) { portionError.value = error.message }
}
function confirmRecord(destination) {
  if (saving.value) return
  if (!saved.value && !portionsConfirmed.value) { openPortions(); return }
  saving.value = true
  if(!saved.value){
    const isFamilyTable=captureScope.value==='家庭共享桌菜'
    saveRecord({
      id:recordId,version:1,source:sourceMode.value,captureScope:captureScope.value,caseId:caseId.value||undefined,
      memberId:memberId.value,memberIds:selectedMembers.value.map(m=>m.id),memberName:member.value.name,memberNames:selectedMembers.value.map(m=>m.name),
      meal:meal.value,portion:isFamilyTable?'逐人确认':portion.value,grams:isFamilyTable?null:grams.value,oil:oil.value,
      dishes:isFamilyTable?[...recognizedDishes.value]:[...personalDishes.value],
      memberIntake:confirmedIntake.value,
      photo:Boolean(imagePath.value),photoPath:imagePath.value||null,...(isFamilyTable?emptyEstimate:(estimate.value||emptyEstimate)),
      createdAt:new Date().toISOString(),isDemo:true,
    })
    saved.value=true
  }
  const url=destination==='chat'?'/pages/chat/index?recordId='+recordId+(isDiabetesCase.value?'&caseFeedback=diabetes':''):'/pages/records/index'
  uni.redirectTo({url,fail:()=>{saving.value=false;uni.showToast({title:'记录已保存，打开失败可重试',icon:'none'})}})
}
function correction(){uni.showModal({title:'纠正识别结果（演示）',editable:true,placeholderText:'用顿号分隔菜名',content:recognizedDishes.value.join('、'),confirmText:'确认事实修正',success:r=>{if(!r.confirm||!r.content?.trim())return;recognizedDishes.value=[...new Set(r.content.split(/[、，,]/).map(t=>t.trim()).filter(Boolean))];personalDishes.value=personalDishes.value.filter(d=>recognizedDishes.value.includes(d));Object.keys(familyIntake.value).forEach(id=>familyIntake.value[id].dishes=familyIntake.value[id].dishes.filter(d=>recognizedDishes.value.includes(d)));portionsConfirmed.value=false;uni.showToast({title:'示例菜品已更新，请核对份量',icon:'none'})}})}
function fromMenu(){const p=todayPlan(profile,meal.value);recognizedDishes.value=p.dishes.map(d=>d.name);personalDishes.value=[...recognizedDishes.value];sourceMode.value='当天食谱选菜';imagePath.value='';Object.keys(familyIntake.value).forEach(id=>familyIntake.value[id]={dishes:[],portion:'不确定',grams:null,noneConfirmed:false});portionsConfirmed.value=false;analyze()}
function manualEntry() {
  uni.showModal({ title: '手动填写菜品', editable: true, placeholderText: '例如：杂粮饭、西兰花', success: result => {
    if (!result.confirm || !result.content?.trim()) return
    recognizedDishes.value = [...new Set(result.content.split(/[、，,]/).map(dish => dish.trim()).filter(Boolean))]
    personalDishes.value = [...recognizedDishes.value]
    sourceMode.value = '手动填写'
    imagePath.value = ''
    portionsConfirmed.value = false
    Object.keys(familyIntake.value).forEach(id => { familyIntake.value[id] = { dishes: [], portion: '不确定', grams: null, noneConfirmed: false } })
    analyze()
  } })
}
function editDiners() {
  if (captureScope.value === '单人餐盘') { select('member'); return }
  uni.showActionSheet({ itemList: profile.members.map(m => `${memberIds.value.includes(m.id) ? '已选 · ' : '加入 · '}${m.name}`), success: ({ tapIndex }) => toggleMember(profile.members[tapIndex].id) })
}
function help() {
  uni.showModal({ title: '为什么展示估算区间？', content: '真实识别也无法仅凭照片确定重量和隐形油盐。本页用同一虚拟餐盘演示流程，上传图片只在本机预览，不会送往 AI。', showCancel: false })
}
</script>
<template>
  <view class="screen scan-screen">
    <AppNavBar><view class="nav-row"><button class="icon-button" @click="goBack">‹</button><text class="nav-title">拍照记一餐</text><button class="icon-button" aria-label="估算说明" @click="help">?</button></view></AppNavBar>
    <FlowRibbon :current="6" class="scan-flow" />

    <view class="scan-status" :class="{ processing: status === 'analyzing' }">
      <view class="status-dot"></view>
      <text>{{ status === 'idle' ? '拍照或从相册选择，开始记录这一餐' : status === 'analyzing' ? '正在展示分析流程…' : sourceMode === '拍照分析' ? '演示菜品已展示 · 非真实照片识别' : sourceMode + ' · 请确认实际份量' }}</text>
    </view>
    <view class="photo-preview">
      <image v-if="imagePath" :src="imagePath" mode="aspectFill" />
      <view v-else class="photo-placeholder">
        <view v-if="status !== 'idle'" class="demo-plate"><text>🍚</text><text>🥦</text><text>🍗</text></view>
        <template v-else><text class="photo-symbol">＋</text><text class="photo-title">拍下这一餐</text><text class="small">照片会保留在这里，方便核对菜品</text></template>
      </view>
      <view v-if="status === 'analyzing'" class="scan-line"></view>
      <view v-if="imagePath" class="confidence">本机原图预览 · AI 识别待接入</view>
      <view v-else-if="status !== 'idle'" class="confidence">示例餐盘示意 · 非真实识别</view>
    </view>
    <view class="photo-actions">
      <button class="primary-button" :disabled="status === 'analyzing' || saving" @click="chooseImage('camera')">{{ imagePath ? '重新拍照' : '拍照' }}</button>
      <button class="secondary-button" :disabled="status === 'analyzing' || saving" @click="chooseImage('album')">从相册选择</button>
    </view>

    <view v-if="status === 'idle'" class="idle-state">
      <view class="capture-setup card">
        <text class="field-title">记录哪一餐</text>
        <view class="scope-grid"><button v-for="scope in ['单人餐盘','家庭共享桌菜']" :key="scope" :class="{active:captureScope===scope}" @click="captureScope=scope;portionsConfirmed=false">{{scope}}</button></view>
        <button v-if="captureScope==='单人餐盘'" class="setup-row" @click="select('member')"><text>就餐成员</text><text>{{member.name}} ›</text></button>
        <view v-else class="member-picks"><button v-for="m in profile.members" :key="m.id" :class="{active:memberIds.includes(m.id)}" @click="toggleMember(m.id)">{{m.name}} · {{memberIds.includes(m.id)?'已选':'加入'}}</button></view>
        <button class="setup-row" @click="select('meal')"><text>餐次</text><text>{{meal}} ›</text></button>
      </view>
      <button class="demo-entry" @click="analyze">体验示例餐盘分析 ›</button>
      <view class="other-methods"><button @click="fromMenu">从今日食谱选菜</button><button @click="manualEntry">手动填写</button></view>
      <text class="demo-label">AI 识别待接入。选图仅用于本机预览，演示结果不对应上传照片。</text>
    </view>

    <view v-else-if="status === 'analyzing'" class="analyzing-card card"><text class="section-title">先看菜品，再确认份量</text><text>正在展示示例流程，请稍候</text></view>

    <view v-else class="result-state">
      <view class="foods-card card">
        <view class="foods-heading"><view><text class="field-title">{{ sourceMode==='拍照分析'?'识别出的菜品':'本餐菜品' }}</text><text class="small">{{ meal }} · {{ captureScope }}</text></view><button class="adjust-button" @click="openPortions">调整份量</button></view>
        <view v-for="dish in recognizedDishes" :key="dish" class="food-row"><view class="food-dot"></view><text>{{dish}}</text><text class="small">{{ sourceMode==='拍照分析'?'示例菜品':'待核对份量' }}</text></view>
      </view>

      <view class="nutrition-card card">
        <view class="nutrition-heading"><text class="field-title">{{ captureScope==='家庭共享桌菜'?'家庭记餐':'本餐营养估算' }}</text><text class="status-chip">{{portionsConfirmed?'已确认份量':'份量待确认'}}</text></view>
        <template v-if="captureScope==='单人餐盘' && estimate">
          <view class="calorie-line"><text class="calorie-value">约 {{estimate.kcal}}</text><text>kcal</text></view>
          <text class="nutrition-range">估算范围 {{estimate.low}}–{{estimate.high}} kcal · 演示数值</text>
          <view class="macro-grid"><view><text>{{estimate.protein}} g</text><text class="small">蛋白质</text></view><view><text>{{estimate.carbs}} g</text><text class="small">碳水</text></view><view><text>{{estimate.fat}} g</text><text class="small">脂肪</text></view><view><text>{{estimate.sugars}} g</text><text class="small">糖类</text></view></view>
        </template>
        <text v-else class="nutrition-empty">{{captureScope==='家庭共享桌菜'?'分别确认每位成员吃过的菜和份量，不分摊整桌热量。':'份量不确定，暂不展示摄入估算。'}}</text>
        <view v-if="portionsConfirmed" class="intake-summary"><view v-for="person in confirmedIntake" :key="person.memberId"><text>{{person.memberName}}</text><text>{{intakeSummary(person)}}</text></view></view>
        <text class="estimate-note">照片无法确定重量和隐形油盐。营养数值仅演示流程，不能据此判断健康状况。</text>
      </view>

      <view class="confirm-card card">
        <button class="confirm-row" @click="editDiners"><text>就餐者</text><text>{{selectedMembers.map(m=>m.name).join('、')}} ›</text></button>
        <button class="confirm-row" @click="select('meal')"><text>餐次</text><text>{{meal}} ›</text></button>
        <view class="confirm-row"><text>烹饪用油</text><button class="inline-link" @click="openPortions">{{oil}} · 调整</button></view>
      </view>

      <view class="risk-card card">
        <view class="risk-heading"><text class="field-title">过敏与不耐受风险</text><button class="inline-link" @click="riskExpanded=!riskExpanded">{{riskExpanded?'收起说明':'展开说明'}} ›</button></view>
        <text :class="{ 'risk-warning': risk.length }">{{risk.length?risk.join('；')+' · 存在已知风险':'暂无法确认'}}</text>
        <text class="small">照片无法确认全部配料，不代表已验证安全。</text>
        <view v-if="riskExpanded" class="risk-details"><text>结合菜品、已知配料、用户补充与成员档案进行风险匹配；照片无法确定隐形调味和全部成分。</text><text>以上仅为饮食记录与演示建议，不输出医疗诊断。</text></view>
        <view v-for="m in cautions.filter(m=>m.notes.length)" :key="m.name" class="member-caution"><text>{{m.name}}的饮食注意事项</text><text v-for="note in m.notes" :key="note">{{note}}</text></view>
      </view>

      <button class="correction" @click="correction">{{sourceMode==='拍照分析'?'拍照认错？重新识别':'修改本餐菜品'}}</button>
      <view class="save-actions"><button class="secondary-button" :disabled="saving" @click="confirmRecord('records')">仅保存</button><button class="primary-button" :disabled="saving" @click="confirmRecord('chat')">保存并聊聊这一餐</button></view>
    </view>

    <view v-if="portionDialogOpen" class="portion-mask" @click="closePortions" @touchmove.stop.prevent>
      <view class="portion-dialog" role="dialog" aria-label="调整份量" @click.stop>
        <view class="dialog-header"><view><text class="section-title">调整份量</text><text class="small">{{meal}} · {{captureScope}}</text></view><button class="dialog-close" aria-label="关闭份量调整" @click="closePortions">×</button></view>
        <scroll-view class="dialog-body" scroll-y @touchmove.stop>
          <view v-for="person in portionDraft.people" :key="person.memberId" class="person-adjustment">
            <view class="person-heading"><text class="field-title">{{person.memberName}}吃了什么</text><button class="not-eaten" :class="{active:person.noneConfirmed}" @click="markNotEaten(person)">未吃这些菜</button></view>
            <view class="dish-picks"><button v-for="dish in recognizedDishes" :key="dish" :class="{active:person.dishes.includes(dish)}" @click="toggleDraftDish(person,dish)">{{dish}}</button></view>
            <template v-if="!person.noneConfirmed">
              <text class="adjust-label">大致吃了多少</text>
              <view class="portion-choices"><button v-for="choice in portionOptions" :key="choice" :class="{active:person.portion===choice}" @click="person.portion=choice">{{choice}}</button></view>
              <view class="grams-row"><view><text>实际克数（选填）</text><text class="small">仅填写你已知的食物总重量</text></view><input v-model="person.grams" type="digit" maxlength="8" placeholder="可留空" aria-label="实际克数" /><text>g</text></view>
            </template>
          </view>
          <view class="oil-adjustment"><text class="field-title">烹饪用油（选填）</text><view class="portion-choices"><button v-for="choice in oilOptions" :key="choice" :class="{active:portionDraft.oil===choice}" @click="portionDraft.oil=choice">{{choice}}</button></view></view>
          <view v-if="draftEstimate" class="draft-nutrition"><text class="field-title">调整后估算（演示）</text><text class="draft-calories">约 {{draftEstimate.kcal}} kcal</text><text class="small">{{draftEstimate.low}}–{{draftEstimate.high}} kcal</text><text class="small">蛋白质 {{draftEstimate.protein}} g · 碳水 {{draftEstimate.carbs}} g · 脂肪 {{draftEstimate.fat}} g</text></view>
          <text class="dialog-note">{{captureScope==='家庭共享桌菜'?'每位成员只记录本人确认吃过的菜和份量，不平均分配整桌热量。':'默认使用粗略份量，不要求称重或填写百分比。'}} 克数作为补充记录保存；演示估算仍依据粗略份量。</text>
        </scroll-view>
        <view class="dialog-footer"><text v-if="portionError" class="inline-error">{{portionError}}</text><view class="dialog-actions"><button class="secondary-button" @click="closePortions">取消</button><button class="primary-button" @click="applyPortions">确认份量</button></view></view>
      </view>
    </view>
  </view>
</template>
<style scoped>
.scan-flow{margin-top:20rpx}
.scan-status{display:flex;align-items:center;gap:12rpx;margin:24rpx 0 18rpx;padding:18rpx 22rpx;border:1rpx solid #ebebef;border-radius:20rpx;background:#fff;color:#63636b;font-size:23rpx;line-height:1.5}
.status-dot{width:12rpx;height:12rpx;flex-shrink:0;border-radius:50%;background:#246b50}
.processing .status-dot{animation:pulse 1s infinite alternate}
.photo-preview{position:relative;height:400rpx;overflow:hidden;border:1rpx solid #ebebef;border-radius:28rpx;background:#e9ecea}
.photo-preview image{width:100%;height:100%}
.photo-placeholder{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16rpx}
.photo-symbol{color:#246b50;font-size:76rpx;line-height:1}
.photo-title{font-size:30rpx;font-weight:600}
.photo-placeholder .small{font-size:23rpx;text-align:center}
.demo-plate{display:flex;align-items:center;justify-content:center;gap:18rpx;width:290rpx;height:210rpx;border:16rpx solid #fff;border-radius:50%;background:#f0f3f1;font-size:58rpx}
.confidence{position:absolute;left:20rpx;bottom:20rpx;max-width:calc(100% - 40rpx);padding:12rpx 18rpx;border-radius:16rpx;background:rgba(29,29,31,.78);color:#fff;font-size:21rpx}
.scan-line{position:absolute;left:6%;right:6%;top:20%;height:3rpx;background:#fff;box-shadow:0 0 20rpx #fff;animation:scan 1.2s infinite alternate}
@keyframes scan{to{top:78%}}@keyframes pulse{to{opacity:.3}}
.photo-actions{display:grid;grid-template-columns:1fr 1fr;gap:14rpx;margin-top:16rpx}
.photo-actions button{min-height:80rpx;font-size:26rpx}
.capture-setup{margin-top:24rpx;padding:24rpx}
.field-title{display:block;font-size:28rpx;font-weight:600;line-height:1.4}
.scope-grid{display:grid;grid-template-columns:1fr 1fr;gap:12rpx;margin-top:20rpx}
.scope-grid button,.member-picks button{min-height:64rpx;padding:14rpx;border:1rpx solid #dedee3;border-radius:16rpx;color:#63636b;font-size:23rpx}
.scope-grid button.active,.member-picks button.active{border-color:#246b50;background:#eaf2ed;color:#246b50;font-weight:600}
.setup-row{width:100%;display:flex;justify-content:space-between;gap:16rpx;padding:22rpx 0;border-bottom:1rpx solid #ebebef;font-size:25rpx}
.setup-row:last-child{border:0;padding-bottom:0}
.setup-row text:last-child{color:#246b50}
.member-picks{display:flex;flex-wrap:wrap;gap:10rpx;margin-top:20rpx}
.demo-entry{width:100%;margin-top:22rpx;padding:18rpx;color:#246b50;font-size:25rpx}
.other-methods{display:grid;grid-template-columns:1fr 1fr;gap:12rpx;margin-top:8rpx}
.other-methods button{padding:18rpx;border:1rpx solid #dedee3;border-radius:18rpx;background:#fff;font-size:23rpx;color:#63636b}
.analyzing-card{display:flex;flex-direction:column;gap:14rpx;margin-top:24rpx;padding:28rpx;font-size:25rpx;color:#63636b}
.result-state{display:flex;flex-direction:column;gap:20rpx;margin-top:24rpx}
.foods-card,.nutrition-card,.confirm-card,.risk-card{padding:26rpx}
.foods-heading,.nutrition-heading,.risk-heading{display:flex;align-items:center;justify-content:space-between;gap:16rpx}
.foods-heading>view{display:flex;flex-direction:column;gap:8rpx}
.foods-heading .small{font-size:22rpx}
.adjust-button{flex-shrink:0;min-height:68rpx;padding:16rpx 22rpx;border-radius:18rpx;background:#246b50;color:#fff;font-size:25rpx;font-weight:600}
.food-row{display:flex;align-items:center;gap:14rpx;min-height:88rpx;border-top:1rpx solid #ebebef;font-size:28rpx}
.food-row:first-of-type{margin-top:20rpx}
.food-row>text:first-of-type{flex:1;min-width:0}
.food-row .small{font-size:22rpx;flex-shrink:0}
.food-dot{width:10rpx;height:10rpx;border-radius:50%;background:#246b50;flex-shrink:0}
.nutrition-heading .status-chip{flex-shrink:0;font-size:21rpx}
.calorie-line{display:flex;align-items:baseline;gap:10rpx;margin-top:24rpx;color:#63636b;font-size:25rpx}
.calorie-value{color:#1d1d1f;font-size:52rpx;font-weight:600}
.nutrition-range{display:block;margin-top:10rpx;font-size:23rpx;color:#63636b}
.macro-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10rpx;margin-top:22rpx}
.macro-grid>view{display:flex;flex-direction:column;gap:8rpx;padding:16rpx 6rpx;border-radius:16rpx;background:#f5f5f7;text-align:center;font-size:25rpx;font-weight:600}
.macro-grid .small{font-size:21rpx;font-weight:400}
.nutrition-empty{display:block;margin-top:20rpx;font-size:25rpx;color:#63636b;line-height:1.65}
.intake-summary{display:flex;flex-direction:column;gap:14rpx;margin-top:20rpx}
.intake-summary>view{display:flex;justify-content:space-between;gap:20rpx;font-size:24rpx}
.intake-summary text:last-child{color:#63636b;text-align:right}
.estimate-note{display:block;margin-top:20rpx;font-size:22rpx;color:#767680;line-height:1.65}
.confirm-row{width:100%;display:flex;align-items:center;justify-content:space-between;gap:20rpx;min-height:80rpx;border-bottom:1rpx solid #ebebef;text-align:left;font-size:26rpx}
.confirm-row:last-child{border:0}
.confirm-row>text:last-child{max-width:65%;color:#63636b;text-align:right;font-size:24rpx}
.inline-link{flex-shrink:0;padding:10rpx 0;color:#246b50;font-size:23rpx}
.risk-card{display:flex;flex-direction:column;gap:14rpx;font-size:25rpx;line-height:1.65}
.risk-card .small,.risk-details{font-size:23rpx}
.risk-heading .field-title{font-size:27rpx}
.risk-warning{color:#c73632;font-weight:600}
.risk-details,.member-caution{display:flex;flex-direction:column;gap:12rpx;border-top:1rpx solid #ebebef;padding-top:16rpx}
.correction{width:100%;min-height:76rpx;border:1rpx solid #dedee3;border-radius:20rpx;background:#fff;color:#246b50;font-size:25rpx;font-weight:500}
.save-actions{display:grid;grid-template-columns:.8fr 1.4fr;gap:12rpx}
.save-actions button{min-width:0;padding:16rpx 10rpx;font-size:25rpx}
.portion-mask{position:fixed;inset:0;z-index:100;display:flex;align-items:center;justify-content:center;padding:32rpx;background:rgba(0,0,0,.4)}
.portion-dialog{width:100%;max-width:690rpx;max-height:86vh;display:flex;flex-direction:column;overflow:hidden;border-radius:32rpx;background:#fff}
.dialog-header{display:flex;align-items:center;justify-content:space-between;gap:16rpx;padding:26rpx 28rpx 22rpx;border-bottom:1rpx solid #ebebef}
.dialog-header>view{display:flex;flex-direction:column;gap:8rpx}
.dialog-header .section-title{font-size:32rpx}
.dialog-header .small{font-size:22rpx}
.dialog-close{width:64rpx;height:64rpx;flex-shrink:0;border-radius:50%;background:#f5f5f7;font-size:38rpx;color:#63636b}
.dialog-body{height:52vh;min-height:0}
.person-adjustment,.oil-adjustment{margin:0 26rpx;padding:24rpx 0;border-bottom:1rpx solid #ebebef}
.person-heading{display:flex;align-items:center;justify-content:space-between;gap:12rpx}
.person-heading .field-title{font-size:27rpx}
.not-eaten{flex-shrink:0;padding:10rpx 12rpx;border:1rpx solid #dedee3;border-radius:12rpx;color:#63636b;font-size:21rpx}
.not-eaten.active{border-color:#246b50;color:#246b50;background:#eaf2ed}
.dish-picks{display:flex;flex-wrap:wrap;gap:10rpx;margin-top:18rpx}
.dish-picks button{min-height:60rpx;padding:14rpx 18rpx;border:1rpx solid #dedee3;border-radius:16rpx;color:#63636b;font-size:23rpx}
.dish-picks button.active,.portion-choices button.active{border-color:#246b50;background:#eaf2ed;color:#246b50;font-weight:600}
.adjust-label{display:block;margin-top:22rpx;font-size:24rpx}
.portion-choices{display:grid;grid-template-columns:repeat(4,1fr);gap:8rpx;margin-top:14rpx}
.portion-choices button{min-height:62rpx;padding:14rpx 4rpx;border:1rpx solid #dedee3;border-radius:14rpx;color:#63636b;font-size:23rpx}
.grams-row{display:flex;align-items:center;gap:10rpx;margin-top:22rpx;font-size:24rpx}
.grams-row>view{display:flex;flex:1;min-width:0;flex-direction:column;gap:8rpx}
.grams-row .small{font-size:20rpx}
.grams-row input{width:132rpx;height:64rpx;padding:0 14rpx;border:1rpx solid #dedee3;border-radius:14rpx;background:#f5f5f7;font-size:24rpx;text-align:right}
.dialog-note{display:block;margin:22rpx 26rpx 26rpx;font-size:21rpx;color:#767680;line-height:1.65}
.draft-nutrition{display:flex;flex-direction:column;gap:10rpx;margin:22rpx 26rpx;padding:22rpx;border-radius:20rpx;background:#f5f5f7}.draft-calories{font-size:34rpx;font-weight:600}.draft-nutrition .small{font-size:22rpx;line-height:1.6}
.dialog-footer{flex-shrink:0;padding:20rpx 26rpx 26rpx;border-top:1rpx solid #ebebef}
.dialog-footer .inline-error{padding:0 0 16rpx;font-size:23rpx}
.dialog-actions{display:grid;grid-template-columns:1fr 1fr;gap:14rpx}
.dialog-actions button{min-height:80rpx;padding:16rpx 8rpx;font-size:26rpx}
</style>
