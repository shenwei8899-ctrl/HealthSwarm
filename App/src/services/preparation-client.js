// 准备状态属于服务器；本机只保留未确认提交与准备ID。
export function createPreparationClient({send, root, storage, onChange, newId, onSaved = () => {}, current = () => true, onInvalidated = () => {}, wait = ms => new Promise(resolve => setTimeout(resolve, ms)), pollLimit = 150}) {
  let generation = 0, flight = null
  const valid = ticket => ticket === generation && current()
  async function run({body = null, id = '', resume = false} = {}) {
    if (flight) return flight
    const ticket = ++generation
    flight = (async () => {
      let value
      try {
        if (body) {
          onChange({status:'preparing',stage:'saving',profile_saved:false})
          value = (await send({path:root(),method:'POST',data:body,headers:{'Idempotency-Key':body.client_request_id},timeout:30000})).data
        } else {
          const path = root() + (id ? '/' + encodeURIComponent(id) : '/current') + (resume && id ? '/resume' : '')
          try { value = (await send({path, ...(resume && id ? {method:'POST'} : {})})).data }
          catch(error) {
            if(!resume || !['preparation_date_changed','preparation_sources_changed'].includes(error.businessCode))throw error
            if(!valid(ticket)){if(ticket===generation)onInvalidated();return}
            value=(await send({path:root()+'/current'})).data
          }
        }
        if(ticket===generation&&!current()){onInvalidated();return}
        if(!valid(ticket))return
        for(let recovery=0;!body && recovery<2 && ['absent','stale'].includes(value?.status);recovery++) {
          if(!valid(ticket))return
          const key='onboarding-preparation-existing-pending'
          const pending=storage.getStorageSync(key)||{client_request_id:newId()}
          storage.setStorageSync(key,pending)
          value=(await send({path:root()+'/from-profile',method:'POST',data:pending,headers:{'Idempotency-Key':pending.client_request_id},timeout:30000})).data
          if(ticket===generation&&!current()){onInvalidated();return}
          if(!valid(ticket))return
          if(value?.status!=='stale'||value.profile_saved!==true||!value.id||!value.date)break
          // 原键已得到确定答复；读回当前来源后才允许用新键继续，最多恢复一次。
          storage.setStorageSync(key,null)
          if(recovery===0){value=(await send({path:root()+'/current'})).data;if(ticket===generation&&!current()){onInvalidated();return}}
        }
        for (let count = 0; valid(ticket); count++) {
          if (!value || !['absent','preparing','ready','failed','blocked','stale'].includes(value.status)) throw new Error('准备状态返回不完整，请重新读取。')
          if (value.status !== 'absent' && (!value.id || !value.date || value.profile_saved !== true)) throw new Error('档案保存状态尚未确认，请继续原请求。')
          if (value.profile_saved) {
            storage.setStorageSync('onboarding-preparation-id',value.id)
            storage.setStorageSync('onboarding-preparation-pending',null)
            storage.setStorageSync('onboarding-preparation-existing-pending',null)
            onSaved()
          }
          onChange(value)
          if (value.status !== 'preparing') return value
          if (count >= pollLimit) {
            onChange({...value,status:'waiting',message:'准备仍在后台继续，你可以稍后继续查看。'})
            return value
          }
          await wait(2000)
          if (!valid(ticket)) return
          value = (await send({path:root()+'/'+encodeURIComponent(value.id)})).data
        }
      } catch (error) {
        if(ticket===generation&&!current()){onInvalidated();return}
        if (valid(ticket)) {
          const rejected=!value&&Number(error.code)>=400&&Number(error.code)<500&&![401,403].includes(Number(error.code))
          if(rejected){storage.setStorageSync('onboarding-preparation-pending',null);storage.setStorageSync('onboarding-preparation-existing-pending',null)}
          onChange({...value,status:rejected?'submission_error':'connection_error',profile_saved:!!value?.profile_saved,message:error.message||'暂时无法连接，请继续读取原准备。',error_code:error.businessCode||error.code,retryable:!rejected})
        }
      } finally {
        if (ticket === generation) flight = null
      }
    })()
    return flight
  }
  return {run, stop(){generation++;flight=null}}
}
