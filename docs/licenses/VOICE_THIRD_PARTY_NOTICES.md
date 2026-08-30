# Edu_Agent 语音第三方声明

核查日期：2026-08-30。本文按 GitHub 常见 Third-Party Notices 形式，列出当前
仓库语音链路主动选择的代码、模型和 sidecar 直接依赖。它不是“全链路 MIT”声明。
动态传递依赖、wheel 内 native library、NLTK data 和模型缓存必须以发布时生成的
SBOM 及其随附 `LICENSE`/`COPYING`/`NOTICE` 为准。

## 1. 运行时范围

- 输入：浏览器 `SpeechRecognition`/`webkitSpeechRecognition`，只发送最终文本；
  不向 Edu_Agent 后端发送电话 PCM。
- 输出：本地 MeloTTS `ZH`/`ZH_MIX_EN` sidecar，返回 WAV，后端转为 PCM16 给浏览器。
- 不随当前运行时安装服务器语音识别、日/韩词典或其输入音频链路。
- 浏览器 API 和 Chrome/Edge 在线识别服务不随本项目以 MIT 软件分发，必须遵守
  实际厂商的隐私、服务、地域、计费和商业条款。

## 2. 代码与模型

| 项目 | 用途 | 来源与固定 revision | 许可证与再分发要求 |
|---|---|---|---|
| [MeloTTS](https://github.com/myshell-ai/MeloTTS) | TTS 推理代码 | [`209145371cff8fc3bd60d7be902ea69cbdb7965a`](https://github.com/myshell-ai/MeloTTS/tree/209145371cff8fc3bd60d7be902ea69cbdb7965a) | MIT；保留上游版权和许可证。全文：[`melotts-MIT.txt`](melotts-MIT.txt) |
| [MeloTTS-Chinese](https://huggingface.co/myshell-ai/MeloTTS-Chinese) | 中文 TTS 权重 | [`af5d207a364ea4208c6f589c89f57f88414bdd16`](https://huggingface.co/myshell-ai/MeloTTS-Chinese/tree/af5d207a364ea4208c6f589c89f57f88414bdd16) | 模型卡标示 MIT；随权重保留模型卡、README、许可证、revision/hash |
| [`bert-base-multilingual-uncased`](https://huggingface.co/google-bert/bert-base-multilingual-uncased) | 中文 BERT 特征 | [`7cbf9a625e29989f6b9c6c2fa68234c304f7e38f`](https://huggingface.co/google-bert/bert-base-multilingual-uncased/tree/7cbf9a625e29989f6b9c6c2fa68234c304f7e38f) | Apache-2.0；不是 MIT，随模型保留 Apache 条款和 NOTICE（如有） |
| [`bert-base-uncased`](https://huggingface.co/google-bert/bert-base-uncased) | 中英混排 tokenizer | [`86b5e0934494bd15c9632b12f734a8a67f723594`](https://huggingface.co/google-bert/bert-base-uncased/tree/86b5e0934494bd15c9632b12f734a8a67f723594) | Apache-2.0；不是 MIT，随模型保留 Apache 条款和 NOTICE（如有） |

MeloTTS MIT 不覆盖上述模型、传递依赖、PyTorch/native libraries 或浏览器服务。

## 3. Sidecar direct dependencies

版本规则以 `backend/voice_sidecar/requirements.txt` 为准；表中是已核查的官方
许可证类别。下表中的宽松许可证通常允许商业使用，但必须履行版权、许可证、NOTICE
和商标边界义务；`torch`/native library 不能压缩成单一 MIT 标签。

| Package | Role | License / required notice | Official source |
|---|---|---|---|
| `fastapi` | HTTP API | MIT | [repo](https://github.com/fastapi/fastapi), [LICENSE](https://github.com/fastapi/fastapi/blob/master/LICENSE) |
| `uvicorn` | ASGI server | BSD-3-Clause | [repo](https://github.com/Kludex/uvicorn), [LICENSE](https://github.com/Kludex/uvicorn/blob/main/LICENSE.md) |
| `pydantic` | request validation | MIT | [repo](https://github.com/pydantic/pydantic), [LICENSE](https://github.com/pydantic/pydantic/blob/main/LICENSE) |
| `torch` | CPU inference | Apache-2.0, Apache-2.0 WITH LLVM-exception, BSD-2/3-Clause, BSL-1.0, MIT and other bundled notices | [repo](https://github.com/pytorch/pytorch), [LICENSE](https://github.com/pytorch/pytorch/blob/main/LICENSE) |
| `torchaudio` | audio helpers | BSD-2-Clause plus bundled notices | [repo](https://github.com/pytorch/audio), [LICENSE](https://github.com/pytorch/audio/blob/main/LICENSE) |
| `transformers==4.27.4` | BERT loader | Apache-2.0 | [repo](https://github.com/huggingface/transformers), [LICENSE](https://github.com/huggingface/transformers/blob/v4.27.4/LICENSE) |
| `numpy==1.26.4` | numeric arrays | BSD-3-Clause plus binary-wheel notices | [repo](https://github.com/numpy/numpy), [LICENSE](https://github.com/numpy/numpy/blob/v1.26.4/LICENSE.txt) |
| `scipy` | `scipy.io.wavfile`/numeric helper | BSD-3-Clause plus binary-wheel notices | [repo](https://github.com/scipy/scipy), [LICENSE](https://github.com/scipy/scipy/blob/main/LICENSE.txt) |
| `soundfile` | WAV output | BSD-3-Clause; bundled `libsndfile` may add LGPL-2.1/BSD terms | [repo](https://github.com/bastibe/python-soundfile), [LICENSE](https://github.com/bastibe/python-soundfile/blob/master/LICENSE) |
| `librosa` | mel/spectrogram processing | ISC | [repo](https://github.com/librosa/librosa), [LICENSE](https://github.com/librosa/librosa/blob/main/LICENSE.md) |
| `cached-path` | model/config cache | Apache-2.0 | [repo](https://github.com/allenai/cached_path), [LICENSE](https://github.com/allenai/cached_path/blob/main/LICENSE) |
| `huggingface_hub` | model download | Apache-2.0 | [repo](https://github.com/huggingface/huggingface_hub), [LICENSE](https://github.com/huggingface/huggingface_hub/blob/main/LICENSE) |
| `tqdm` | progress wrapper | MPL-2.0 AND MIT | [repo](https://github.com/tqdm/tqdm), [license](https://github.com/tqdm/tqdm/blob/master/LICENCE) |
| `jieba` | Chinese segmentation | MIT | [repo](https://github.com/fxsjy/jieba), [LICENSE](https://github.com/fxsjy/jieba/blob/master/LICENSE) |
| `pypinyin` | Chinese pinyin | MIT | [repo](https://github.com/mozillazg/python-pinyin), [LICENSE](https://github.com/mozillazg/python-pinyin/blob/master/LICENSE.txt) |
| `cn2an` | Chinese number normalization | MIT | [repo](https://github.com/Ailln/cn2an), [LICENSE](https://github.com/Ailln/cn2an/blob/master/LICENSE) |
| `g2p_en` | embedded English G2P | Apache-2.0 | [repo](https://github.com/Kyubyong/g2p), [LICENSE](https://github.com/Kyubyong/g2p/blob/master/LICENSE.txt) |
| `nltk` | G2P data access | Apache-2.0 | [repo](https://github.com/nltk/nltk), [LICENSE](https://github.com/nltk/nltk/blob/develop/LICENSE.txt) |

## 4. Data and native libraries

- `g2p_en` imports NLTK `cmudict` and averaged-perceptron tagger data. The installer
  fetches the data packages from the [official nltk_data repository](https://github.com/nltk/nltk_data).
  NLTK's [dataset license index](https://github.com/nltk/nltk_data/blob/gh-pages/DATASET-LICENSES.md)
  lists both averaged-perceptron packages as MIT, but currently lists `cmudict` as
  unclarified; its bundled CMUdict README contains BSD-style terms. Preserve that README,
  record the source in the SBOM, and verify commercial redistribution against the original
  CMU source before shipping.
- `soundfile` may load a bundled/system `libsndfile`; retain its `COPYING` and any
  codec/native-library notices. The repository keeps [`LGPL-2.1.txt`](LGPL-2.1.txt)
  because this current audio boundary can contain LGPL-2.1 material.
- PyTorch, NumPy, SciPy and other binary wheels can bundle additional libraries. Never
  replace their `LICENSE`, `COPYING`, `NOTICE` or `third_party` directories with this
  short table.

## 5. Deliberately excluded language packages

`melo_bootstrap.py` supplies fail-loud import stubs for `MeCab`, `pykakasi`, `num2words`,
`anyascii`, `jamo`, `gruut` and `gruut_ipa`. The installer also removes stale copies of
`mecab-python3`, `unidic-lite`, `fugashi`, `g2pkk`, `gruut`, `gruut-ipa`, `unidecode` and `eng_to_ipa` from a
reused virtualenv. These packages/dictionaries are not part of the current Chinese
runtime, so they are not listed as current project dependencies or MIT notices.

The bootstrap also replaces unused French, Spanish, Japanese and Korean BERT
backends before they construct tokenizers. The current warmup therefore requires only
MeloTTS-Chinese, `bert-base-multilingual-uncased`, and the `bert-base-uncased`
tokenizer used by mixed English text.

The upstream training/UI extras (`gradio`, `pydub`, `langid`, `tensorboard`) are likewise
not installed by this sidecar. Enabling another language or installing upstream
MeloTTS directly requires a new license/data audit.

## 6. Browser API notice

`SpeechRecognition` and `webkitSpeechRecognition` are browser APIs, not source code
licensed by this repository. See [MDN](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition)
for compatibility notes. Chrome/Edge and any remote recognition service they use have
separate terms, privacy policies, data handling, and commercial conditions. Edu_Agent
only sends final text to its backend; it does not grant, bundle, or guarantee access to
those vendor services.

## 7. Distribution checklist

1. Keep `melotts-MIT.txt` and the MeloTTS copyright notice when distributing MeloTTS code.
2. Keep model-card README/license, revision and hash when distributing model files.
3. Preserve every resolved wheel's `*.dist-info/licenses`, `LICENSE`, `COPYING`, `NOTICE`
   and bundled-native-library notices, or ship an equivalent versioned SBOM.
4. Do not describe this entire chain as MIT, free forever, offline, or unconditionally
   commercially authorized.
5. Re-run the audit whenever a package, wheel, model, language, browser target or vendor
   service changes.
