import { splitReplyGraphemes } from '../utils/reply-selection.js'

// Smooth only public, server-approved deltas. The authoritative final answer
// always replaces this preview immediately; presentation never delays completion.
export function createStreamTextPresentation({ onChange, schedule = fn => setTimeout(fn, 40),
  cancel = handle => clearTimeout(handle) }) {
  let target = '', shown = '', timer = null, frames = 0, generation = 0, disposed = false
  function stop() {
    generation++
    if (timer !== null) cancel(timer)
    timer = null; frames = 0
  }
  function publish(text) {
    if (shown === text) return
    shown = text; onChange(text)
  }
  function enqueue() {
    if (timer !== null || shown === target || disposed) return
    const mine = generation
    timer = schedule(() => {
      if (disposed || mine !== generation) return
      timer = null
      const remaining = splitReplyGraphemes(target.slice(shown.length))
      // Catch up within six frames, including large buffered chunks. Further
      // arrivals share that deadline instead of restarting a slow typewriter.
      const count = Math.max(4, Math.ceil(remaining.length / Math.max(1, frames)))
      frames--
      publish(shown + remaining.slice(0, count).join(''))
      enqueue()
    })
  }
  return {
    update(text, streaming = true) {
      if (disposed) return
      text = String(text || '')
      if (!streaming || !text) { stop(); target = text; publish(text); return }
      if (!text.startsWith(target)) { stop(); publish('') }
      target = text
      if (shown === target) return
      if (timer === null) frames = 6
      enqueue()
    },
    dispose() { stop(); disposed = true; target = ''; shown = '' },
  }
}
