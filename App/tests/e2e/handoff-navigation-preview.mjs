// 仅用于本机 H5 生命周期协议回归；不代替真实 Worker、数据库或交易验收。
import http from 'node:http'
import fs from 'node:fs/promises'
import path from 'node:path'
const root=path.resolve(process.env.HANDOFF_H5_DIR||'.codex/app-handoff-plan-20261022/api-h5')
const day=()=>new Date(Date.now()+8*3600000).toISOString().slice(0,10)
const ids={family:'11111111-1111-4111-8111-111111111111',member:'22222222-2222-4222-8222-222222222222',health:'33333333-3333-4333-8333-333333333333',arrangement:'44444444-4444-4444-8444-444444444444'}
const calls=[],state={denied:false,version:1}
function profile(account){return {source:'api',householdId:ids.family,onboarded:true,familyVersion:1,isOwner:true,selfMemberId:ids.member,usageMode:'个人使用',defaultDiners:[ids.member],members:[{id:ids.member,healthMemberId:ids.health,version:1,name:'合成账号'+account,relation:'本人',birthDate:'1990-01-01',healthStatus:'none',goals:['均衡饮食'],cuisines:['不限菜系'],tastePreferences:['不限口味'],allergyStatus:'none',intoleranceStatus:'none',avoidanceStatus:'none',doctorStatus:'none'}]}}
function arrangement(account){return {status:'ready',id:ids.arrangement,version:state.version,date:day(),saved:true,validation:{status:'passed'},procurement:{checked:true},analysis:{source:'agent',request_id:ids.health,run_id:ids.member,text:'仅合成协议验收：三餐与说明来自同一个固定测试快照。'},meals:['breakfast','lunch','dinner'].map(type=>({type,detail_ref:type,members:[{id:ids.member,name:'合成账号'+account}],dishes:[{id:'dish',name:'合成协议菜品',recipeVersion:'synthetic-v1',ingredients:[{name:'合成食材',planned_grams:100}],steps:['仅合成做法，不作为实际建议']}],memberNotes:[{memberId:ids.member,dishes:[{dishId:'dish',name:'合成协议菜品',grams:100}]}],nutrition:{kcal:null},nutritionSource:{source:'synthetic-protocol-only'},purchase:{package_sn:'synthetic-'+type,package_version:1,items:[]}}))}}
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css','.jpg':'image/jpeg','.png':'image/png','.svg':'image/svg+xml'}
const server=http.createServer(async(req,res)=>{
 const url=new URL(req.url,'http://127.0.0.1:15193')
 const json=(value,status=200)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(value))}
 try{
  if(url.pathname==='/fixture-state'){json({state,calls});return}
  if(url.pathname==='/fixture-control'&&req.method==='POST'){let body='';for await(const chunk of req)body+=chunk;Object.assign(state,JSON.parse(body));json(state);return}
  if(url.pathname.startsWith('/api/')){
   const account=req.headers.authorization==='Bearer synthetic-b'?'B':'A'
   calls.push({method:req.method,path:url.pathname,account})
   if(url.pathname==='/api/auth/token'){let body='';for await(const chunk of req)body+=chunk;const b=new URLSearchParams(body).get('username')==='synthetic-b';json({user_id:b?102:101,access_token:b?'synthetic-b':'synthetic-a'});return}
   if(!req.headers.authorization){json({message:'请登录'},401);return}
   if(url.pathname==='/api/auth/me'){json({id:account==='B'?102:101,username:'合成账号'+account});return}
   if(url.pathname==='/api/family'){json([{id:ids.family,name:'合成家庭',is_owner:true}]);return}
   if(url.pathname.endsWith('/miniapp-profile')){json(profile(account));return}
   if(url.pathname.endsWith('/configuration')){json({policy_version:'',meal_plan:{available:false},consultation:{available:false},limits:{image_mb:10,pdf_mb:20,report_pages:20,meal_images:3}});return}
   if(url.pathname==='/api/health/v1/members'){json([{id:ids.health,display_name:'合成账号'+account,is_owner:true,scopes:['ai_use','diet_edit']}]);return}
   if(url.pathname.endsWith('/readiness')){json({capabilities:{member_id:ids.health},entries:[{entry_type:'consultation',status:'dependency_not_ready'}]});return}
   if(url.pathname.includes('/daily-arrangements/')){
    if(state.denied){json({message:'合成测试：用途授权已撤回',code:'consent_required'},403);return}
    const saved=arrangement(account)
    if(url.pathname.endsWith('/purchase')){json({arrangement_id:saved.id,version:saved.version,purchase:{items:[],available:false,message:'合成协议验收不提供交易'}});return}
    const meal=url.pathname.match(/\/meals\/(breakfast|lunch|dinner)$/)
    if(meal){json({arrangement_id:saved.id,version:saved.version,meal:saved.meals.find(row=>row.type===meal[1])});return}
    json(saved);return
   }
   json({message:'合成协议未启用该能力'},503);return
  }
  const target=path.resolve(root,'.'+decodeURIComponent(url.pathname))
  if(target!==root&&!target.startsWith(root+path.sep)){res.writeHead(403);res.end();return}
  const filename=path.extname(target)?target:path.join(root,'index.html')
  res.writeHead(200,{'Content-Type':mime[path.extname(filename)]||'application/octet-stream','Cache-Control':'no-store'});res.end(await fs.readFile(filename))
 }catch{if(!res.headersSent)res.writeHead(500);res.end('Synthetic preview failure')}
})
server.listen(15193,'127.0.0.1',()=>console.log('Handoff H5 synthetic protocol preview: http://127.0.0.1:15193'))
