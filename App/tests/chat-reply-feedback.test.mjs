import test from 'node:test'
import assert from 'node:assert/strict'
import { replyMessageId, saveReplyFeedback } from '../src/services/chat-reply-feedback.js'

test('feedback accepts only real positive safe message ids',async()=>{
  for(const value of [null,'request-answer','0','01','1.5',-1,0,NaN,Infinity,9007199254740992])assert.equal(replyMessageId(value),null)
  assert.equal(replyMessageId('42'),42)
  let writes=0
  await assert.rejects(saveReplyFeedback('request-answer','like',{send:async()=>{writes++}}),/不支持/)
  assert.equal(writes,0)
})
test('confirmed feedback needs a matching write receipt',async()=>{
  const calls=[]
  assert.equal(await saveReplyFeedback(42,'like',{send:async options=>{calls.push(options);return{data:options.method?{id:7,message_id:42,rating:'like'}:{has_feedback:false,feedback:null}}}}),'like')
  assert.deepEqual(calls,[{path:'/api/chat/message/42/feedback'},{path:'/api/chat/message/42/feedback',method:'POST',data:{rating:'like'}}])
})
test('existing immutable feedback is read without another write',async()=>{
  const calls=[]
  assert.equal(await saveReplyFeedback(42,'dislike',{send:async options=>{calls.push(options);return{data:{has_feedback:true,feedback:{id:3,rating:'like'}}}}}),'like')
  assert.equal(calls.length,1)
})
for(const code of ['NETWORK_ERROR',409])test(`uncertain/conflicting write ${code} is read back without reposting`,async()=>{
  const calls=[]
  assert.equal(await saveReplyFeedback(42,'like',{send:async options=>{calls.push(options);if(options.method)throw Object.assign(new Error('unknown'),{code});return{data:calls.length===1?{has_feedback:false,feedback:null}:{has_feedback:true,feedback:{id:9,rating:'dislike'}}}}}),'dislike')
  assert.deepEqual(calls.map(item=>item.method||'GET'),['GET','POST','GET'])
})
test('no saved feedback is not presented as success after a lost write',async()=>{
  let posts=0
  await assert.rejects(saveReplyFeedback(42,'like',{send:async options=>{if(options.method){posts++;throw Object.assign(new Error('lost'),{code:'NETWORK_ERROR'})}return{data:{has_feedback:false,feedback:null}}}}),/尚未确认/)
  assert.equal(posts,1)
})
test('malformed read and revoked access never trigger a write',async()=>{
  for(const read of [()=>({data:{has_feedback:false,feedback:{id:1,rating:'like'}}}),()=>{throw Object.assign(new Error('forbidden'),{code:403})}]){
    let posts=0
    await assert.rejects(saveReplyFeedback(42,'like',{send:async options=>{if(options.method)posts++;return read()}}))
    assert.equal(posts,0)
  }
})
test('late read after conversation change cannot post feedback',async()=>{
  let active=true,posts=0
  await assert.rejects(saveReplyFeedback(42,'like',{isCurrent:()=>active,send:async options=>{if(options.method)posts++;active=false;return{data:{has_feedback:false,feedback:null}}}}),/对话已变化/)
  assert.equal(posts,0)
})
test('mismatched write receipt cannot show a saved vote',async()=>{
  await assert.rejects(saveReplyFeedback(42,'like',{send:async options=>({data:options.method?{id:1,message_id:43,rating:'like'}:{has_feedback:false,feedback:null}})}),/尚未确认/)
})
