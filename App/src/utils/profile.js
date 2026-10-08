import { getActiveHealthCase, updateActiveHealthCaseProfile } from './health-cases.js'
import { clearMealSwaps } from './meal-customization.js'

export const DEMO_MEMBERS = [
  { id: 1, name: '我', age: 28, birthDate: '1998-05-18', gender: '女', relation: '本人', height: 165, weight: 58, health: '一般成人', healthStatus: 'none', doctorStatus: 'none', conditions: [], focus: '规律三餐', flavors: ['清淡'], goals: ['健脾养胃'], cuisines: ['家常菜'], tastePreferences: ['少油少盐'], allergyStatus: 'none', allergies: [], avoidanceStatus: 'none', avoidances: [], reportStatus: 'empty', color: '#f6c96b', clinicianGuidance: '', hypoglycemiaRisk: '未填写', kidneyCondition: '未填写', recentNote: '' },
  { id: 2, name: '家人 A', age: 52, birthDate: '1974-02-08', gender: '女', relation: '家人', height: 160, weight: 56, health: '一般成人', healthStatus: 'none', doctorStatus: 'none', conditions: [], focus: '清淡少盐', flavors: ['葱香'], goals: ['控压'], cuisines: ['家常菜'], tastePreferences: ['清淡'], allergyStatus: 'unknown', allergies: [], avoidanceStatus: 'unknown', avoidances: [], reportStatus: 'empty', color: '#ef927e', clinicianGuidance: '', hypoglycemiaRisk: '未填写', kidneyCondition: '未填写', recentNote: '' },
  { id: 3, name: '家人 B', age: 55, birthDate: '1971-11-26', gender: '男', relation: '家人', height: 172, weight: 70, health: '一般成人', healthStatus: 'none', doctorStatus: 'none', conditions: [], focus: '多吃蔬菜', flavors: ['咸鲜'], goals: ['补蛋白'], cuisines: ['快手菜'], tastePreferences: ['无要求'], allergyStatus: 'none', allergies: [], avoidanceStatus: 'none', avoidances: [], reportStatus: 'empty', color: '#8dc5a5', clinicianGuidance: '', hypoglycemiaRisk: '未填写', kidneyCondition: '未填写', recentNote: '' },
]

export function newMember(index) {
  return { id: Date.now() + index, name: `成员 ${index + 1}`, age: 30, birthDate: '', gender: '未填写', relation: '家人', height: '', weight: '', health: '未填写', healthStatus: 'unknown', doctorStatus: 'unknown', conditions: [], focus: '均衡饮食', flavors: [], goals: [], cuisines: [], tastePreferences: [], allergyStatus: 'unknown', allergies: [], avoidanceStatus: 'unknown', avoidances: [], reportStatus: 'empty', color: '#a9c8dd', clinicianGuidance: '', hypoglycemiaRisk: '未填写', kidneyCondition: '未填写', recentNote: '' }
}

export function normalizeMember(member) {
  const legacyDisease=member.healthStatus===undefined?['糖尿病','高血压','高血脂','肾脏疾病'].find(c=>(member.health||'').includes(c)):null
  return {
    birthDate: '', gender: '未填写', relation: '家人', clinicianGuidance: '', hypoglycemiaRisk: '未填写', kidneyCondition: '未填写', recentNote: '',
    healthStatus: 'unknown', doctorStatus: 'unknown', conditions: [], flavors: [], goals: [], cuisines: [], tastePreferences: [],
    allergyStatus: 'unknown', allergies: [], intoleranceStatus: 'unknown', intolerances: [], otherCondition: '', avoidanceStatus: 'unknown', avoidances: [], reportStatus: 'empty',
    ...member,
    ...(member.relation==='本人'&&!member.claimedBy?{claimedBy:'creator'}:{}),
    ...(legacyDisease?{healthStatus:'set',conditions:[legacyDisease]}:{}),
    health: member.health || '未填写',
  }
}

export function normalizeProfile(profile) {
  const members = (profile.members || []).map(normalizeMember)
  return {
    householdName: '我的家', usageMode: '家庭使用', sharedDinerCount: members.length || 1, goals: ['吃得均衡'], tastes: ['家常'], allergies: ['无已知过敏'], memories: [],
    ...profile,
    members,
    defaultDiners: (profile.defaultDiners || members.map(member => member.id)).filter(id => members.some(member => member.id === id)),
  }
}

export function getProfile() {
  const activeCase = getActiveHealthCase()
  if (activeCase?.profile) return normalizeProfile(activeCase.profile)
  const stored = uni.getStorageSync('family-profile-v2')
  return normalizeProfile(stored || {
    householdName: '我的家', usageMode: '家庭使用', sharedDinerCount: 3, goals: ['吃得均衡'], tastes: ['家常'], allergies: ['无已知过敏'], memories: [],
    members: JSON.parse(JSON.stringify(DEMO_MEMBERS)),
  })
}

export function saveProfile(profile) {
  const normalized = normalizeProfile(profile)
  normalized.revision = Date.now()
  if (getActiveHealthCase()) updateActiveHealthCaseProfile(normalized)
  else uni.setStorageSync('family-profile-v2', JSON.parse(JSON.stringify(normalized)))
}
export function getRecords() { return uni.getStorageSync(getActiveHealthCase() ? 'meal-records-health-case-v1' : 'meal-records-v1') || [] }
export function saveRecord(record) {
  const records = getRecords()
  if (!records.some(item => item.id === record.id)) records.push(record)
  uni.setStorageSync(getActiveHealthCase() ? 'meal-records-health-case-v1' : 'meal-records-v1', records)
}
export function updateRecord(id,patch){const records=getRecords().map(r=>r.id===id?{...r,...patch}:r);uni.setStorageSync(getActiveHealthCase()?'meal-records-health-case-v1':'meal-records-v1',records)}
export function resetProfileData() {
  uni.setStorageSync('family-profile-v2', null)
  uni.setStorageSync('meal-records-v1', [])
  uni.setStorageSync('meal-records-health-case-v1', [])
  uni.setStorageSync('active-health-case-v1', null)
  clearMealSwaps()
  uni.setStorageSync('meal-session-v3', {})
  uni.setStorageSync('family-invites-v1', {})
}
export function backHome() {
  if (getCurrentPages().length > 1) uni.navigateBack()
  else uni.reLaunch({ url: '/pages/chat/index' })
}
