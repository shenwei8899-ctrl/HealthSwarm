import { createPlan } from './demo.js'

export const DIABETES_CASE_ID = 'diabetes-family-dinner'
export const DIABETES_CASE_QUESTION = '爸爸有糖尿病，我们三个人今晚吃什么？'

export function createDiabetesCaseProfile() {
  return {
    householdName: '糖尿病家庭案例（虚拟）',
    goals: ['吃得均衡', '稳血糖'],
    tastes: ['家常', '清淡'],
    allergies: ['无已知过敏'],
    defaultDiners: [101, 102, 103],
    members: [
      { id: 101, name: '我', age: 28, height: 165, weight: 58, health: '一般成人', focus: '规律三餐', color: '#f6c96b', clinicianGuidance: '', hypoglycemiaRisk: '未填写', kidneyCondition: '未填写', recentNote: '' },
      { id: 102, name: '妈妈', age: 55, height: 160, weight: 56, health: '一般成人', focus: '清淡少盐', color: '#ef927e', clinicianGuidance: '', hypoglycemiaRisk: '未填写', kidneyCondition: '未填写', recentNote: '' },
      { id: 103, name: '爸爸', age: 58, height: 172, weight: 70, health: '2型糖尿病（自报）', focus: '稳血糖', color: '#8dc5a5', clinicianGuidance: '', hypoglycemiaRisk: '不确定', kidneyCondition: '未填写', recentNote: '暂无医生饮食要求记录' },
    ],
  }
}

export function getActiveHealthCase() { return uni.getStorageSync('active-health-case-v1') || null }
export function getActiveHealthCaseId() { return getActiveHealthCase()?.id || '' }
export function updateActiveHealthCaseProfile(profile) {
  const active = getActiveHealthCase()
  if (active) uni.setStorageSync('active-health-case-v1', { ...active, profile: JSON.parse(JSON.stringify(profile)) })
}
export function activateDiabetesCase() {
  uni.setStorageSync('active-health-case-v1', { id: DIABETES_CASE_ID, profile: createDiabetesCaseProfile(), activatedAt: new Date().toISOString() })
  uni.setStorageSync('meal-records-health-case-v1', [])
}
export function deactivateHealthCase() { uni.setStorageSync('active-health-case-v1', null) }

export function createDiabetesCasePlan(profile, meal = '晚餐') {
  const planningProfile = JSON.parse(JSON.stringify(profile))
  planningProfile.members = planningProfile.members.map(member => ({ ...member, health: '一般成人' }))
  const plan = createPlan(planningProfile, meal)
  plan.caseId = DIABETES_CASE_ID
  return plan
}
