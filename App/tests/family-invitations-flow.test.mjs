import test from 'node:test'
import assert from 'node:assert/strict'
import { createEntryResolver } from '../src/services/entry-routing.js'
import { createFamilyShareController, familyShareState } from '../src/services/family-invitations.js'

function harness(send) {
  let revision=1
  const state=familyShareState(),calls=[]
  const session=()=>({token:'synthetic',householdId:'family',accountId:'owner'})
  const controller=createFamilyShareController({state,session,revision:()=>revision,now:()=>1000,
    send:async options=>{calls.push(options);return send?send(options):{data:{options:[
      {key:'mom',member_id:'mom',name:'妈妈',code:'family_'+ 'm'.repeat(32),expires_at:'2099-01-01T00:00:00Z'},
      {key:'family',member_id:null,name:'邀请其他家人',code:'familyshare_'+ 'f'.repeat(65),expires_at:null,version:0},
    ]}}}})
  return {state,calls,controller,switchAccount(){revision++}}
}

test('a completed prefilled profile still routes invited member to personal review',async()=>{
  const account={accountId:'synthetic',token:'synthetic',householdId:'family',families:[{id:'family',invitationReviewPending:true,onboardingRequired:false}]}
  const resolve=createEntryResolver({session:()=>account,auth:{restore:async()=>account},readProfile:async()=>({householdId:'family',completeProfile:true,invitationReviewPending:true})})
  assert.equal(await resolve(),'/pages/onboarding/index')
})

test('share uses the clicked member, fixed cover and generic title without another mutation',async()=>{
  const h=harness();await h.controller.prepare()
  const result=h.controller.share({from:'button',target:{dataset:{inviteKey:'mom'}}})
  assert.equal(result.title,'邀请你加入家庭')
  assert.equal(result.path,'/pages/invite/index?token=family_'+ 'm'.repeat(32))
  assert.ok(result.imageUrl.startsWith('/static/'))
  assert.equal(h.calls.length,1)
  assert.notEqual(h.controller.share({from:'button',target:{dataset:{inviteKey:'family'}}}).path,result.path)
})

test('stale identity, hidden page, expired ticket and unknown button cannot reuse invitation credentials',async()=>{
  for(const action of ['account','hide','unknown','expired']){
    const h=harness();await h.controller.prepare()
    if(action==='account')h.switchAccount()
    if(action==='hide')h.controller.discard()
    if(action==='expired')h.state.options[0].expires_at='1970-01-01T00:00:00Z'
    const share=h.controller.share({from:'button',target:{dataset:{inviteKey:action==='unknown'?'missing':'mom'}}})
    assert.ok(!share.path.includes('token='),action)
  }
})

test('late preparation after account switching cannot populate share state',async()=>{
  let release
  const h=harness(()=>new Promise(done=>release=done))
  const pending=h.controller.prepare();h.switchAccount()
  release({data:{options:[{key:'mom',code:'family_'+ 'm'.repeat(32)}]}})
  await pending
  assert.deepEqual(h.state.options,[])
})

test('revocation removes the share credential before the server request settles',async()=>{
  const h=harness();await h.controller.prepare()
  const pending=h.controller.revoke('mom')
  assert.ok(!h.controller.share({from:'button',target:{dataset:{inviteKey:'mom'}}}).path.includes('token='))
  await pending
  assert.equal(h.calls[1].path,'/api/family/family/members/mom/invite/revoke')
  assert.equal(h.calls[1].data.code,'family_'+ 'm'.repeat(32))
})
