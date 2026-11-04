import { createPhoneBindingClient } from './phone-binding-client.js'

// The native button obtains consent. Login/grant codes stay separate and only in memory.
export function createPhoneLogin({ auth, session, commerce, accountContext, appId, randomKey, resolveEntry, navigate, update,
  setTimer=setTimeout, clearTimer=clearTimeout }) {
  let epoch=0,busy=false,binding={},error='',awaitingAuthorization=false,authorizationTimer=null,needsAuthorization=false
  const publish=()=>update({busy,error,awaitingAuthorization,needsAuthorization,uncertain:binding.uncertain===true})
  function stopWaiting() {
    if(authorizationTimer!==null)clearTimer(authorizationTimer)
    authorizationTimer=null;awaitingAuthorization=false
  }
  function beginAuthorization() {
    if(busy||binding.uncertain)return
    stopWaiting();error='';awaitingAuthorization=true;publish()
    // Keep the native button enabled: changing disabled here can suppress its consent action.
    authorizationTimer=setTimer(()=>{
      authorizationTimer=null;awaitingAuthorization=false
      error='微信尚未返回手机号授权。若没有弹出授权窗口，请使用微信真机预览重试；仍失败时请检查小程序的手机号接口权限和隐私保护指引。'
      publish()
    },30000)
  }
  const phone=createPhoneBindingClient({commerce,accountContext,appId,randomKey,update:value=>{binding=value}})
  const identity=()=>{const s=session();return s?.token?String(s.accountId)+':'+s.token:''}
  const current=(mine,owner)=>mine===epoch&&(!owner||owner===identity())
  async function run(detail,restoreOnly,loginWithoutGrant=false) {
    if(busy)return
    stopWaiting()
    if(!restoreOnly&&!loginWithoutGrant&&(!detail?.code||detail.errMsg&&detail.errMsg!=='getPhoneNumber:ok')) {
      const message=detail?.errMsg||''
      error=/deny|cancel/i.test(message)?'你已取消手机号授权，可以再次点击微信登录。'
        :Number(detail?.errno)===1400001?'小程序的手机号授权额度已用完，请联系管理员补充额度。'
        :/privacy/i.test(message)?'微信手机号授权未完成，请检查小程序的隐私保护指引配置。'
        :/no permission|permission denied/i.test(message)?'当前小程序没有手机号接口权限，请联系管理员检查小程序认证与接口权限。'
        :'未取得微信手机号授权，请重试；开发者工具内可使用微信真机预览排查。'
      if(Number.isSafeInteger(detail?.errno))error+='（错误码 '+detail.errno+'）'
      publish();return
    }
    const mine=++epoch;busy=true;error='';publish()
    try {
      let account=null
      if(session()?.token){
        try { account=await auth.restore() }
        catch(e){
          // An explicit retry may renew an expired session; never replace a changed identity.
          if(restoreOnly||Number(e.code)!==401)throw e
        }
      }
      if(!current(mine))return
      if(!account?.token){if(restoreOnly)return;await auth.login()}
      if(!current(mine))return
      const owner=identity();if(!owner)throw Error('登录未完成，请重试。')
      await phone.load()
      if(!current(mine,owner))return
      if(!binding.ready)throw Error(binding.error||'手机号状态读取失败，请重试。')
      needsAuthorization=!binding.status?.phone_bound
      if(needsAuthorization&&!restoreOnly&&!loginWithoutGrant){
        if(!binding.config?.available)throw Error('手机号授权暂未开放，请稍后重试。')
        await phone.authorize(detail)
        if(!current(mine,owner))return
      }
      needsAuthorization=!binding.status?.phone_bound
      if(needsAuthorization){error=binding.error||(loginWithoutGrant?'当前微信账号尚未绑定手机号，请点击按钮完成手机号授权后继续。':'');return}
      const url=await resolveEntry()
      if(current(mine,owner))await navigate(url)
    } catch(e) {if(mine===epoch)error=e.message||'登录未完成，请重试。'}
    finally {if(mine===epoch){busy=false;publish()}}
  }
  function dispose(){epoch++;stopWaiting();busy=false;error='';needsAuthorization=false;phone.dispose();publish()}
  return {beginAuthorization,login:()=>run(null,false,true),authorize:detail=>run(detail,false),restore:()=>run(null,true),dispose}
}
