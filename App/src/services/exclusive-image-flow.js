// 页面只轮询当前一天；后台任务由服务端持久保存。
export function createExclusiveImageFlow({send, scope, apply, status, schedule = setTimeout, cancel = clearTimeout}) {
  let generation = 0, timer = null, current = null, registration = null
  function stop() {
    generation++
    if (timer !== null) cancel(timer)
    timer = null
  }
  async function open(selection, {retry = false, start = true} = {}) {
    stop()
    current = selection
    const ticket = generation, identity = scope()
    const active = () => ticket === generation && identity === scope()
    async function read() {
      try {
        const result = await send(selection.groupId, selection.tier, selection.dayNo)
        if (!active()) return
        apply(result.images || [])
        status(result.status)
        if (['pending', 'running'].includes(result.status)) timer = schedule(read, 5000)
      } catch (error) {
        if (active()) status('unavailable', error)
      }
    }
    try {
      if (start) registration = {identity,groupId:selection.groupId,promise:send(selection.groupId, selection.tier, selection.dayNo, {start:true, retry})}
      if (registration?.identity===identity && registration.groupId===selection.groupId) await registration.promise
      if (active()) await read()
    } catch (error) {
      if (active()) status('unavailable', error)
    }
  }
  return {open, stop, retry: () => current && open(current, {retry:true})}
}
