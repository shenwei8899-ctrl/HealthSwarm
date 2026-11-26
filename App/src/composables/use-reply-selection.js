import { computed, reactive } from 'vue'
import { selectionHit, selectionPosition } from '../utils/reply-selection.js'

export function useReplySelection(onQuote, scrollBy = () => {}) {
 const state=reactive({owner:'',source:null,text:'',point:null,region:null,start:0,end:0,rects:[],dragging:false,viewport:null,revision:0,scrolling:false,measuring:false})
 let expiry=null,scrollTimer=null,edgeTimer=null,dragPoint=null,dragEdge=null
 const screenRects=()=>state.rects.map(r=>({...r,top:r.top-(state.viewport?.scrollTop||0),bottom:r.bottom-(state.viewport?.scrollTop||0)}))
 const position=computed(()=>{
  if(!state.owner||state.end<=state.start)return null
  const window=uni.getWindowInfo(),v=state.viewport||{top:0,bottom:window.windowHeight}
  const result=selectionPosition(screenRects(),state.start,state.end,{width:window.windowWidth,height:window.windowHeight,top:v.top,bottom:v.bottom})
  // Keep the actively dragged node mounted while its endpoint leaves the viewport.
  if(state.dragging&&dragPoint){
   const r=result||{left:8,top:v.top+8,first:null,last:null}
   if(dragEdge==='start')r.first={left:dragPoint.x,top:dragPoint.y+22}
   else r.last={right:dragPoint.x,bottom:dragPoint.y+18}
   return {...r,scrolling:state.scrolling}
  }
  return result?{...result,scrolling:state.scrolling}:null
 })
 function dragEnd(){clearInterval(edgeTimer);edgeTimer=null;state.dragging=false;dragPoint=null;dragEdge=null}
 function close(){clearTimeout(expiry);clearTimeout(scrollTimer);dragEnd();Object.assign(state,{owner:'',source:null,text:'',point:null,region:null,start:0,end:0,rects:[],scrolling:false,measuring:false})}
 function begin(source,event){
  close();Object.assign(state,{owner:String(source.id),source,text:event.text,point:event.point})
  expiry=setTimeout(()=>{if(!state.end)close()},4000)
 }
 function viewport(value){
  const previous=state.viewport;state.viewport=value
  if(!state.owner)return
  if(previous&&['top','bottom','width','scrollTop'].every(key=>previous[key]===value[key]))return
  if(previous&&previous.width!==value.width)state.rects=[]
  state.revision++;state.measuring=true
  if(previous&&previous.scrollTop!==value.scrollTop){
   state.scrolling=true;clearTimeout(scrollTimer);scrollTimer=setTimeout(()=>{state.scrolling=false},130)
  }
 }
 function updateDrag(){
  if(!dragPoint)return
  const hit=selectionHit(screenRects().filter(r=>r.region===state.region),dragPoint,true)
  if(!hit)return
  if(dragEdge==='start'&&hit.start<state.end)state.start=hit.start
  if(dragEdge==='end'&&hit.end>state.start)state.end=hit.end
 }
 function geometry(source,payload){
  if(state.owner!==String(source.id))return
  state.measuring=false
  const rows=Array.isArray(payload)?payload:payload.rects
  const offset=Array.isArray(payload)?0:payload.scrollTop
  const rects=new Map(state.rects.map(r=>[r.start,r]))
  for(const r of rows)rects.set(r.start,{...r,top:r.top+offset,bottom:r.bottom+offset})
  state.rects=[...rects.values()].sort((a,b)=>a.start-b.start)
  if(state.end){updateDrag();return}
  if(!state.point)return
  const hit=selectionHit(screenRects(),state.point)
  if(hit){state.start=hit.start;state.end=hit.end;state.region=hit.region;clearTimeout(expiry)}
  else close()
 }
 function edgeScroll(){
  // Native selector queries can span several frames. Wait for the new glyphs
  // before scrolling again, otherwise every result would be invalidated.
  const v=state.viewport;if(!v||!dragPoint||state.measuring)return
  const band=48,y=dragPoint.y
  const speed=y<v.top+band?-Math.min(20,Math.max(2,(v.top+band-y)/2)):y>v.bottom-band?Math.min(20,Math.max(2,(y-v.bottom+band)/2)):0
  if(speed)scrollBy(speed)
 }
 function drag({edge,point}){
  dragEdge=edge;dragPoint=point;state.dragging=true;updateDrag()
  if(!edgeTimer)edgeTimer=setInterval(edgeScroll,100)
 }
 function quote(){
  const text=state.text.slice(state.start,state.end).trim()
  if(!text)return
  if(text.length>1200){uni.showToast({title:'请选择1200字以内的片段',icon:'none'});return}
  onQuote(state.source,text);close()
 }
 return {state,position,begin,geometry,viewport,drag,dragEnd,quote,close}
}
