import test from 'node:test'
import assert from 'node:assert/strict'
import { effectScope, nextTick } from 'vue'
import { splitReplyGraphemes, replyGlyphs, quoteLayout, selectionHit, selectionPosition, replyQuote } from '../src/utils/reply-selection.js'
import { useReplySelection } from '../src/composables/use-reply-selection.js'
import { parseAiAnswer } from '../src/utils/ai-answer.js'
import { chatMessages } from '../src/services/cloud-chat.js'

test('visible ranges cross parsed paragraphs and keep emoji and combining marks intact',()=>{
 const layout=quoteLayout(parseAiAnswer('**第一段**\n\n第二段👩🏽‍🍳和e\u0301').blocks)
 assert.equal(layout.text,'第一段\n\n第二段👩🏽‍🍳和e\u0301')
 const glyphs=layout.blocks.flatMap(b=>replyGlyphs(b.leaf.segments,b.leaf.start))
 assert.ok(glyphs.some(g=>g.text==='👩🏽‍🍳'))
 assert.ok(glyphs.some(g=>g.text==='e\u0301'))
 assert.equal(layout.text.slice(glyphs[1].start,glyphs.at(-1).end),'一段\n\n第二段👩🏽‍🍳和e\u0301')
})

const rects=[{text:'字',start:0,end:1,left:10,right:26,top:100,bottom:128,width:16,height:28},
 {text:'词',start:1,end:2,left:26,right:42,top:100,bottom:128,width:16,height:28}]
test('cross-screen scrolling preserves bounds, replaces geometry and quotes the full range',()=>{
 const oldUni=globalThis.uni;globalThis.uni={getWindowInfo:()=>({windowWidth:390,windowHeight:844})}
 const quotes=[],h=useReplySelection((...args)=>quotes.push(args)),source={id:'cross'}
 try{
  h.viewport({top:80,bottom:600,width:390,scrollTop:0,scrollHeight:2200})
  h.begin(source,{point:{x:20,y:110},text:'甲乙丙丁'})
  h.geometry(source,{rects,scrollTop:0});h.drag({edge:'end',point:{x:40,y:110}});h.dragEnd()
  h.viewport({...h.state.viewport,scrollTop:800})
  assert.equal(h.state.start,0);assert.equal(h.state.end,2);assert.equal(h.position.value,null)
  const next=rects.map(r=>({...r,start:r.start+2,end:r.end+2}))
  h.geometry(source,{rects:next,scrollTop:800});h.drag({edge:'end',point:{x:40,y:110}});h.dragEnd()
  assert.equal(h.state.end,4);assert.equal(h.position.value.first,null);assert.equal(h.position.value.last.top,100)
  h.geometry(source,{rects:next,scrollTop:800});assert.equal(h.state.rects.length,4)
  h.quote();assert.equal(quotes[0][1],'甲乙丙丁')
 }finally{h.close();globalThis.uni=oldUni}
})
test('stationary edge drag scrolls repeatedly in both directions and stops on release or close',async()=>{
 const moves=[],h=useReplySelection(()=>{},delta=>{
  moves.push(delta);h.viewport({...h.state.viewport,scrollTop:h.state.viewport.scrollTop+delta})
  h.geometry({id:'edge'},{rects:[{...rects[1],start:2,end:3,top:570,bottom:598}],scrollTop:h.state.viewport.scrollTop})
 })
 try{
  h.viewport({top:80,bottom:600,width:390,scrollTop:200,scrollHeight:2200})
  h.begin({id:'edge'},{point:{x:20,y:110},text:'甲乙丙丁'});h.geometry({id:'edge'},{rects,scrollTop:200})
  h.drag({edge:'end',point:{x:40,y:590}});await new Promise(r=>setTimeout(r,260))
  assert.ok(moves.length>=2);assert.ok(moves.every(n=>n>0));assert.equal(h.state.end,3)
  h.dragEnd();const count=moves.length;await new Promise(r=>setTimeout(r,130));assert.equal(moves.length,count)
  h.drag({edge:'start',point:{x:20,y:85}});await new Promise(r=>setTimeout(r,130));assert.ok(moves.at(-1)<0)
  h.close();const closed=moves.length;await new Promise(r=>setTimeout(r,130));assert.equal(moves.length,closed)
 }finally{h.close()}
})
test('slow native geometry pauses edge scrolling until the new viewport is measured',async()=>{
 let moves=0
 const h=useReplySelection(()=>{},delta=>{moves++;h.viewport({...h.state.viewport,scrollTop:h.state.viewport.scrollTop+delta})})
 try{
  h.viewport({top:80,bottom:600,width:390,scrollTop:0})
  h.begin({id:'slow'},{point:{x:20,y:110},text:'字词'});h.geometry({id:'slow'},rects)
  h.drag({edge:'end',point:{x:40,y:590}})
  await new Promise(r=>setTimeout(r,350));assert.equal(moves,1)
  h.geometry({id:'slow'},{rects,scrollTop:h.state.viewport.scrollTop})
  await new Promise(r=>setTimeout(r,130));assert.equal(moves,2)
 }finally{h.close()}
})
test('only measured text hits start selection; paragraph trailing whitespace is excluded',()=>{
 assert.equal(selectionHit(rects,{x:20,y:110}).start,0)
 for(const point of [{x:80,y:110},{x:15,y:145},{x:5,y:110}])assert.equal(selectionHit(rects,point),null)
 assert.equal(selectionHit(rects,{x:80,y:110},true).start,1)
})
test('floating control stays inside narrow viewport and flips above a low selection',()=>{
 const position=selectionPosition(rects.map(r=>({...r,top:760,bottom:788})),0,2,{width:320,height:844})
 assert.ok(position.left>=8 && position.left+210<=320)
 assert.ok(position.top<760)
})
test('selecting an older reply rejects late geometry from another reply and quotes the selected text',async()=>{
 const scope=effectScope(),quotes=[];const h=scope.run(()=>useReplySelection((...args)=>quotes.push(args)))
 try{
  const source={id:'1'};h.begin(source,{point:{x:20,y:110},text:'字词'})
  h.geometry({id:'2'},rects);assert.equal(h.state.end,0)
  h.geometry(source,rects);assert.equal(h.state.start,0);assert.equal(h.state.end,1)
  h.drag({edge:'end',point:{x:40,y:110}});h.quote()
  assert.deepEqual(quotes,[[source,'字词']]);assert.equal(h.state.owner,'')
  h.begin(source,{point:{x:80,y:110},text:'字词'});h.geometry(source,rects);assert.equal(h.state.end,0)
  h.close();await nextTick()
 }finally{scope.stop()}
})
test('source lookup distinguishes a real message id from a local request id and history restores a quote',()=>{
 const thread='11111111-1111-4111-8111-111111111111'
 assert.deepEqual(replyQuote({id:'request-local',requestId:'request-id'},'片段',thread),{source_thread_id:thread,source_request_id:'request-id',text:'片段'})
 const quote=replyQuote({id:'42'},'片段',thread)
 assert.equal(quote.source_message_id,42)
 const restored=chatMessages({history:[{id:90,type:'human',content:'为什么？',extra_metadata:{reply_quote:quote}}]})
 assert.deepEqual(restored[0].replyQuote,quote)
 assert.equal(restored[0].text,'为什么？')
})

test('fallback keeps regional flags and emoji tag sequences together without Intl.Segmenter',()=>{
 for(const emoji of ['🇨🇳','👩🏽‍🍳','🏴\u{e0067}\u{e0062}\u{e007f}'])assert.deepEqual(splitReplyGraphemes(emoji,false),[emoji]);
 assert.deepEqual(splitReplyGraphemes('🇨🇳🇬🇧',false),['🇨🇳','🇬🇧']);
})


test('long replies keep chunk offsets and graphemes without expanding idle replies',()=>{
 const text='合理搭配👩🏽‍🍳🇨🇳。'.repeat(500),blocks=parseAiAnswer(text).blocks
 assert.equal(quoteLayout(blocks).leaves[0].groups,undefined)
 const group=quoteLayout(blocks,true).leaves[0].groups[0]
 assert.ok(group.chunks.every(c=>c.glyphs.length<=48))
 assert.equal(group.chunks.map(c=>c.text).join(''),text)
 for(const c of group.chunks){assert.equal(c.start,c.glyphs[0].start);assert.equal(text.slice(c.start,c.glyphs.at(-1).end),c.text)}
})
