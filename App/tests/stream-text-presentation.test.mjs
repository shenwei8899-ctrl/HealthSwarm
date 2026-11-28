import test from 'node:test'
import assert from 'node:assert/strict'
import { createStreamTextPresentation } from '../src/services/stream-text-presentation.js'

function fixture() {
  const pending = [], changes = []
  const view = createStreamTextPresentation({onChange:text=>changes.push(text),
    schedule:fn=>{const job={fn};pending.push(job);return job},cancel:job=>job.cancelled=true})
  const next=()=>{const job=pending.find(job=>!job.used&&!job.cancelled);assert.ok(job);job.used=true;job.fn()}
  return {view,changes,pending,next,last:()=>changes.at(-1)||'',drain(){while(pending.some(job=>!job.used&&!job.cancelled))next()}}
}

test('public text grows in bounded batches and catches up within six frames',()=>{
  const h=fixture(),text='已经通过服务端校验的正文。'.repeat(100)
  h.view.update(text);assert.equal(h.changes.length,0)
  h.next();assert.ok(h.last().length>0&&h.last().length<text.length)
  for(let i=1;i<6;i++)h.next()
  assert.equal(h.last(),text);assert.equal(h.changes.length,6)
})

test('burst arrivals share a single scheduled update and do not extend the catchup deadline',()=>{
  const h=fixture()
  h.view.update('一'.repeat(120));h.next()
  for(let i=121;i<240;i++)h.view.update('一'.repeat(i))
  assert.equal(h.pending.filter(job=>!job.used&&!job.cancelled).length,1)
  for(let i=1;i<6;i++)h.next()
  assert.equal(h.last(),'一'.repeat(239));assert.equal(h.changes.length,6)
})

test('whole graphemes survive batching, including emoji and combining marks',()=>{
  const h=fixture(),unit='👨‍👩‍👧‍👦🇨🇳👍🏽e\u0301',text=unit.repeat(30)
  h.view.update(text);h.drain()
  const allowed=new Set(['']);let prefix=''
  for(const token of Array.from(new Intl.Segmenter(undefined,{granularity:'grapheme'}).segment(text),x=>x.segment)){prefix+=token;allowed.add(prefix)}
  assert.ok(h.changes.every(value=>allowed.has(value)))
  assert.equal(h.last(),text)
})

test('formal completion flushes immediately and ignores late queued callbacks',()=>{
  const h=fixture();h.view.update('公开预览。'.repeat(80));h.next()
  const late=h.pending.at(-1)
  h.view.update('正式结果，与预览不同。',false)
  late.fn();assert.equal(h.last(),'正式结果，与预览不同。')
  h.view.update('历史答复',false);assert.equal(h.last(),'历史答复')
})

test('replacement, permission clearing and disposal never leak old buffered text',()=>{
  const h=fixture();h.view.update('旧线程'.repeat(60));h.next()
  const old=h.pending.at(-1)
  h.view.update('新线程公开内容。');assert.equal(h.last(),'');old.fn();h.drain()
  assert.equal(h.last(),'新线程公开内容。')
  h.view.update('新线程公开内容。后续'.repeat(20));const denied=h.pending.at(-1)
  h.view.update('');denied.fn();assert.equal(h.last(),'')
  h.view.update('离开页面后不能再出现');const unmounted=h.pending.at(-1)
  h.view.dispose();const count=h.changes.length;unmounted.fn();h.view.update('迟到内容')
  assert.equal(h.changes.length,count)
})
