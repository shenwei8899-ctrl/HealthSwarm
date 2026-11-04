import test from 'node:test'
import assert from 'node:assert/strict'
import { uploadVoice } from '../src/services/voice-upload.js'
import { getSession, setSession } from '../src/services/session.js'
import { createVoiceCapture } from '../src/services/chat-voice.js'

const audio = { filePath: '/saved.pcm', clientRequestId: 'voice-request-1', format: 'PCM', sampleRate: 16000, numberOfChannels: 1 }
const tick = () => new Promise(resolve => setImmediate(resolve))
function setup() {
  const memory = new Map(), calls = []; let aborted = 0
  globalThis.window = {}
  globalThis.uni = {
    getStorageSync: key => memory.get(key), setStorageSync: (key, value) => memory.set(key, value),
    uploadFile: options => { calls.push(options); return { abort: () => { aborted++; options.fail() } } },
  }
  setSession({ accountId: 'voice-user', householdId: 'family', token: 'synthetic-token' })
  return { calls, aborted: () => aborted }
}
test('voice upload carries bytes, identity and stable request key then validates text receipt', async () => {
  const fixture = setup(), pending = uploadVoice(audio), request = fixture.calls[0]
  assert.equal(request.url, '/api/health/v1/voice/transcriptions')
  assert.equal(request.filePath, '/saved.pcm')
  assert.equal(request.header.Authorization, 'Bearer synthetic-token')
  assert.equal(request.header['Idempotency-Key'], audio.clientRequestId)
  assert.deepEqual(request.formData, { client_request_id: audio.clientRequestId, format: 'PCM', sample_rate: 16000, channels: 1 })
  request.success({ statusCode: 200, data: JSON.stringify({ text: ' 今天吃什么 ', client_request_id: audio.clientRequestId }) })
  assert.deepEqual(await pending, { text: '今天吃什么' })
})
test('cancellation aborts upload and ignores a late success', async () => {
  const fixture = setup(); let cancel
  const pending = uploadVoice({ ...audio, onCancelReady: value => { cancel = value } })
  cancel()
  fixture.calls[0].success({ statusCode: 200, data: { text: '迟到', client_request_id: audio.clientRequestId } })
  await assert.rejects(pending, { code: 'VOICE_CANCELLED' })
  assert.equal(fixture.aborted(), 1)
})
test('previous account 401 cannot clear a new session', async () => {
  const fixture = setup(), pending = uploadVoice(audio)
  setSession({ accountId: 'new-user', householdId: 'family', token: 'new-token' })
  fixture.calls[0].success({ statusCode: 401, data: {} })
  await assert.rejects(pending, /账号已切换/)
  assert.equal(getSession().token, 'new-token')
})
test('unconfigured provider, malformed and mismatched receipts never emit text', async () => {
  for (const response of [
    { statusCode: 503, data: { detail: { code: 'VOICE_NOT_READY', message: '尚未配置' } } },
    { statusCode: 200, data: 'invalid' },
    { statusCode: 200, data: { text: '其他录音', client_request_id: 'other' } },
    { statusCode: 200, data: { text: ' ', client_request_id: audio.clientRequestId } },
  ]) {
    const fixture = setup(), pending = uploadVoice(audio)
    fixture.calls[0].success(response)
    await assert.rejects(pending)
  }
})
test('missing authentication and production endpoint reject without uploading', async () => {
  const fixture = setup()
  setSession({ accountId: 'voice-user', householdId: 'family' })
  await assert.rejects(uploadVoice(audio), /请先登录/)
  delete globalThis.window
  await assert.rejects(uploadVoice(audio), /尚未配置/)
  assert.equal(fixture.calls.length, 0)
})

for (const scenario of ['expired', 'switched']) test('capture releases busy state and saved audio when session is ' + scenario, async () => {
  const fixture = setup(), events = {}, states = [], discarded = [], texts = []
  const native = { start() {}, stop() {} }
  for (const name of ['Start', 'Stop', 'Error', 'FrameRecorded', 'InterruptionBegin', 'Pause']) native['on' + name] = fn => { events[name] = fn }
  const capture = createVoiceCapture({
    getRecorder: () => native, authorize: async () => {},
    save: async recording => ({ ...recording, filePath: '/saved.pcm' }),
    transcribe: recording => uploadVoice({ ...audio, clientRequestId: recording.id, onCancelReady: recording.onCancelReady }).then(result => result.text),
    discard: recording => { if (recording?.filePath) discarded.push(recording.filePath) },
    onState: state => states.push(state), onText: text => texts.push(text),
  })
  try {
    await capture.begin(200); events.Start(); capture.end(200)
    events.Stop({ duration: 1000, tempFilePath: '/temp.pcm' }); await tick()
    assert.equal(states.at(-1).phase, 'transcribing')
    if (scenario === 'switched') setSession({ accountId: 'new-user', householdId: 'family', token: 'new-token' })
    const request = fixture.calls[0]
    request.success(scenario === 'expired'
      ? { statusCode: 401, data: { detail: 'Session expired' } }
      : { statusCode: 200, data: { text: '旧账号内容', client_request_id: request.formData.client_request_id } })
    await tick()
    assert.equal(states.at(-1).phase, 'error')
    assert.match(states.at(-1).error, /重新登录/)
    assert.equal(states.at(-1).hasAudio, false)
    assert.deepEqual(discarded, ['/saved.pcm'])
    assert.deepEqual(texts, [])
    assert.equal(getSession()?.token || null, scenario === 'expired' ? null : 'new-token')
  } finally { capture.dispose() }
})
