const { voiceFeatures, decodeVoice } = require('./paraformer.js')

let config, vocab
worker.onMessage(({ id, operation, input }) => {
  try {
    let result
    if (operation === 'init') {
      config = input.config
      vocab = input.vocab
    } else if (operation === 'features') {
      result = voiceFeatures(input, config)
    } else if (operation === 'decode') {
      result = decodeVoice(input, vocab)
    } else {
      throw new Error('VOICE_WORKER_FAILED')
    }
    worker.postMessage({ id, result })
  } catch (error) {
    worker.postMessage({ id, error: error.message })
  }
})
