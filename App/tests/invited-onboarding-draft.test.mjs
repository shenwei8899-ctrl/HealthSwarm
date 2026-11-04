import test from 'node:test'
import assert from 'node:assert/strict'
import {canRestoreOnboardingDraft} from '../src/services/onboarding-draft.js'
const profile=()=>({householdId:'family',selfMemberId:'mom',isOwner:false,familyVersion:2,members:[{id:'mom',version:4}]})
test('invited draft restores the same member and saved version despite unrelated family changes',()=>{
 const p=profile(),draft={profile:structuredClone(p)};draft.profile.familyVersion=1
 assert.equal(canRestoreOnboardingDraft(draft,p),true)
})
test('new server facts, another member and another family cannot be overwritten by a draft',()=>{
 for(const change of [d=>d.profile.members[0].version--,d=>d.profile.selfMemberId='dad',d=>d.profile.householdId='other']){
  const p=profile(),d={profile:structuredClone(p)};change(d);assert.equal(canRestoreOnboardingDraft(d,p),false)
 }
})
