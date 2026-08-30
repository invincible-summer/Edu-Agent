# 语音组件许可证与商业使用说明

**核查日期：2026-08-30。** 本文件是当前仓库语音实现的工程化第三方声明，不是
对未来版本、特定浏览器服务或任何部署方案的法律意见。发布时必须以实际随发布物
分发的源码、模型、wheel、系统库和服务条款为准。

## 1. 当前链路和边界

```text
浏览器 SpeechRecognition / webkitSpeechRecognition
    → 最终识别文本（WebSocket JSON）
    → Edu_Agent 会话、LLM、工具和持久化
    → MeloTTS sidecar
    → 浏览器播放 TTS PCM
```

- **STT**：只使用浏览器平台的 Web Speech Recognition API。仓库不分发该 API 的
  实现，不安装服务器 STT，不缓存或上传电话输入 PCM；后端只接受
  `{"type":"utterance_end","text":"..."}`。
- **TTS**：当前可选的 `melo` provider 在本地 sidecar 中运行固定 revision 的
  MeloTTS `ZH`（中英混排）路径；`stub` 仅用于测试，`off` 为默认关闭。
- **浏览器服务边界**：`SpeechRecognition`/`webkitSpeechRecognition` 是浏览器
  平台 API，不是本项目的 MIT 依赖。Chrome、Edge 及其可能调用的在线识别服务的
  软件许可、隐私政策、地域限制、计费和商业条款由厂商决定。项目不宣称该服务
  MIT、永久免费、离线可用或无条件适合商业部署；部署方须按实际浏览器、版本、
  地区和组织政策自行审查；可从 [Google Privacy](https://policies.google.com/privacy) 和
  [Microsoft Privacy Statement](https://www.microsoft.com/en-us/privacy/privacystatement)
  开始核对厂商条款。

## 2. 项目主动管理的代码和模型

| 组件 | 用途 | 已核查来源和 revision | 许可证/边界 | 发布处理 |
|---|---|---|---|---|
| MeloTTS | TTS 推理源码，随仓库以 vendor checkout 使用 | [GitHub LICENSE](https://github.com/myshell-ai/MeloTTS/blob/209145371cff8fc3bd60d7be902ea69cbdb7965a/LICENSE)，`209145371cff8fc3bd60d7be902ea69cbdb7965a` | MIT；允许商业使用、修改和再分发，但须保留版权和许可证，且不授予商标或质量保证 | 保留 `docs/licenses/melotts-MIT.txt`；分发 `backend/vendor/MeloTTS` 时保留上游 LICENSE |
| MeloTTS-Chinese | 中文/中英混排 TTS 权重 | [模型卡](https://huggingface.co/myshell-ai/MeloTTS-Chinese/tree/af5d207a364ea4208c6f589c89f57f88414bdd16)，`af5d207a364ea4208c6f589c89f57f88414bdd16` | 模型卡标示 MIT；模型权重、README、模型卡和来源文件必须作为一个可审计单元处理 | 发布权重或 HF 缓存时随附模型卡、README、许可证、revision 和 hash |
| `bert-base-multilingual-uncased` | MeloTTS 中文前端 BERT 特征 | [模型卡](https://huggingface.co/google-bert/bert-base-multilingual-uncased/tree/7cbf9a625e29989f6b9c6c2fa68234c304f7e38f)，`7cbf9a625e29989f6b9c6c2fa68234c304f7e38f` | Apache-2.0；不是 MIT。再分发时保留 Apache 条款、版权和 NOTICE（如模型卡/权重目录提供） | 发布缓存或镜像时保留模型卡、许可证、revision 和 hash |
| `bert-base-uncased` | MeloTTS 中英混排 tokenizer | [模型卡](https://huggingface.co/google-bert/bert-base-uncased/tree/86b5e0934494bd15c9632b12f734a8a67f723594)，`86b5e0934494bd15c9632b12f734a8a67f723594` | Apache-2.0；不是 MIT | 发布 tokenizer/cache 时保留模型卡、许可证、revision 和 hash |

MeloTTS 的 MIT 许可只覆盖 MeloTTS 代码本身；它不覆盖模型权重、BERT、Python
依赖、系统音频库、浏览器软件或浏览器厂商的在线服务。模型卡标示的许可证也不
自动覆盖训练数据、商标、第三方依赖或厂商服务。

## 3. sidecar 直接依赖逐项清单

以下每一行对应 `backend/voice_sidecar/requirements.txt` 中的直接依赖。除
`transformers` 和 `numpy` 外，安装文件允许解析到兼容的新版本，因此表中的许可
是包/上游的许可类别，不是对未来 wheel 内容的替代审计。发布 sidecar 镜像、wheel
或虚拟环境时，必须保留实际 `*.dist-info/licenses`、NOTICE，并生成版本化 SBOM。

| 包 | 当前用途 | 上游许可证（已核查） | 官方来源/许可证 |
|---|---|---|---|
| `fastapi` | sidecar HTTP | MIT | [repo](https://github.com/fastapi/fastapi)、[LICENSE](https://github.com/fastapi/fastapi/blob/master/LICENSE) |
| `uvicorn` | sidecar ASGI server | BSD-3-Clause | [repo](https://github.com/Kludex/uvicorn)、[LICENSE](https://github.com/Kludex/uvicorn/blob/main/LICENSE.md) |
| `pydantic` | sidecar request schema | MIT | [repo](https://github.com/pydantic/pydantic)、[LICENSE](https://github.com/pydantic/pydantic/blob/main/LICENSE) |
| `torch` | CPU TTS inference | wheel 中为 Apache-2.0、Apache-2.0 WITH LLVM-exception、BSD-2-Clause、BSD-3-Clause、BSL-1.0、MIT 等组合，并含第三方归属 | [repo](https://github.com/pytorch/pytorch)、[LICENSE](https://github.com/pytorch/pytorch/blob/main/LICENSE)；以实际 wheel `LICENSE`/`third_party` 为准 |
| `torchaudio` | TTS 音频/推理辅助 | BSD-2-Clause，并随发行物附带第三方声明 | [repo](https://github.com/pytorch/audio)、[LICENSE](https://github.com/pytorch/audio/blob/main/LICENSE) |
| `transformers==4.27.4` | BERT tokenizer/model loader | Apache-2.0 | [repo](https://github.com/huggingface/transformers)、[LICENSE](https://github.com/huggingface/transformers/blob/v4.27.4/LICENSE) |
| `numpy==1.26.4` | 数值张量/音频数组 | BSD-3-Clause；binary wheel 可能附带 OpenBLAS 等额外声明 | [repo](https://github.com/numpy/numpy)、[license](https://github.com/numpy/numpy/blob/v1.26.4/LICENSE.txt) |
| `scipy` | MeloTTS `scipy.io.wavfile` 及数值辅助 | BSD-3-Clause；以实际 wheel 及其 bundled libraries 为准 | [repo](https://github.com/scipy/scipy)、[license](https://github.com/scipy/scipy/blob/main/LICENSE.txt) |
| `soundfile` | sidecar WAV 写出 | BSD-3-Clause | [repo](https://github.com/bastibe/python-soundfile)、[LICENSE](https://github.com/bastibe/python-soundfile/blob/master/LICENSE) |
| `librosa` | MeloTTS mel/spectrogram 处理 | ISC | [repo](https://github.com/librosa/librosa)、[LICENSE](https://github.com/librosa/librosa/blob/main/LICENSE.md) |
| `cached-path` | MeloTTS 模型/配置缓存 | Apache-2.0 | [repo](https://github.com/allenai/cached_path)、[LICENSE](https://github.com/allenai/cached_path/blob/main/LICENSE) |
| `huggingface_hub` | HF 模型下载 | Apache-2.0 | [repo](https://github.com/huggingface/huggingface_hub)、[LICENSE](https://github.com/huggingface/huggingface_hub/blob/main/LICENSE) |
| `tqdm` | MeloTTS 推理进度包装 | MPL-2.0 AND MIT | [repo](https://github.com/tqdm/tqdm)、[license](https://github.com/tqdm/tqdm/blob/master/LICENCE) |
| `jieba` | 中文分词 | MIT | [repo](https://github.com/fxsjy/jieba)、[license](https://github.com/fxsjy/jieba/blob/master/LICENSE) |
| `pypinyin` | 中文拼音/声调 | MIT | [repo](https://github.com/mozillazg/python-pinyin)、[license](https://github.com/mozillazg/python-pinyin/blob/master/LICENSE.txt) |
| `cn2an` | 中文数字规范化 | MIT | [repo](https://github.com/Ailln/cn2an)、[license](https://github.com/Ailln/cn2an/blob/master/LICENSE) |
| `g2p_en` | `ZH_MIX_EN` 中嵌入英文的 G2P | Apache-2.0 | [repo](https://github.com/Kyubyong/g2p)、[license](https://github.com/Kyubyong/g2p/blob/master/LICENSE.txt) |
| `nltk` | `g2p_en` 的词性/CMU 语料读取 | Apache-2.0 | [repo](https://github.com/nltk/nltk)、[license](https://github.com/nltk/nltk/blob/develop/LICENSE.txt) |

### 3.1 wheel 和传递依赖边界

上表不假装把动态依赖闭包压缩成一张永久不变的 MIT 表。例如 `torch`、`numpy`、
`scipy`、`soundfile` 和 `librosa` 的 wheel 可能带 native library；`soundfile`
wheel 当前可能携带 `libsndfile`，其许可证文件包含 LGPL-2.1 及其他声明。发布
二进制时应保留实际 wheel 中的 `LICENSE`、`COPYING`、`NOTICE` 和 bundled library
清单；仓库保留 `docs/licenses/LGPL-2.1.txt` 作为当前 soundfile/lib boundary 的
提示，不把它误写成全部 Python 依赖的许可证。

`cached-path`、`transformers`、`librosa`、`g2p_en` 等会再引入
`requests`、`filelock`、`tokenizers`、`inflect`、`python-crfsuite` 等传递包。
它们的版本和许可证以发布环境的 `*.dist-info` 与 SBOM 为准，不能只凭本文件中的
直接依赖表再分发。发布前建议使用 `pip inspect`/CycloneDX 等工具生成并归档 SBOM。

## 4. 明确未安装的旧/非中文语言依赖

为了让固定 MeloTTS 版本的 `cleaner` 导入通过，源码仍会在模块加载期触碰日/韩
模块名；`backend/voice_sidecar/melo_bootstrap.py` 在导入 MeloTTS 前提供 fail-loud
stub。当前安装脚本不会安装以下包，也不会执行对应语言路径：

- `mecab-python3`、`unidic`、`unidic-lite`、`fugashi`（日语词典/MeCab；其中词典
  数据可能同时含 GPL/LGPL/BSD 条款）；
- `pykakasi`、`num2words`、`g2pkk`、`anyascii`、`jamo`、`unidecode`、`eng_to_ipa`
  （日/韩/其他语言路径）；
- MeloTTS upstream 的 `gradio`、`pydub`、`langid`、`tensorboard` 及训练/演示依赖。

bootstrap 也屏蔽非中文 BERT backend 的导入期 tokenizer 构造，因此当前 warmup
只需要 MeloTTS-Chinese、`bert-base-multilingual-uncased` 和中英混排所需的
`bert-base-uncased` tokenizer，不下载法/西/日/韩模型。

如果将来启用非中文语言、修改 bootstrap 或直接 `pip install` 上游 MeloTTS，必须
重新做逐包许可证、词典/语料和模型审计；本文件不能沿用。

## 5. 浏览器语音识别不是本项目许可证

[MDN SpeechRecognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition)
将该接口标为浏览器实现相关且兼容性有限；浏览器厂商可选择在线识别服务。Chrome
或 Edge 只是当前推荐的运行目标，不代表本项目拥有或转授其识别服务权利。生产
部署方必须把浏览器版本、企业策略、隐私告知、数据跨境/留存、服务可用性和商业
条款纳入自己的审查。

## 6. 发布前清单

1. 若分发 MeloTTS 源码，保留 MIT 版权/许可证全文；若分发模型，保留模型卡、
   README、许可证、revision 和 hash。
2. 不把 MeloTTS MIT 文本当作 BERT、PyTorch、音频库、Python 包或浏览器服务的
   许可证替代品。
3. 对实际 sidecar wheel、native library、NLTK data 和 HF 模型缓存生成 SBOM，
   随发布物保留所有 `LICENSE`/`COPYING`/`NOTICE`。
4. 对浏览器识别服务单独取得组织所需的隐私、服务和商业授权；本项目不作免费、
   离线或无条件商用承诺。
5. 替换版本、模型、语言或依赖后重新执行本审计。

## 7. 仓库内随附的许可证全文

仓库只保留当前语音发布边界实际需要的短名单：

- `docs/licenses/melotts-MIT.txt`：随仓库管理的 MeloTTS MIT 代码；
- `docs/licenses/Apache-2.0.txt`：当前 Apache-2.0 组件的通用全文；
- `docs/licenses/BSD-2-Clause.txt`：当前 torchaudio BSD-2-Clause；
- `docs/licenses/BSD-3-Clause.txt`：当前 soundfile/BSD-3-Clause 组件；
- `docs/licenses/ISC.txt`：当前 librosa/ISC 组件；
- `docs/licenses/LGPL-2.1.txt`：soundfile wheel 可能携带的 libsndfile 边界提示。

已删除的历史语音输入许可证文本不属于当前发布物，因此不再保留。

## 8. 核查来源

- [MeloTTS GitHub LICENSE](https://github.com/myshell-ai/MeloTTS/blob/209145371cff8fc3bd60d7be902ea69cbdb7965a/LICENSE) 与 [requirements](https://github.com/myshell-ai/MeloTTS/blob/209145371cff8fc3bd60d7be902ea69cbdb7965a/requirements.txt)；
- [MeloTTS-Chinese 模型卡与 MIT 标注](https://huggingface.co/myshell-ai/MeloTTS-Chinese/tree/af5d207a364ea4208c6f589c89f57f88414bdd16)；
- [BERT 模型卡与 Apache-2.0 标注](https://huggingface.co/google-bert/bert-base-multilingual-uncased/tree/7cbf9a625e29989f6b9c6c2fa68234c304f7e38f)；
- 上表每个包的官方仓库 LICENSE、PyPI 元数据、实际安装 wheel `*.dist-info` 和 native library `COPYING`；
- [MDN SpeechRecognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition) 兼容性和平台边界说明；
- [Google Privacy](https://policies.google.com/privacy) 与 [Microsoft Privacy Statement](https://www.microsoft.com/en-us/privacy/privacystatement)，用于按实际浏览器核对厂商隐私/服务条款。

若上游页面、模型卡、wheel metadata、NOTICE 或实际发布物之间存在差异，以实际
发布物包含的许可证文件和版本化 SBOM 为准；无法核实的组件不得标示为“免费商用”。
