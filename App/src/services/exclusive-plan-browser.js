/** 每个页面保留本次会话已见日期；回执版本由服务器计算，客户端缓存不授予权限。 */
export const exclusiveBrowseState = () => ({directory:null,days:{},selected:1,checking:false,error:'',active:false})

export function createExclusivePlanBrowser({state,send,scope,later=setTimeout,cancelLater=clearTimeout,onDay=()=>{}}){
 let epoch=0,owner='',selection=null,timer=null
 const pending=new Map()
 const identity=s=>JSON.stringify([s.familyId,s.groupId,s.tier])
 function reset(){epoch++;pending.clear();if(timer)cancelLater(timer);timer=null;Object.assign(state,exclusiveBrowseState())}
 function hide(){epoch++;pending.clear();if(timer)cancelLater(timer);timer=null;state.active=false;state.checking=true;for(const row of Object.values(state.days)){row.loading=false;row.verified=false}}
 const root=()=>'/api/health/v1/families/'+encodeURIComponent(selection.familyId)+'/exclusive-plans/'+encodeURIComponent(selection.groupId)+'/tiers/'+encodeURIComponent(selection.tier)
 function current(token,account){if(owner!==scope()){reset();owner=scope();return false}return state.active&&token===epoch&&account===scope()}
 function fail(error,number){
  if([401,403,404,409].includes(Number(error.code))||error.businessCode==='plan_basis_changed'){reset();state.error=error.message;return}
  if(number){const row=state.days[number];if(row){row.error=error.message;row.verified=false;if([404,409,410,422].includes(Number(error.code))){row.data=null;row.version=null}}}
  else {state.error=error.message;if([404,409,410,422].includes(Number(error.code))){state.directory=null;state.days={}}}
 }
 async function open(target){
  const account=scope()
  if(owner!==account||!selection||identity(selection)!==identity(target))reset()
  owner=account;selection={...target};state.active=true;state.checking=true;state.error=''
  const token=++epoch;pending.clear()
  for(const row of Object.values(state.days))row.verified=false
  try{
   const {data}=await send({path:root()+'/directory'})
   if(!current(token,account))return
   if(!Array.isArray(data.days)||data.days.length!==7)throw Error('计划日期目录不完整，请重试')
   for(const [number,row] of Object.entries(state.days)){
    const day=data.days.find(d=>Number(d.day_no)===Number(number))
    if(!day||!day.available||row.contentVersion!==day.content_version||row.sourceVersion!==day.version)delete state.days[number]
   }
   state.directory=data
   if(!data.days.some(d=>Number(d.day_no)===state.selected))state.selected=Number(data.days[0].day_no)
   await readDay(state.selected)
  }catch(error){if(current(token,account))fail(error)}
  finally{if(current(token,account))state.checking=false}
 }
 function readDay(number){
  if(!state.active||owner!==scope()) {if(owner!==scope())reset();return Promise.resolve()}
  if(pending.has(number))return pending.get(number)
  const directory=state.directory?.days.find(d=>Number(d.day_no)===number)
  if(!directory)return Promise.resolve()
  const token=epoch,account=owner
  let row=state.days[number]||{data:null,version:null,contentVersion:directory.content_version,sourceVersion:directory.version}
  state.days[number]=row;row=state.days[number];row.loading=true;row.verified=false;row.error=''
  const flight=Promise.resolve().then(async()=>{
   try{
    if(!directory.available)throw Object.assign(Error('当天菜谱来源已变化，请更新计划'),{code:410})
    const {data}=await send({path:root()+'/days/'+number+(row.version?'?known_version='+encodeURIComponent(row.version):'')})
    if(!current(token,account))return
    if(data.day_no!==number||typeof data.version!=='string'||data.unchanged&&!row.data||!data.unchanged&&!Array.isArray(data.day?.meals))throw Error('当天菜谱返回不完整，请重试')
    if(!data.unchanged)row.data=data.day
    row.version=data.version;row.verified=true
    if(state.selected===number){onDay(number);prefetch(number+1)}
   }catch(error){if(current(token,account))fail(error,number)}
   finally{if(current(token,account)){row.loading=false;pending.delete(number)}}
  })
  pending.set(number,flight)
  return flight
 }
 function prefetch(number){
  if(number>7||state.days[number]?.data||pending.has(number))return
  if(timer)cancelLater(timer)
  const token=epoch,account=owner
  timer=later(()=>{timer=null;if(current(token,account)&&state.selected+1===number)void readDay(number)},250)
 }
 function select(number){
  number=Number(number)
  if(!Number.isInteger(number)||!state.directory?.days.some(d=>Number(d.day_no)===number))return Promise.resolve()
  state.selected=number
  return readDay(number)
 }
 const ready=()=>state.active&&owner===scope()&&!state.checking&&!!state.days[state.selected]?.verified
 return {open,select,retry:()=>readDay(state.selected),hide,reset,ready}
}
