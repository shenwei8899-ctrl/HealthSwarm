// Presentation only: no session creation, network calls or draft ownership.
export const CHAT_ENTRY_DURATION = 260

export function canRestoreChatHome(context) {
  return context.eligible && !context.hasMessages && !context.hasDraft &&
    !context.blocked && !context.busy && !context.focused && !context.keyboardOpen &&
    !context.voiceMode && !context.intent
}

export function createChatEntryTransition({read, onChange, schedule = setTimeout, cancel = clearTimeout, duration = CHAT_ENTRY_DURATION}) {
  let phase = 'home', engaged = false, timer, generation = 0, paused = false
  const publish = () => onChange({phase, engaged, generation})
  function invalidate() { generation++; cancel(timer); timer = undefined }
  function settle() {
    phase = read().hasMessages ? 'conversation' : 'composing'
    publish()
  }
  function finish(ticket = generation) {
    if (paused || ticket !== generation || phase !== 'leaving') return
    invalidate(); settle(); reconcile()
  }
  function enter() {
    if (paused) return
    const context = read()
    engaged = true
    if (phase === 'home' && context.eligible && !context.blocked) {
      invalidate(); phase = 'leaving'; publish()
      const ticket = generation
      timer = schedule(() => finish(ticket), duration + 80)
    } else if (phase !== 'leaving') settle()
  }
  function reconcile() {
    if (paused) return
    const context = read()
    // Recovery/consent panels take precedence; loading alone must not cut a fade short.
    if (phase === 'leaving') {
      if (context.blocked) { invalidate(); settle() }
      return
    }
    if (context.hasMessages) phase = 'conversation'
    else if (canRestoreChatHome(context)) { phase = 'home'; engaged = false }
    else if (phase !== 'home' || !context.eligible || context.hasDraft || context.focused || context.voiceMode) phase = 'composing'
    publish()
  }
  return {
    enter, reconcile, finish,
    reset() { invalidate(); phase = 'home'; engaged = false; publish() },
    pause() { invalidate(); paused = true; if (phase === 'leaving') settle() },
    resume() { paused = false; reconcile() },
    dispose() { invalidate(); paused = true },
  }
}
