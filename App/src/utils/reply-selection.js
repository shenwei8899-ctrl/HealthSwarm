// Only the active reply expands into measured glyphs; other replies keep their normal rendering.
let graphemeSegmenter=null
try { if(typeof Intl!=='undefined' && Intl.Segmenter)graphemeSegmenter=new Intl.Segmenter(undefined,{granularity:'grapheme'}) } catch {}
let markPattern=/[\u0300-\u036f\u1ab0-\u1aff\u1dc0-\u1dff\u20d0-\u20ff\u3099-\u309a\ufe20-\ufe2f]/
try { markPattern=new RegExp('\\p{Mark}','u') } catch {}
export function splitReplyGraphemes(text, native=true) {
 if(native && graphemeSegmenter)return Array.from(graphemeSegmenter.segment(text),part=>part.segment)
 const result=[]
 for(const character of Array.from(text)){
  const previous=result[result.length-1],code=character.codePointAt(0)
  const regional=code>=0x1f1e6 && code<=0x1f1ff
  const previousRegional=previous && Array.from(previous).every(c=>c.codePointAt(0)>=0x1f1e6 && c.codePointAt(0)<=0x1f1ff)
  const join=previous && (markPattern.test(character) || /[\ufe00-\ufe0f\u200d]/.test(character) || previous.endsWith('\u200d') ||
   code>=0x1f3fb && code<=0x1f3ff || code>=0xe0020 && code<=0xe007f || code>=0xe0100 && code<=0xe01ef ||
   regional && previousRegional && Array.from(previous).length%2===1 || previous==='\r' && character==='\n')
  if(join)result[result.length-1]+=character
  else result.push(character)
 }
 return result
}
export function replyGlyphs(segments, start=0) {
 const result=[];let offset=start
 for(const segment of segments)for(const text of splitReplyGraphemes(segment.text)){
  result.push({...segment,text,start:offset,end:offset+text.length});offset+=text.length
 }
 return result
}

export function quoteLayout(blocks, active=false) {
 let text = '',region=0; const leaves = []
 const leaf = segments => {
  if (leaves.length) text += '\n\n'
  const value = { key: String(leaves.length), region, start: text.length, segments }
  if(active){let offset=value.start;value.groups=segments.map(segment=>{const glyphs=replyGlyphs([segment],offset).map(g=>({...g,region}));offset+=segment.text.length;const chunks=[];for(let i=0;i<glyphs.length;i+=48){const part=glyphs.slice(i,i+48);chunks.push({start:part[0].start,text:part.map(g=>g.text).join(""),glyphs:part})}return{...segment,glyphs,chunks}})}
  text += segments.map(s => s.text).join(''); leaves.push(value); return value
 }
 const mapped = blocks.map(block => {
  if (block.segments) return { ...block, leaf: leaf(block.segments) }
  if (block.type === 'code') return { ...block, leaf: leaf([{ text: block.text }]) }
  if (block.items) return { ...block, items: block.items.map(item => ({ ...item, leaf: leaf(item.segments) })) }
  if (block.rows) return { ...block, quoteFields: block.rows.map(row => row.map((segments,column) => ({header:block.headers[column]?.length?leaf(block.headers[column]):null,value:leaf(segments)}))) }
  region++; return block
 })
 return { blocks: mapped, text, leaves }
}

export function selectionHit(rects, point, nearest = false) {
 let best = null, distance = Infinity
 for (const rect of rects) {
  if (!(rect.width > 0 && rect.height > 0) || !rect.text?.trim()) continue
  const dx = Math.max(rect.left - point.x, 0, point.x - rect.right)
  const dy = Math.max(rect.top - point.y, 0, point.y - rect.bottom)
  if (!dx && !dy) return rect
  if (nearest && dx * dx + dy * dy < distance) { distance = dx * dx + dy * dy; best = rect }
 }
 return best
}

export function selectionPosition(rects, start, end, viewport) {
 const selected = rects.filter(r => r.start >= start && r.end <= end && r.width > 0)
 if (!selected.length) return null
 const topEdge=viewport.top??0,bottomEdge=viewport.bottom??viewport.height
 const visible=selected.filter(r=>r.bottom>=topEdge&&r.top<=bottomEdge)
 if(!visible.length)return null
 const inView=r=>r.bottom>=topEdge&&r.top<=bottomEdge
 const first = inView(selected[0])?selected[0]:null, last = inView(selected[selected.length-1])?selected[selected.length-1]:null
 const anchor=visible[visible.length-1]
 const left = Math.max(8, Math.min(anchor.right - 180, viewport.width - 210))
 const top = Math.max(topEdge+8, Math.min(anchor.bottom+14>bottomEdge-66?visible[0].top-58:anchor.bottom+14,bottomEdge-66))
 return { first, last, left, top }
}

export function replyQuote(message, text, threadId) {
 const id = Number(message.serverMessageId || message.id)
 return { source_thread_id: message.threadId || threadId,
  ...(Number.isSafeInteger(id) && id > 0 ? { source_message_id: id } : { source_request_id: message.requestId || message.id }), text }
}
