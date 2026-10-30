// A single owner of keyboard avoidance; never subtract from an already resized viewport.
export function chatAvailableHeight({baseline, windowHeight, keyboardHeight = 0}) {
  if (!(windowHeight > 0)) return 0
  if (!(keyboardHeight > 0)) return windowHeight
  return Math.max(1, Math.min(windowHeight, baseline - keyboardHeight))
}

export function createChatKeyboardLayout({platform, api, browser, onChange}) {
  let active = false, focused = false, keyboardHeight = 0, baseline = 0, width = 0, viewportHeight = 0
  let frozen = false, off = [], generation = 0, last = {height:0, offsetTop:0, keyboardOpen:false, homeHeight:0}
  function measure() {
    if (!active) return
    let height = 0, offsetTop = 0, currentWidth = 0, open = false
    if (platform === 'h5' && browser) {
      const viewport = browser.visualViewport
      currentWidth = browser.innerWidth
      const visible = viewport?.height || browser.innerHeight
      // Pinching should not be interpreted as a keyboard opening.
      if (viewport?.scale && Math.abs(viewport.scale - 1) > .05) return
      if (currentWidth !== width) { baseline = visible; width = currentWidth }
      if (!baseline || (!focused && !last.keyboardOpen)) baseline = visible
      baseline = Math.max(baseline, visible)
      open = (focused || last.keyboardOpen) && baseline - visible > 100
      if (!open && !focused) baseline = visible
      height = visible; offsetTop = viewport?.offsetTop || 0
    } else {
      const info = api?.getWindowInfo?.() || api?.getSystemInfoSync?.() || {}
      currentWidth = info.windowWidth || width
      const current = viewportHeight || info.windowHeight || baseline
      if (currentWidth !== width) { baseline = current; width = currentWidth }
      if (!baseline || (!focused && !keyboardHeight && !last.keyboardOpen)) baseline = current
      baseline = Math.max(baseline, current)
      open = keyboardHeight > 0
      height = chatAvailableHeight({baseline, windowHeight:current, keyboardHeight})
    }
    const homeHeight = frozen && last.homeHeight ? last.homeHeight : baseline
    last = {height, offsetTop, keyboardOpen:open, homeHeight}
    onChange(last)
  }
  function keyboard(event) {
    if (!active) return
    const height = Number(event?.detail?.height ?? event?.height)
    if (!Number.isFinite(height) || height < 0) return
    keyboardHeight = height
    // A resize callback may still describe the old keyboard-open window.
    // Re-read the actual window when the keyboard closes instead of pinning that stale size.
    if (!height) viewportHeight = 0
    measure()
  }
  function resize(event) { if (!active) return; viewportHeight = event?.size?.windowHeight || 0; measure() }
  function listen(target, name, callback) {
    target?.addEventListener?.(name, callback)
    off.push(() => target?.removeEventListener?.(name, callback))
  }
  return {
    start() {
      if (active) return
      active = true
      const ticket = ++generation
      const current = callback => event => { if (active && ticket === generation) callback(event) }
      if (platform === 'h5' && browser) {
        const update = current(measure)
        listen(browser, 'resize', update)
        listen(browser.visualViewport, 'resize', update)
        listen(browser.visualViewport, 'scroll', update)
      } else {
        const onKeyboard = current(keyboard), onResize = current(resize)
        api?.onKeyboardHeightChange?.(onKeyboard); api?.onWindowResize?.(onResize)
        off.push(() => api?.offKeyboardHeightChange?.(onKeyboard), () => api?.offWindowResize?.(onResize))
      }
      measure()
    },
    focus(value) { focused = value; if (value) frozen = true; measure() },
    freeze(value) { frozen = value; measure() },
    keyboard,
    stop() {
      active = false; generation++; off.splice(0).forEach(remove => remove())
      focused = false; keyboardHeight = 0; viewportHeight = 0
      last = {...last, height:0, offsetTop:0, keyboardOpen:false}
      onChange(last)
    },
  }
}
