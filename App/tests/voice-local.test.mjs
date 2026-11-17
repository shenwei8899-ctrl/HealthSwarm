import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInThisContext } from 'node:vm'
import test from 'node:test'
import { createLocalVoiceTranscriber } from '../src/services/voice-local.js'

const loadWorker = (file, globals) => runInThisContext(
  '(function(module, require, worker) {' +
  readFileSync(new URL('../src/static/voice-workers/' + file, import.meta.url), 'utf8') +
  '\n})',
)(globals.module, globals.require, globals.worker)
const math = { exports: {} }
loadWorker('paraformer.js', { module: math })
const audio = { format: 'PCM', sampleRate: 16000, numberOfChannels: 1, filePath: 'recording' }
const config = { neg_mean: Array(560).fill(0), inv_stddev: Array(560).fill(1) }
const vocab = ['<blank>', '<s>', '</s>', '你', '好', ...Array.from({ length: 8354 }, (_, i) => 't' + i)]
const modelFiles = {
  'model_int8.onnx': [81828675, '3ef6c19369b912f7caf3cef8e545c5ccd1a33d9d7ec792a46668dc41c4b229ec'],
  'config.json': [23381, '467031d9cdc3296a4b2bf84f11110cd505081ffa4417facaaff1e9b95194131b', JSON.stringify(config)],
  'vocab.txt': [75352, '4b2d964e18b9cf139b473003b6698fb2ed9a2a5ec55b93daa677b28f578897aa', vocab.map((token, id) => token + ' ' + id).join('\n')],
}

function setup() {
  const pcm = Int16Array.from({ length: 16000 }, (_, i) => 2000 * Math.sin(i * 0.2)).buffer
  const files = new Map([['recording', { data: pcm }]])
  const calls = { downloads: [], sessions: 0, terminated: 0, destroyed: 0, corrupt: false }
  const fs = {
    getFileInfo({ filePath, digestAlgorithm, success, fail }) {
      assert.equal(digestAlgorithm, 'sha256')
      if (files.has(filePath)) success(files.get(filePath))
      else fail()
    },
    readFile({ filePath, success, fail }) {
      const file = files.get(filePath)
      if (file) success({ data: file.data })
      else fail()
    },
    rename({ oldPath, newPath, success }) {
      files.set(newPath, files.get(oldPath))
      files.delete(oldPath)
      success()
    },
    unlink({ filePath, success }) { files.delete(filePath); success() },
  }
  const platform = {
    env: { USER_DATA_PATH: 'user' },
    getFileSystemManager: () => fs,
    downloadFile(options) {
      const name = options.url.split('/').at(-1)
      const [size, digest, data] = modelFiles[name]
      calls.downloads.push(name)
      assert.deepEqual(Object.keys(options).sort(), ['fail', 'filePath', 'success', 'timeout', 'url'])
      files.set(options.filePath, { size, digest: calls.corrupt ? 'invalid' : digest, data })
      options.success({ statusCode: 200 })
    },
    createWorker(path) {
      assert.equal(path, 'static/voice-workers/index.js')
      const manifest = JSON.parse(readFileSync(new URL('../src/manifest.json', import.meta.url), 'utf8'))
      assert.ok(path.startsWith(manifest['mp-weixin'].workers + '/'), 'WeChat worker must be in its declared directory')
      let main, background
      loadWorker('index.js', {
        require: () => math.exports,
        worker: {
          onMessage(fn) { background = fn },
          postMessage(message) { queueMicrotask(() => main(message)) },
        },
      })
      return {
        onMessage(fn) { main = fn },
        postMessage(message) { queueMicrotask(() => background(message)) },
        terminate() { calls.terminated++ },
      }
    },
    createInferenceSession({ model }) {
      assert.ok(files.has(model))
      calls.sessions++
      return {
        onError() {},
        onLoad(fn) { queueMicrotask(fn) },
        destroy() { calls.destroyed++ },
        async run({ speech, speech_lengths }) {
          assert.equal(speech_lengths.type, 'int32')
          assert.deepEqual(speech.shape, [1, 17, 560])
          assert.equal(new Int32Array(speech_lengths.data)[0], 17)
          if (calls.pending) await calls.pending()
          const data = new Float32Array(vocab.length * 3)
          data[3] = 1
          data[vocab.length + 4] = 1
          data[vocab.length * 2 + 2] = 1
          return { logits: { shape: [1, 3, vocab.length], type: 'float32', data: data.buffer },
            token_num: { type: 'int32', data: Int32Array.of(3).buffer } }
        },
      }
    },
  }
  return { calls, files, transcriber: () => createLocalVoiceTranscriber({ getPlatform: () => platform, modelBase: 'https://model.example.test/paraformer' }) }
}

test('voice downloads only fixed model assets, verifies them, and transcribes again from cache after restart', async () => {
  const { calls, transcriber } = setup()
  const transcribe = transcriber()
  const progress = []
  assert.deepEqual(await transcribe({ ...audio, onModelDownload: value => progress.push(value) }), { text: '你好' })
  assert.deepEqual(progress, [true, true, true, false])
  assert.deepEqual(await transcribe(audio), { text: '你好' })
  assert.equal(calls.sessions, 1)
  assert.deepEqual(await transcriber()(audio), { text: '你好' })
  assert.deepEqual(calls.downloads, ['config.json', 'vocab.txt', 'model_int8.onnx'])
  assert.equal(calls.terminated, 3)
})

test('invalid downloads never become model cache entries; retry can download again', async () => {
  const { calls, files, transcriber } = setup()
  const transcribe = transcriber()
  calls.corrupt = true
  await assert.rejects(transcribe(audio), { code: 'VOICE_BAD_MODEL' })
  assert.deepEqual([...files.keys()], ['recording'])
  assert.equal(calls.sessions, 0)
  calls.corrupt = false
  assert.deepEqual(await transcribe(audio), { text: '你好' })
})

test('cancelling inference destroys its session and a late result is ignored', async () => {
  const { calls, transcriber } = setup()
  let started, resolveRun, cancel
  const running = new Promise(resolve => { started = resolve })
  calls.pending = () => new Promise(resolve => { resolveRun = resolve; started() })
  const transcribe = transcriber()
  const result = transcribe({ ...audio, onCancelReady: value => { cancel = value } })
  await running
  await assert.rejects(transcribe(audio), { code: 'VOICE_BUSY' })
  cancel()
  await assert.rejects(result, { code: 'VOICE_CANCELLED' })
  assert.equal(calls.destroyed, 1)
  calls.pending = null
  resolveRun()
  assert.deepEqual(await transcribe(audio), { text: '你好' })
  assert.equal(calls.sessions, 2)
})

test('rejects unsupported devices and silent PCM without an inference session', async () => {
  const unsupported = createLocalVoiceTranscriber({ getPlatform: () => ({}) })
  await assert.rejects(unsupported(audio), { code: 'VOICE_UNSUPPORTED' })
  const { calls, files, transcriber } = setup()
  files.set('recording', { data: new ArrayBuffer(32000) })
  await assert.rejects(transcriber()(audio), { code: 'VOICE_NO_SPEECH' })
  assert.equal(calls.sessions, 0)
})
