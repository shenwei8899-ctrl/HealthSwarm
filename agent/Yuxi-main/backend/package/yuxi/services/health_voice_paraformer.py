"""自托管 Paraformer 的 PCM 特征计算、CPU 推理和解码。"""

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import onnxruntime as ort

ASSETS = {
    "model_int8.onnx": (81828675, "3ef6c19369b912f7caf3cef8e545c5ccd1a33d9d7ec792a46668dc41c4b229ec"),
    "config.json": (23381, "467031d9cdc3296a4b2bf84f11110cd505081ffa4417facaaff1e9b95194131b"),
    "vocab.txt": (75352, "4b2d964e18b9cf139b473003b6698fb2ed9a2a5ec55b93daa677b28f578897aa"),
}


class NoSpeech(Exception):
    """音频无有效信号或模型未输出文字。"""


@lru_cache(maxsize=1)
def load_model(directory: Path):
    """校验固定模型文件并缓存 CPU 会话和特征参数。"""
    for name, (size, digest) in ASSETS.items():
        with (directory / name).open("rb") as asset:
            if (directory / name).stat().st_size != size or hashlib.file_digest(asset, "sha256").hexdigest() != digest:
                raise ValueError(f"Invalid Paraformer asset: {name}")

    config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    entries = [line.rsplit(maxsplit=1) for line in (directory / "vocab.txt").read_text(encoding="utf-8").splitlines()]
    vocab = {int(index): token for token, index in entries}
    if len(entries) != 8359 or set(vocab) != set(range(8359)) or vocab[2] != "</s>":
        raise ValueError("Invalid Paraformer vocabulary")
    mean = np.asarray(config["neg_mean"], dtype=np.float32)
    scale = np.asarray(config["inv_stddev"], dtype=np.float32)
    if mean.shape != (560,) or scale.shape != (560,) or not np.isfinite([mean, scale]).all():
        raise ValueError("Invalid Paraformer normalization")

    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    session = ort.InferenceSession(
        str(directory / "model_int8.onnx"), sess_options=options, providers=["CPUExecutionProvider"]
    )
    return session, vocab, mean, scale


def recognize(directory: Path, pcm: bytes) -> str:
    """把经过接口校验的 16kHz、16 位单声道 PCM 转成文字。"""
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
    if np.ptp(samples) < 64:
        raise NoSpeech
    session, vocab, mean, scale = load_model(directory)
    speech = features(samples, mean, scale)
    logits, count = session.run(
        ["logits", "token_num"], {"speech": speech, "speech_lengths": np.array([speech.shape[1]], dtype=np.int32)}
    )
    text = decode(logits, count, vocab)
    if not text:
        raise NoSpeech
    return text


@lru_cache(maxsize=1)
def feature_tables():
    """生成与模型对应的 Hamming 窗和 80 个三角 Mel 滤波器。"""
    mel_bins = 1127 * np.log1p(np.arange(256) * (16000 / 512 / 700))
    low, high = 1127 * np.log1p(np.array([20, 8000]) / 700)
    step = (high - low) / 81
    centers = low + step * np.arange(1, 81)
    filters = np.maximum(0, 1 - np.abs(mel_bins[:, None] - centers) / step)
    return np.hamming(400).astype(np.float32), filters.astype(np.float32)


def features(samples, mean, scale):
    """使用模型对应的去直流、预加重、对数滤波和 LFR 叠帧。"""
    window, filters = feature_tables()
    frames = np.lib.stride_tricks.sliding_window_view(samples, 400)[::160].copy()
    frames -= frames.mean(axis=1, keepdims=True)
    frames[:, 1:] -= 0.97 * frames[:, :-1]
    frames[:, 0] *= 0.03
    power = np.abs(np.fft.rfft(frames * window, n=512)[:, :256]) ** 2
    bank = np.log(np.maximum(np.einsum("ij,jk->ik", power, filters), 2 ** -23)).astype(np.float32)
    starts = np.arange(0, len(bank), 6)[:, None]
    indices = np.clip(starts + np.arange(-3, 4), 0, len(bank) - 1)
    stacked = bank[indices].reshape(-1, 560)
    return ((stacked + mean) * scale)[None, :, :]


def decode(logits, count, vocab):
    """按模型词表解码，保留英文子词拼接规则。"""
    limit = int(count.item())
    if logits.ndim != 3 or logits.shape[0] != 1 or logits.shape[2] != len(vocab) or not 0 <= limit <= logits.shape[1]:
        raise ValueError("Invalid Paraformer output dimensions")
    scores = logits[0, :limit]
    best = scores.argmax(axis=1)
    if not np.isfinite(scores[np.arange(limit), best]).all():
        raise ValueError("Invalid Paraformer scores")
    text, continues = "", False
    for index in best:
        token = vocab[int(index)]
        if token == "</s>":
            break
        if re.fullmatch(r"<[^>]+>", token):
            continue
        if text and not continues and (token[0].isascii() or re.search(r"[A-Za-z0-9]$", text)):
            text += " "
        continues = token.endswith("@@")
        text += token[:-2] if continues else token
    return text.strip()
