import { callApiAdapter } from './index.js'
import { storageContext } from './storage.js'

export const VOICE_OPTIONS = Object.freeze({ duration: 60000, sampleRate: 16000, numberOfChannels: 1, format: 'PCM', frameSize: 4 })

// Recorder frames are signed 16-bit little-endian PCM, never compressed MP3 bytes.
export function pcmVoiceLevel(buffer) {
  if (!buffer || buffer.byteLength < 2) return 0
  const view = new DataView(buffer)
  let sum = 0
  const count = Math.floor(view.byteLength / 2)
  for (let i = 0; i < count; i++) { const sample = view.getInt16(i * 2, true) / 32768; sum += sample * sample }
  const rms = Math.sqrt(sum / count)
  if (rms < 0.001) return 0
  return Math.max(0, Math.min(1, (20 * Math.log10(rms) + 55) / 43))
}

export async function authorizeVoice() {
  const denied = () => Object.assign(new Error('麦克风权限已被拒绝，请在设置中开启'), { code: 'RECORD_PERMISSION_DENIED' })
  const failure = (prefix, cause) => Object.assign(new Error(prefix + (cause?.errMsg ? '：' + cause.errMsg : '，请稍后重试')), { code: 'RECORD_AUTH_FAILED', cause })
  const readSettings = () => new Promise((resolve, reject) => {
    uni.getSetting({ success: result => resolve(result.authSetting || {}), fail: error => reject(failure('读取麦克风授权状态失败', error)) })
  })
  const settings = await readSettings()
  if (settings['scope.record'] === true) return
  if (settings['scope.record'] === false) throw denied()
  // Only WeChat can render the native Allow / Deny authorization dialog.
  try {
    await new Promise((resolve, reject) => {
      uni.authorize({ scope: 'scope.record', success: resolve, fail: reject })
    })
  } catch (error) {
    // Confirm the resulting permission state instead of treating every API
    // failure (privacy/configuration/runtime included) as a user denial.
    try {
      const current = await readSettings()
      if (current['scope.record'] === false) throw denied()
    } catch (settingsError) {
      if (settingsError.code === 'RECORD_PERMISSION_DENIED') throw settingsError
    }
    throw failure('微信麦克风授权未完成', error)
  }
}

export function saveVoiceFile(audio) {
  return new Promise((resolve, reject) => {
    uni.saveFile({ tempFilePath: audio.tempFilePath,
      success: result => result.savedFilePath ? resolve({ ...audio, filePath: result.savedFilePath }) : reject(new Error('录音保存失败，请重试')),
      fail: () => reject(new Error('录音保存失败，请检查存储空间后重试')),
    })
  })
}

export async function transcribeVoice(audio) {
  try {
    const result = await callApiAdapter('transcribeVoice', {
      filePath: audio.filePath, format: 'PCM', sampleRate: 16000, numberOfChannels: 1,
      duration: audio.duration, clientRequestId: audio.id,
    })
    if (typeof result?.text !== 'string' || !result.text.trim()) throw new Error('没有识别到内容，请重新录音')
    return result.text.trim()
  } catch (error) {
    if (error.code === 'ADAPTER_NOT_READY') throw Object.assign(new Error('语音识别服务暂不可用，录音已保留，可重试'), { code: 'VOICE_NOT_READY' })
    throw error
  }
}

// WeChat exposes a singleton recorder. Attach its listeners once and route events
// to its owner, including a late onStart after the page has been disposed.
const recorders = new WeakMap()
function recorderSlot(manager) {
  if (!recorders.has(manager)) {
    const slot = { owner: null }
    for (const name of ['Start', 'Stop', 'Error', 'FrameRecorded', 'InterruptionBegin', 'Pause']) {
      manager['on' + name]?.(event => slot.owner?.[name]?.(event))
    }
    recorders.set(manager, slot)
  }
  return recorders.get(manager)
}

export function createVoiceCapture({ getRecorder = () => uni.getRecorderManager(), authorize = authorizeVoice,
  save = saveVoiceFile, transcribe = transcribeVoice, getScope = storageContext,
  onState = () => {}, onLevel = () => {}, onText = () => {}, now = Date.now } = {}) {
  let phase = 'idle', error = '', permissionDenied = false, holding = false, canceling = false
  let alive = true, version = 0, scope, startY = 0, startedAt = 0, started = false, stopping = false
  let audio = null, manager, slot, owner
  const emit = () => { if (alive) onState({ phase, error, permissionDenied, canceling, hasAudio: Boolean(audio) }) }
  const valid = ticket => alive && ticket === version && scope === getScope()
  const releaseSlot = () => { if (slot?.owner === owner) slot.owner = null; started = false; stopping = false }
  function fail(message, denied = false) { phase = 'error'; error = message; permissionDenied = denied; emit() }
  function stopNative() {
    if (started && !stopping) { stopping = true; phase = 'stopping'; emit(); manager.stop() }
  }
  async function recognize(ticket) {
    if (!valid(ticket) || !audio) return
    phase = 'transcribing'; error = ''; emit()
    try {
      if (!audio.filePath) {
        const saved = await save(audio)
        if (!valid(ticket)) return
        audio = saved
      }
      const text = await transcribe(audio)
      if (!valid(ticket)) return
      audio = null; phase = 'idle'; emit(); onText(text)
    } catch (e) { if (valid(ticket)) fail(e.message || '语音识别失败，录音已保留，可重试') }
  }
  async function begin(y = 0) {
    if (!alive || holding || (owner && slot?.owner === owner) || ['authorizing', 'starting', 'recording', 'stopping', 'transcribing'].includes(phase)) return
    const ticket = ++version; scope = getScope(); holding = true; canceling = false; startY = y
    let claimed = false
    audio = null; error = ''; permissionDenied = false; phase = 'authorizing'; emit()
    try {
      manager = getRecorder()
      if (!manager) throw new Error('请在微信小程序中使用语音输入')
      slot = recorderSlot(manager)
      if (slot.owner) throw new Error('麦克风正在使用，请稍后再试')
      await authorize()
      if (!valid(ticket) || !holding) { if (valid(ticket)) { phase = 'idle'; emit() }; return }
      if (slot.owner) throw new Error('麦克风正在使用，请稍后再试')
      owner = {
        Start() {
          started = true; startedAt = now()
          if (!valid(ticket) || !holding || canceling) { stopNative(); return }
          phase = 'recording'; emit()
        },
        FrameRecorded(event) { if (valid(ticket) && phase === 'recording') onLevel(pcmVoiceLevel(event?.frameBuffer)) },
        Stop(result = {}) {
          releaseSlot(); holding = false
          if (!valid(ticket)) {
            if (alive && phase === 'stopping') { phase = 'idle'; canceling = false; emit() }
            return
          }
          if (canceling) { phase = 'idle'; canceling = false; emit(); return }
          const duration = Number(result.duration) || Math.max(0, now() - startedAt)
          if (duration < 500 || !result.tempFilePath) { fail('说话时间太短，请按住再说一次'); return }
          audio = { id: 'voice-' + now() + '-' + Math.random().toString(36).slice(2), tempFilePath: result.tempFilePath, duration }
          recognize(ticket)
        },
        Error() {
          releaseSlot(); holding = false
          if (valid(ticket)) fail('录音失败，请检查麦克风权限后重试')
          else if (alive && phase === 'stopping') { phase = 'idle'; canceling = false; emit() }
        },
        InterruptionBegin() { cancel(); if (alive) fail('录音已中断，请重新按住说话') },
        Pause() { cancel(); if (alive) fail('录音已中断，请重新按住说话') },
      }
      slot.owner = owner; claimed = true; phase = 'starting'; emit()
      manager.start(VOICE_OPTIONS)
    } catch (e) {
      if (claimed && slot?.owner === owner) releaseSlot()
      holding = false
      if (valid(ticket)) fail(e.message || '录音启动失败，请重试', e.code === 'RECORD_PERMISSION_DENIED')
    }
  }
  function move(y) {
    if (!holding) return
    canceling = startY - y >= 80; emit()
  }
  function end(y) {
    if (!holding) return
    if (typeof y === 'number') move(y)
    holding = false
    if (phase === 'authorizing') { version++; phase = 'idle'; canceling = false; emit(); return }
    stopNative() // If start is still pending, the Start callback stops it.
  }
  function cancel() {
    if (!alive) return
    holding = false; canceling = true; version++
    if (owner && slot?.owner === owner) { stopNative(); phase = 'stopping' }
    else { phase = 'idle'; canceling = false }
    audio = null; error = ''; emit()
  }
  function retry() { if (phase === 'error' && audio && scope === getScope()) return recognize(version) }
  function dispose() { cancel(); alive = false }
  return { begin, move, end, cancel, retry, dispose }
}
