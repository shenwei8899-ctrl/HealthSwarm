const RATE = 16000
const FRAME = 400
const SHIFT = 160
const FFT = 512
const BINS = 80
const STACK = 7
const HOP = 6
const DIM = BINS * STACK

const window = Float32Array.from({ length: FRAME }, (_, i) => 0.54 - 0.46 * Math.cos(2 * Math.PI * i / (FRAME - 1)))
const cos = Float32Array.from({ length: FFT / 2 }, (_, i) => Math.cos(2 * Math.PI * i / FFT))
const sin = Float32Array.from({ length: FFT / 2 }, (_, i) => -Math.sin(2 * Math.PI * i / FFT))
const reverse = Uint16Array.from({ length: FFT }, (_, value) => {
  let result = 0
  for (let bit = 1; bit < FFT; bit *= 2) {
    result = result * 2 + (value & 1)
    value >>= 1
  }
  return result
})

const mel = hz => 1127 * Math.log1p(hz / 700)
const low = mel(20)
const step = (mel(RATE / 2) - low) / (BINS + 1)
const filters = Array.from({ length: BINS }, (_, i) => {
  const center = low + (i + 1) * step
  const weights = []
  for (let bin = 0; bin < FFT / 2; bin++) {
    const weight = 1 - Math.abs(mel(bin * RATE / FFT) - center) / step
    if (weight > 0) weights.push([bin, weight])
  }
  return weights
})

function spectrum(real, imag) {
  for (let size = 2; size <= FFT; size *= 2) {
    const half = size / 2
    for (let start = 0; start < FFT; start += size) {
      for (let j = 0; j < half; j++) {
        const a = start + j, b = a + half, k = j * FFT / size
        const re = real[b] * cos[k] - imag[b] * sin[k]
        const im = real[b] * sin[k] + imag[b] * cos[k]
        real[b] = real[a] - re
        imag[b] = imag[a] - im
        real[a] += re
        imag[a] += im
      }
    }
  }
}

function fbank(samples) {
  const frames = 1 + Math.floor((samples.length - FRAME) / SHIFT)
  const result = new Float32Array(frames * BINS)
  const real = new Float32Array(FFT), imag = new Float32Array(FFT)
  const power = new Float32Array(FFT / 2)
  for (let frame = 0; frame < frames; frame++) {
    const offset = frame * SHIFT
    let mean = 0
    for (let i = 0; i < FRAME; i++) mean += samples[offset + i]
    mean /= FRAME
    real.fill(0)
    imag.fill(0)
    let previous = samples[offset] - mean
    for (let i = 0; i < FRAME; i++) {
      const current = samples[offset + i] - mean
      real[reverse[i]] = (current - 0.97 * previous) * window[i]
      previous = current
    }
    spectrum(real, imag)
    for (let i = 0; i < power.length; i++) power[i] = real[i] ** 2 + imag[i] ** 2
    for (let i = 0; i < BINS; i++) {
      let energy = 0
      for (const [bin, weight] of filters[i]) energy += power[bin] * weight
      result[frame * BINS + i] = Math.log(Math.max(energy, 2 ** -23))
    }
  }
  return result
}

function voiceFeatures(bytes, { neg_mean: mean, inv_stddev: scale }) {
  if (!(bytes instanceof ArrayBuffer) || bytes.byteLength < RATE || bytes.byteLength > RATE * 120 || bytes.byteLength % 2) {
    throw new Error('VOICE_BAD_AUDIO')
  }
  if (mean.length !== DIM || scale.length !== DIM) throw new Error('VOICE_BAD_MODEL')
  const source = new DataView(bytes)
  const samples = new Int16Array(bytes.byteLength / 2)
  let min = 0, max = 0
  for (let i = 0; i < samples.length; i++) {
    const value = source.getInt16(i * 2, true)
    samples[i] = value
    if (i === 0 || value < min) min = value
    if (i === 0 || value > max) max = value
  }
  if (max - min < 64) throw new Error('VOICE_NO_SPEECH')

  const bank = fbank(samples)
  const frames = bank.length / BINS
  const rows = Math.ceil(frames / HOP)
  const features = new Float32Array(rows * DIM)
  for (let row = 0; row < rows; row++) {
    for (let i = 0; i < DIM; i++) {
      const frame = Math.min(frames - 1, Math.max(0, row * HOP + Math.floor(i / BINS) - 3))
      features[row * DIM + i] = (bank[frame * BINS + i % BINS] + mean[i]) * scale[i]
    }
  }
  return { data: features.buffer, shape: [1, rows, DIM] }
}

function decodeVoice({ logits, token_num: count }, vocab) {
  const [, rows, width] = logits?.shape || []
  if (logits?.shape?.length !== 3 || logits.shape[0] !== 1 || logits.type !== 'float32' ||
      !(logits.data instanceof ArrayBuffer) || width !== vocab.length ||
      logits.data.byteLength !== rows * width * 4 ||
      count?.type !== 'int32' || !(count.data instanceof ArrayBuffer) || count.data.byteLength !== 4) {
    throw new Error('VOICE_BAD_MODEL')
  }
  const values = new Float32Array(logits.data)
  const limit = new Int32Array(count.data)[0]
  if (limit < 0 || limit > rows) throw new Error('VOICE_BAD_MODEL')
  let text = '', continues = false
  for (let row = 0; row < limit; row++) {
    const offset = row * width
    let best = 0
    for (let i = 1; i < width; i++) {
      if (values[offset + i] > values[offset + best]) best = i
    }
    if (!Number.isFinite(values[offset + best])) throw new Error('VOICE_BAD_MODEL')
    const token = vocab[best]
    if (token === '</s>') break
    if (/^<[^>]+>$/.test(token)) continue
    const piece = token.endsWith('@@')
    if (text && !continues && (/^[\x00-\x7f]/.test(token) || /[A-Za-z0-9]$/.test(text))) text += ' '
    text += piece ? token.slice(0, -2) : token
    continues = piece
  }
  return text.trim()
}

module.exports = { voiceFeatures, decodeVoice }
