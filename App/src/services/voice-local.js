const MODEL_REVISION = 'e580070c6a895c525dd463f3ff6a35409a3bfbe2'
const MODEL_FILES = {
  'model_int8.onnx': [81828675, '3ef6c19369b912f7caf3cef8e545c5ccd1a33d9d7ec792a46668dc41c4b229ec'],
  'config.json': [23381, '467031d9cdc3296a4b2bf84f11110cd505081ffa4417facaaff1e9b95194131b'],
  'vocab.txt': [75352, '4b2d964e18b9cf139b473003b6698fb2ed9a2a5ec55b93daa677b28f578897aa'],
}
const DEFAULT_MODEL_BASE = 'https://hf-mirror.com/OpenVoiceOS/paraformer-zh-small-onnx/resolve/' + MODEL_REVISION
const messages = {
  VOICE_UNSUPPORTED: '当前微信或设备暂不支持本地语音识别，请使用键盘输入',
  VOICE_MODEL_DOWNLOAD: '语音模型下载失败，请联网后重试识别',
  VOICE_MODEL_LOAD: '本地语音模型无法加载，请重试或使用键盘输入',
  VOICE_WORKER_FAILED: '本地语音处理失败，请重试识别',
  VOICE_BAD_MODEL: '本地语音模型验证失败，请重试识别',
  VOICE_BAD_AUDIO: '录音无法读取，请重新录音',
  VOICE_NO_SPEECH: '没有识别到内容，请重新录音',
  VOICE_CANCELLED: '已取消语音识别',
  VOICE_BUSY: '本地语音识别正在进行，请稍后重试',
}

function voiceError(code) {
  return Object.assign(new Error(messages[code] || messages.VOICE_WORKER_FAILED), { code })
}

function invoke(target, method, options) {
  return new Promise((resolve, reject) => {
    target[method]({ ...options, success: resolve, fail: reject })
  })
}

function openSession(platform, model) {
  return new Promise((resolve, reject) => {
    const session = platform.createInferenceSession({ model, precisionLevel: 4, allowNPU: false, allowQuantize: false })
    let settled = false
    const finish = error => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      session.offLoad?.(loaded)
      session.offError?.(failed)
      if (error) {
        session.destroy?.()
        reject(error)
      } else resolve(session)
    }
    const loaded = () => finish()
    const failed = () => finish(voiceError('VOICE_MODEL_LOAD'))
    const timer = setTimeout(failed, 30000)
    session.onError(failed)
    session.onLoad(loaded)
  })
}

function createProcessor(platform) {
  let worker, current, id = 0
  const lost = () => current?.finish(voiceError('VOICE_WORKER_FAILED'))
  try {
    worker = platform.createWorker('static/voice-workers/index.js')
    worker.onMessage(message => {
      if (current?.id !== message.id) return
      current.finish(message.error ? voiceError(message.error) : null, message.result)
    })
    worker.onError?.(lost)
    worker.onProcessKilled?.(lost)
  } catch {
    worker?.terminate()
    throw voiceError('VOICE_WORKER_FAILED')
  }

  return {
    request(operation, input) {
      return new Promise((resolve, reject) => {
        const finish = (error, result) => {
          clearTimeout(timer)
          current = null
          if (error) reject(error)
          else resolve(result)
        }
        const timer = setTimeout(lost, 30000)
        current = { id: ++id, finish }
        try { worker.postMessage({ id, operation, input }) }
        catch { lost() }
      })
    },
    close() {
      current?.finish(voiceError('VOICE_CANCELLED'))
      worker.terminate()
    },
  }
}

export function createLocalVoiceTranscriber({
  getPlatform = () => wx,
  modelBase = import.meta.env?.VITE_VOICE_MODEL_BASE_URL || DEFAULT_MODEL_BASE,
} = {}) {
  let modelFlight, sessionFlight, assetFlight, active

  async function verify(fs, filePath, [expectedSize, sha256]) {
    try {
      const { size, digest } = await invoke(fs, 'getFileInfo', { filePath, digestAlgorithm: 'sha256' })
      return size === expectedSize && typeof digest === 'string' && digest.toLowerCase() === sha256
    } catch {
      return false
    }
  }

  async function prepareFile(platform, fs, filename, onProgress) {
    const signature = MODEL_FILES[filename]
    const path = platform.env.USER_DATA_PATH + '/paraformer-' + MODEL_REVISION + '-' + filename
    if (await verify(fs, path, signature)) return path
    if (!/^https:\/\/[^\s?#]+$/i.test(modelBase)) throw voiceError('VOICE_MODEL_DOWNLOAD')
    onProgress?.(true)
    const staging = path + '.pending'
    try {
      const response = await invoke(platform, 'downloadFile', {
        url: modelBase.replace(/\/+$/, '') + '/' + filename,
        filePath: staging,
        timeout: 120000,
      }).catch(() => { throw voiceError('VOICE_MODEL_DOWNLOAD') })
      if (response.statusCode !== 200) throw voiceError('VOICE_MODEL_DOWNLOAD')
      if (!await verify(fs, staging, signature)) throw voiceError('VOICE_BAD_MODEL')
      // Keep the valid cache path separate from incomplete downloads.
      await invoke(fs, 'unlink', { filePath: path }).catch(() => {})
      await invoke(fs, 'rename', { oldPath: staging, newPath: path }).catch(() => {
        throw voiceError('VOICE_MODEL_DOWNLOAD')
      })
      return path
    } finally {
      await invoke(fs, 'unlink', { filePath: staging }).catch(() => {})
    }
  }

  async function loadAssets(platform, fs, onProgress) {
    const read = async filename => invoke(fs, 'readFile', {
      filePath: await prepareFile(platform, fs, filename, onProgress),
      encoding: 'utf8',
    })
    const configFile = await read('config.json')
    const vocabFile = await read('vocab.txt')
    const config = JSON.parse(configFile.data)
    const vocab = []
    for (const line of vocabFile.data.trim().split(/\r?\n/)) {
      const match = /^(\S+)\s+(\d+)$/.exec(line)
      if (!match || vocab[Number(match[2])] !== undefined) throw voiceError('VOICE_BAD_MODEL')
      vocab[Number(match[2])] = match[1]
    }
    if (vocab.length !== 8359 || Object.keys(vocab).length !== 8359 || vocab[2] !== '</s>' ||
        config.neg_mean?.length !== 560 || config.inv_stddev?.length !== 560) throw voiceError('VOICE_BAD_MODEL')
    return { config, vocab }
  }

  return async function transcribeLocal(audio) {
    const platform = getPlatform()
    if (!platform?.createInferenceSession || !platform?.createWorker || !platform?.getFileSystemManager ||
        !platform?.env?.USER_DATA_PATH) throw voiceError('VOICE_UNSUPPORTED')
    if (audio.format !== 'PCM' || audio.sampleRate !== 16000 || audio.numberOfChannels !== 1 || !audio.filePath) {
      throw voiceError('VOICE_BAD_AUDIO')
    }
    if (active) throw voiceError('VOICE_BUSY')
    const job = {}
    active = job
    let processor, runningSession, timer, rejectCancel
    const onDownload = downloading => {
      if (active === job) audio.onModelDownload?.(downloading)
    }
    const cancelled = new Promise((_, reject) => { rejectCancel = reject })
    const cancel = (error = voiceError('VOICE_CANCELLED')) => {
      if (active !== job) return
      active = null
      if (runningSession) {
        sessionFlight = null
        runningSession.destroy?.()
      }
      rejectCancel(error)
    }
    const checkActive = () => {
      if (active !== job) throw voiceError('VOICE_CANCELLED')
    }

    async function recognize() {
      checkActive()
      const fs = platform.getFileSystemManager()
      if (!fs?.getFileInfo) throw voiceError('VOICE_UNSUPPORTED')
      const pcm = await invoke(fs, 'readFile', { filePath: audio.filePath }).catch(() => { throw voiceError('VOICE_BAD_AUDIO') })
      checkActive()
      const assets = await (assetFlight ||= loadAssets(platform, fs, onDownload).catch(error => {
        assetFlight = null
        throw error.code ? error : voiceError('VOICE_BAD_MODEL')
      }))
      checkActive()
      processor = createProcessor(platform)
      await processor.request('init', assets)
      checkActive()
      const features = await processor.request('features', pcm.data)
      checkActive()

      const model = await (modelFlight ||= prepareFile(platform, fs, 'model_int8.onnx', onDownload).catch(error => {
        modelFlight = null
        throw error
      }))
      checkActive()
      onDownload(false)
      const session = await (sessionFlight ||= openSession(platform, model).catch(() => {
        sessionFlight = null
        throw voiceError('VOICE_MODEL_LOAD')
      }))
      checkActive()
      runningSession = session
      let output
      try {
        output = await session.run({
          speech: { type: 'float32', ...features },
          speech_lengths: { type: 'int32', data: Int32Array.of(features.shape[1]).buffer, shape: [1] },
        })
      } catch {
        if (active === job) {
          sessionFlight = null
          session.destroy?.()
        }
        throw voiceError('VOICE_MODEL_LOAD')
      } finally {
        runningSession = null
      }
      checkActive()
      const text = await processor.request('decode', { logits: output.logits, token_num: output.token_num })
      if (!text?.trim()) throw voiceError('VOICE_NO_SPEECH')
      return { text }
    }

    try {
      // Register the race before the caller can immediately cancel a stale request.
      const result = Promise.race([cancelled, Promise.resolve().then(recognize)])
      audio.onCancelReady?.(() => cancel())
      timer = setTimeout(() => cancel(voiceError('VOICE_WORKER_FAILED')), 240000)
      return await result
    } finally {
      clearTimeout(timer)
      processor?.close()
      if (active === job) active = null
    }
  }
}

export const transcribeLocalVoice = createLocalVoiceTranscriber()
