import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { processingDisclosure, processingPolicyKey } from '../src/utils/processing-disclosure.js'

const configuration = () => ({policy_version:'developer-test-20261023-v1',
  consultation:{available:true,processor:`deepseek:${'a'.repeat(64)}`},
  meal_plan:{available:true,processor:`deepseek:${'a'.repeat(64)}`}})

test('disclosure explains health data transfer without exposing internal identifiers',()=>{
  const config=configuration(),notice=processingDisclosure(config)
  assert.match(notice.content,/健康情况、饮食偏好及限制/)
  assert.match(notice.content,/发送给 AI 服务/)
  assert.doesNotMatch(JSON.stringify(notice),/developer-test|deepseek|DeepSeek|a{64}/)
  assert.equal(config.consultation.processor,`deepseek:${'a'.repeat(64)}`)
  config.meal_plan.processor='openai:other-fingerprint'
  assert.doesNotMatch(JSON.stringify(processingDisclosure(config)),/DeepSeek|OpenAI/)
  assert.doesNotMatch(processingDisclosure({consultation:{processor:'unknown:private'}}).content,/unknown|private/)
})

function harness(){
  let revision=1,modal,writes=0,submittedConsent
  const ref=value=>({value}),profile=ref({healthConfiguration:configuration()}),fieldError=ref('')
  const deps={cloudSaving:ref(false),cloudLoading:ref(false),cloudLoaded:ref(true),invited:ref(false),
    syncDiners(){},self:ref(null),isMockMode:false,step:ref(2),profile,processingPolicyReady:ref(true),
    processingNotice:{get value(){return processingDisclosure(profile.value.healthConfiguration)}},
    sessionRevision:()=>revision,processingPolicyKey,alive:true,fieldError,
    uni:{showModal:options=>{modal=options},reLaunch(){}},cloudError:ref(''),cloudErrorCode:ref(null),
    saveOnboardingProfile:async(_profile,_refs,consent)=>{writes++;submittedConsent=consent;return {householdId:'family'}},
    reportSelections:ref(new Map()),retryWithReports:false,
    scopedStorage:{setStorageSync(){}},preserveProgress(){},draftStorageKey:'draft',preparationRoute:()=>'/prepared',completed:false}
  deps.uni.setStorageSync=()=>{}
  const source=readFileSync(new URL('../src/pages/onboarding/index.vue',import.meta.url),'utf8')
  const commitSource=source.slice(source.indexOf('async function commit('),source.indexOf('\nfunction next('))
  const commit=new Function('deps',`let {${Object.keys(deps)}}=deps;${commitSource};return commit`)(deps)
  return {commit,profile,fieldError,get modal(){return modal},get writes(){return writes},get submittedConsent(){return submittedConsent},switchAccount(){revision++}}
}

test('cancel does not submit; explicit acceptance submits once',async()=>{
  const h=harness();await h.commit()
  h.modal.success({confirm:false});assert.equal(h.writes,0)
  h.modal.success({confirm:true});assert.equal(h.writes,1)
  assert.deepEqual(h.submittedConsent,{purpose:'consultation',processor:configuration().consultation.processor,policy_version:configuration().policy_version})
})

test('account or policy changes while the consent dialog is open invalidate acceptance',async()=>{
  const h=harness();await h.commit();h.switchAccount();h.modal.success({confirm:true});assert.equal(h.writes,0)
  const other=harness();await other.commit();other.profile.value.healthConfiguration.policy_version='updated'
  other.modal.success({confirm:true});assert.equal(other.writes,0);assert.match(other.fieldError.value,/重新确认/)
})
