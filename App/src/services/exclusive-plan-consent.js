/** 仅在用户明确勾选后确认餐单用途，不扩展咨询授权。 */
export function createPlanConsent({send, family, revision, startAnalysis, state = {loading:false, busy:false, processor:'', policyVersion:'', members:[], error:''}}) {
  let epoch = 0
  const stop = () => {epoch++; Object.assign(state,{loading:false,busy:false,members:[],error:''})}
  async function load() {
    const token=++epoch, scope=revision(), fid=family()
    const active=()=>token===epoch&&scope===revision()&&fid===family()
    Object.assign(state,{loading:true,error:'',members:[]})
    try {
      const [profile,config]=await Promise.all([send({path:`/api/family/${encodeURIComponent(fid)}/miniapp-profile`}),send({path:'/api/health/v1/configuration'})])
      if(!active())return
      if(profile.data.householdId!==fid||!Array.isArray(profile.data.members))throw new Error('家庭资料已变化，请重新读取。')
      const policy=config.data
      if(!policy.meal_plan?.available||!policy.meal_plan.processor||!policy.policy_version)throw new Error(policy.meal_plan?.reason||'餐单分析服务尚未配置。')
      state.processor=policy.meal_plan.processor;state.policyVersion=policy.policy_version
      const diners=profile.data.defaultDiners||[]
      if(!diners.length)throw new Error('请先在家庭档案中选择就餐成员。')
      const members=[]
      for(const id of diners){
        const member=profile.data.members.find(row=>row.id===id)
        if(!member)throw new Error('就餐成员已变化，请核对家庭档案。')
        let needsConsent=!member.healthMemberId
        if(member.healthMemberId){
          const {data}=await send({path:`/api/health/v1/members/${encodeURIComponent(member.healthMemberId)}/readiness`})
          if(!active())return
          if(data.capabilities?.member_id!==member.healthMemberId)throw new Error('成员授权状态已变化，请重新读取。')
          const entry=data.capabilities.tasks?.find(row=>row.task_type==='initial_meal_preview')
          if(!entry)throw new Error('餐单分析状态返回不完整，请重新读取。')
          needsConsent=entry?.reason_code==='consent_required'
          if(!needsConsent&&entry.status!=='available'&&!(entry.status==='needs_input'&&entry.reason_code==='selection_required'))throw new Error(entry.message||'该成员的餐单资料、授权或服务配置尚未就绪，请核对家庭档案。')
        }
        if(needsConsent)members.push({...member,checked:false,canConfirm:member.canConfirmAnalysis===true})
      }
      if(active())state.members=members
    }catch(e){if(active())state.error=e.message||'暂时无法读取餐单分析授权。'}
    finally{if(active()){state.loading=false;state.busy=false}}
  }
  async function accept() {
    if(state.busy||state.loading||!state.members.length)return false
    const selected=state.members.filter(member=>member.checked&&member.canConfirm)
    if(!selected.length){state.error='请先勾选需要确认的成员。';return false}
    const token=epoch,scope=revision(),fid=family(),active=()=>token===epoch&&scope===revision()&&fid===family()
    state.busy=true;state.error=''
    try{
      for(const member of selected){
        await startAnalysis(fid,member,{processor:state.processor,policy_version:state.policyVersion},'meal_plan')
        if(!active())return false
      }
      await load()
      return scope===revision()&&fid===family()&&!state.error&&!state.members.length
    }catch(e){if(active())state.error=e.message||'授权尚未确认，请重新读取后核对。';return false}
    finally{if(active())state.busy=false}
  }
  return {state,load,accept,stop}
}
