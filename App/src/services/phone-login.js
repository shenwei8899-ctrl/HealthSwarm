import { createPhoneBindingClient } from './phone-binding-client.js'

// The native button obtains consent. Login/grant codes stay separate and only in memory.
export function createPhoneLogin({ auth, session, commerce, accountContext, appId, randomKey, resolveEntry, navigate, update }) {
  let epoch=0,busy=false,binding={},error=''
  const publish=()=>update({busy,error,uncertain:binding.uncertain===true})
  const phone=createPhoneBindingClient({commerce,accountContext,appId,randomKey,update:value=>{binding=value}})
  const identity=()=>{const s=session();return s?.token?String(s.accountId)+':'+s.token:''}
  const current=(mine,owner)=>mine===epoch&&(!owner||owner===identity())
  async function run(detail,restoreOnly) {
    if(busy)return
    if(!restoreOnly&&(!detail?.code||detail.errMsg&&detail.errMsg!=='getPhoneNumber:ok')) {
      error='你已取消手机号授权，可以再次点击微信登录。';publish();return
    }
    const mine=++epoch;busy=true;error='';publish()
    try {
      const account=session()?.token?await auth.restore():null
      if(!current(mine))return
      if(!account?.token){if(restoreOnly)return;await auth.login()}
      if(!current(mine))return
      const owner=identity();if(!owner)throw Error('登录未完成，请重试。')
      await phone.load()
      if(!current(mine,owner))return
      if(!binding.ready)throw Error(binding.error||'手机号状态读取失败，请重试。')
      if(!binding.status?.phone_bound&&!restoreOnly){
        if(!binding.config?.available)throw Error('手机号授权暂未开放，请稍后重试。')
        await phone.authorize(detail)
        if(!current(mine,owner))return
      }
      if(!binding.status?.phone_bound){error=binding.error||'';return}
      const url=await resolveEntry()
      if(current(mine,owner))await navigate(url)
    } catch(e) {if(mine===epoch)error=e.message||'登录未完成，请重试。'}
    finally {if(mine===epoch){busy=false;publish()}}
  }
  function dispose(){epoch++;busy=false;error='';phone.dispose();publish()}
  return {authorize:detail=>run(detail,false),restore:()=>run(null,true),dispose}
}
