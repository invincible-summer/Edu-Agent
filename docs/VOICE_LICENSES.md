# 语音组件许可证核查报告（STT / TTS）

> **核查日期：2026-08-30**
> 本报告是 Edu_Agent 当前默认语音安装方案的许可证核查记录，不是“绝对保证合法”或法律意见。结论只针对下表列出的上游项目、代码路径、模型制品和 revision；更换模型、量化文件、依赖版本或构建后端后，必须重新核查。

## 1. 核查范围与可复现信息

### 1.1 核查对象

当前默认方案是可插拔的本地 CPU 语音链路：

- **STT**：`whisper.cpp` 子进程 + OpenAI Whisper 的 `ggml-small-q5_1.bin` 量化模型；
- **TTS**：`MeloTTS` 源码 + `MeloTTS-Chinese` 的 `checkpoint.pth`，由独立 FastAPI sidecar 运行；
- **中文前端依赖**：`google-bert/bert-base-multilingual-uncased`；
- **文字规范化**：项目内 vendored 的 OpenCC `TSCharacters` / `TSPhrases` 简繁转换数据；
- **运行环境**：`deploy/install_voice.sh` 创建的 sidecar venv，以及其中已经在本报告中明确列出的宽松许可证依赖。

`VOICE_STT_PROVIDER` 和 `VOICE_TTS_PROVIDER` 默认仍为 `off`；安装脚本只负责准备资源，不会自动改变现有部署的 provider 开关。安装脚本的新默认模型是 `ggml-small-q5_1.bin`，仍可用 `VOICE_WHISPER_SIZE`、`VOICE_WHISPER_MODEL` 等环境变量覆盖。

### 1.2 上游项目、来源和 revision

| 制品 | 上游项目/来源 | 核查时使用的 branch、commit 或 model revision | 本项目实际使用的文件/路径 |
|---|---|---|---|
| Whisper 代码与官方模型权重 | [OpenAI Whisper](https://github.com/openai/whisper) | `main`，核查时 commit `5f86d1d86363843179951550570367b37c5d6f78` | 作为权利来源；本项目实际运行的是下方 GGML 文件 |
| `ggml-small-q5_1.bin` | [ggerganov/whisper.cpp](https://huggingface.co/ggerganov/whisper.cpp) 模型仓库 | model repo revision `5359861c739e955e79d9a303bcbc70fb988958b1`；文件 `ggml-small-q5_1.bin` | `backend/models/voice/whisper/ggml-small-q5_1.bin`（部署资源，gitignored） |
| whisper.cpp | [ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp) | `master`，本次安装脚本默认 pin 到 `c4ac0012a8f5a2082dfca6aad4ddfd8b2c02b337` | `backend/vendor/whisper.cpp/`（部署资源，gitignored） |
| ggml | [ggml-org/ggml](https://github.com/ggml-org/ggml) | 上游 `master` 核查 commit `36da57138425487184aa1da2eee2cde155909c6f`；随 whisper.cpp 的默认 CPU 构建使用 | whisper.cpp 的底层张量库 |
| MeloTTS | [myshell-ai/MeloTTS](https://github.com/myshell-ai/MeloTTS) | `main`，本次安装脚本默认 pin 到 `209145371cff8fc3bd60d7be902ea69cbdb7965a` | `backend/vendor/MeloTTS/`（部署资源，gitignored） |
| MeloTTS-Chinese | [myshell-ai/MeloTTS-Chinese](https://huggingface.co/myshell-ai/MeloTTS-Chinese) | model revision `af5d207a364ea4208c6f589c89f57f88414bdd16` | HF 缓存中的 `config.json`、`checkpoint.pth` |
| multilingual BERT | [google-bert/bert-base-multilingual-uncased](https://huggingface.co/google-bert/bert-base-multilingual-uncased) | model revision `7cbf9a625e29989f6b9c6c2fa68234c304f7e38f` | HF 缓存中的 tokenizer / model 文件 |
| OpenCC 转换数据 | [BYVoid/OpenCC](https://github.com/BYVoid/OpenCC) | `master`，核查时 commit `26753884f1984add422f3b0249ccee8613deaff6` | `backend/app/voice/zh_t2s_chars.txt`、`zh_t2s_phrases.txt` |

上表的 revision 是核查快照，不是对未来上游版本的承诺。安装脚本会在输出中显示实际下载的 MeloTTS-Chinese HF revision；发布新版本前，应把实际 revision、文件 hash 和模型名称同步回本报告。

### 1.3 许可证原文保存位置

本仓库保存的项目管理范围内许可证全文和第三方声明位于 [`docs/licenses/`](./licenses/)：

- [`whisper-MIT.txt`](./licenses/whisper-MIT.txt)：OpenAI Whisper 的 MIT 文本；
- [`whisper.cpp-MIT.txt`](./licenses/whisper.cpp-MIT.txt)：whisper.cpp 的 MIT 文本；
- [`ggml-MIT.txt`](./licenses/ggml-MIT.txt)：ggml 的 MIT 文本；
- [`melotts-MIT.txt`](./licenses/melotts-MIT.txt)：MeloTTS 代码及 MeloTTS-Chinese 模型卡所标示 MIT 许可的留档；
- [`Apache-2.0.txt`](./licenses/Apache-2.0.txt)：Apache-2.0 通用许可证全文；
- [`VOICE_THIRD_PARTY_NOTICES.md`](./licenses/VOICE_THIRD_PARTY_NOTICES.md)：实际文件、来源、revision、版权/归属和发布检查项的映射；其中也记录默认 sidecar 依赖和其许可证范围。
- [`BSD-3-Clause.txt`](./licenses/BSD-3-Clause.txt)、[`ISC.txt`](./licenses/ISC.txt)、[`LGPL-2.1.txt`](./licenses/LGPL-2.1.txt)：当前默认 `soundfile`/`librosa` wheel 归档所需的代表性文本；完整动态依赖仍以发布 SBOM 为准。

这些文件是发布说明的一部分；它们不代表把所有 pip wheel、系统库或 HF 缓存都永久锁定为当前版本。若分发完整 sidecar venv，应另外生成对应版本的 SBOM，并携带每个 wheel/系统库自己的 license 与 NOTICE 文件。

## 2. 许可证结论与制品拆分

### 2.1 逐组件核查表

| 组件/制品 | 项目用途 | 实际版本或 revision | 代码许可证 | 模型权重/数据许可证 | 允许商业使用 | 允许修改 | 允许再分发 | 允许闭源集成 | 分发时必须保留/注意 |
|---|---|---|---|---|---|---|---|---|---|
| OpenAI Whisper 代码 | Whisper 官方参考实现、模型权利来源说明 | `main@5f86d1d…` | MIT | — | 是 | 是 | 是 | 是 | MIT 版权声明和许可证全文 |
| OpenAI Whisper 官方模型权重 | STT 模型权重 | 与上游 Whisper 版本对应 | — | MIT（OpenAI README 明确说明 code and model weights） | 是 | 可制作派生/格式转换制品，但保留来源信息 | 是，按模型许可 | 是 | 模型来源、版权/许可声明 |
| `ggml-small-q5_1.bin` | 当前默认 CPU STT 权重 | `ggerganov/whisper.cpp@5359861c…` | — | 以 Whisper 权重的 MIT 权利为基础；HF 模型仓库元数据为 MIT | 是 | 量化/格式转换不改变上游权利来源 | 是，随发布物带声明 | 是 | 记录文件名、来源 revision、hash；量化文件不是一个自动产生新许可的独立模型 |
| whisper.cpp | CPU STT 推理引擎 | `master@c4ac0012…` | MIT | — | 是 | 是 | 是 | 是 | MIT 版权声明和许可证全文；启用可选后端时重新核查其额外依赖 |
| ggml | whisper.cpp 使用的底层张量库 | `master@36da5713…` | MIT | — | 是 | 是 | 是 | 是 | ggml 的版权声明和 MIT 全文 |
| MeloTTS | TTS 推理代码 | `main@20914537…` | MIT | — | 是 | 是 | 是 | 是 | MIT 版权声明和许可证全文 |
| MeloTTS-Chinese `checkpoint.pth` | 中文 TTS 声学模型 | `af5d207a…` | — | MIT（模型卡 `license: mit`） | 是，按该 revision 的模型卡 | 需保留模型来源并遵守模型卡 | 是，按模型卡并保留声明 | 是 | 不删除模型仓库附带的 README/许可信息；发布前核对 revision |
| `bert-base-multilingual-uncased` | MeloTTS 中文前端 BERT | `7cbf9a62…` | — | Apache-2.0（模型卡 metadata） | 是 | 是 | 是 | 是 | Apache LICENSE、版权/归属、修改文件声明；如有 NOTICE 需保留 |
| OpenCC `TSCharacters` / `TSPhrases` | STT 转写结果繁→简的 vendored 词典数据 | `master@26753884…`；项目文件含来源头 | — | Apache-2.0 | 是 | 是 | 是 | 是 | Apache LICENSE、来源/归属说明；词典只是文字规范化数据 |
| sidecar 中已核实的直接依赖：`transformers==4.27.4`、`numpy==1.26.4`、`mecab-python3`、`unidic-lite`、`anyascii`、`jamo`、`fugashi`、`gruut`、`gruut_ipa`、`nltk`，以及运行时使用的音频/CPU 包 | TTS 导入期和中文合成运行时依赖 | 版本以安装环境/SBOM 为准；其中有固定版本的按 requirements | Apache-2.0、BSD/ISC/MIT 等，按各包自己的发行元数据；`torch` 为多许可证组合，`soundfile` wheel 还携带 libsndfile 相关条款 | — | 不能用一张总表替代逐包核查 | 按各包许可 | 按各包许可 | 通常允许，但需逐包确认 | 分发 sidecar 或 wheel 时携带各包 license/NOTICE；新增依赖需加入 SBOM |

这里的“是”表示许可证文本本身授予相应权限，不等于对数据来源、声音人格、商标、隐私、专利有效性或最终产品合规作出保证。

### 2.2 代码许可证与模型权重许可证不是一回事

- OpenAI Whisper 的代码是 MIT，官方 README 同时明确模型权重按 MIT 发布；但 GGML 文件仍是一个**具体的模型制品**，应记录它的下载来源、文件名、revision 和 hash，不能仅因 `whisper.cpp` 代码是 MIT 就跳过权重核查。
- `ggml-small-q5_1.bin` 是对 Whisper 权重的 GGML/量化格式转换。转换格式本身不会自动生成一个比上游更宽或更窄的新模型许可；发布时应同时保留 Whisper 权利来源和转换仓库的来源信息。
- MeloTTS 的代码许可证和 `MeloTTS-Chinese` 的 `checkpoint.pth` 模型许可证分开记录。模型卡标示 MIT 是权重结论的依据，不能只引用 MeloTTS 代码仓库的 LICENSE。
- BERT 是 MeloTTS 中文前端实际读取的独立模型制品，适用 Apache-2.0；OpenCC 词典也是独立数据制品，适用其文件头和上游仓库标示的 Apache-2.0。

## 3. 为什么这些组件可以用于商业产品

在遵守许可证通知义务的前提下，当前核查范围内的 MIT/Apache-2.0 组件可以用于商业产品、教育平台、SaaS 服务、比赛作品、内部系统和闭源软件，不需要向许可证作者支付授权费，也不需要公开 Edu_Agent 自身的源代码。可以复制、修改、合并、发布、再分发，或销售包含这些组件的产品；但每个模型或数据制品仍要按自己的模型卡、数据说明和许可证执行。

### 3.1 MIT 的许可范围

MIT 文本通常授予：

- 免费用于商业和非商业项目；
- 复制、修改、合并到其他项目；
- 发布、再分发和销售包含该软件的产品；
- 集成到闭源商业软件；
- 制作并分发修改后的版本；
- 不要求项目主体开源，也不要求向上游支付授权费或版税。

MIT 的主要义务和边界：

- 分发软件或模型文件时，保留原版权声明和 MIT 许可证全文；
- 修改代码时，建议在文件或发布说明中标明修改内容，方便审计；
- MIT 不授予上游名称、商标或背书权；合理描述来源不等于可以使用上游商标进行营销；
- MIT 按“现状”提供，不提供质量、适用性或不侵权保证；上游通常不承担因使用组件造成的损失责任；
- MIT 合规不等于音频采集、转写文本、训练数据、个人信息和隐私处理自动合规。

### 3.2 Apache-2.0 的额外事项

Apache-2.0 同样允许免费商用、修改、分发和闭源集成，不要求 Edu_Agent 主体开源，也不要求支付版税；但发布时应额外注意：

- 随发布物提供 Apache-2.0 许可证全文；
- 保留上游版权、专利、商标和归属声明中与所分发部分有关的内容；
- 如果上游提供 `NOTICE` 文件，应一并保留其中的归属信息；当前核查的 BERT、OpenCC 制品应以实际下载 revision 的文件为准；
- 修改 Apache-2.0 文件时，给修改文件加上显著的修改声明；
- Apache-2.0 包含对贡献者专利权利的一定范围授权；如果针对该作品提起专利诉讼，相关专利授权可能按许可证终止；
- Apache-2.0 不授予上游商标权，也不提供质量、适用性或不侵权保证。

## 4. 分发场景与实际义务

### 4.1 SaaS 与软件/模型分发

如果只是服务器端运行 SaaS，通常没有把二进制、源代码或模型权重交付给用户，因此不会触发软件再分发场景下的全部义务；但仍应保留内部许可证台账，并遵守音频、转写文本和用户隐私相关法律。

如果向客户、学校、比赛评委或用户提供 Docker 镜像、安装包、二进制、sidecar venv 或模型权重，则属于应认真处理的分发场景：第三方声明、版权、许可证全文、NOTICE（如有）、修改标记和实际模型来源应随发布物提供。不要把“没有公开源码”误解为“不需要许可证文件”。

### 4.2 默认方案中未纳入的 copyleft/未知依赖

MeloTTS 上游完整依赖谱系包含并非本项目默认中文路径所需的组件。当前安装策略如下：

| 组件 | 已知许可风险 | 默认安装/运行处理 |
|---|---|---|
| `unidecode` | GPL-2.0+ | 不写入 `requirements.txt`；中文路径不使用 |
| `pykakasi` | GPLv3+ | 不由安装脚本安装；`melo_bootstrap.py` 在导入前注入最小 stub，中文路径不执行日语转换 |
| `num2words` | LGPL | 不由安装脚本安装；导入期以 stub 提供符号，中文路径不执行日/韩数字规范化 |
| 完整 `unidic` 词典 | 许可和体积需按实际发行包核查 | 不安装；默认使用较小的 `unidic-lite`，仍需随 sidecar SBOM 记录其自身许可 |
| `eng_to_ipa` | 上游发行元数据未作为本方案的已确认许可依据 | 不安装；中文默认路径不依赖 |

这只是**默认安装脚本和中文路径的范围说明**，不是对任意已经存在的 venv、可选语言路径、GPU/加速后端或未来依赖树的绝对结论。若复用旧 venv、启用其他 MeloTTS 语言、安装可选后端，发布前必须重新扫描实际文件和包元数据；不能仅凭 `requirements.txt` 推断最终镜像的完整许可证集合。

## 5. 未纳入默认方案的 ASR/TTS 模型

SenseVoice、Paraformer、第三方中文微调模型及其他替代方案不因为代码仓库公开或标注“开源”就自动具有免费商业权利。加入默认方案前必须分别确认：

1. 模型卡、权重文件和上游许可证是否一致；
2. 是否存在额外的非商业限制、研究用途限制、来源数据限制、地区限制或再分发限制；
3. 量化、剪枝、转换后的文件是否有独立说明，是否仍可追溯到原始权重；
4. 实际安装脚本、Docker 镜像和模型包是否会分发该权重，以及随包携带了哪些声明。

在严格 MIT/Apache-2.0 要求下，当前默认优先采用许可证链条更清晰的 Whisper/whisper.cpp 路线。未来加入其他中文 ASR 前，必须新增完整的核查表、上游 revision、实际文件名、hash 和对应许可证文件。

## 6. 资源、模型与并发评估

目标环境为 **4 vCPU / 8 GB RAM / 8 GB 系统盘、无 GPU**。下面是安装包和当前链路的保守预算，不是性能保证；上线前应在目标 CPU 上实测。

| 项目 | 估算/默认值 | 说明 |
|---|---|---|
| STT 模型 | `ggml-small-q5_1.bin`，约 180–190 MiB | 相比更小模型增加内存和磁盘，但提高中文识别余量；实际 hash/大小以下载文件为准 |
| 磁盘 | whisper.cpp 源码/构建 + small 模型约 0.5 GB；sidecar venv 约 1.7–2.0 GB；HF 缓存约 0.8–1.0 GB | 精简安装约 3.0–3.5 GB，8 GB 系统盘仍需为系统、项目和临时文件留余量；安装使用 `--no-cache-dir` |
| 内存 | 主服务约 1 GB；small 量化 STT 峰值需按 0.6–1.0 GB 预留；MeloTTS 常驻约 1.5–2.5 GB | 8 GB RAM 通常可容纳低并发，但应留给 OS、编译和文件缓存 |
| STT 线程 | `VOICE_WHISPER_THREADS=2` 默认；4 vCPU 可按实测调到 3–4 | `whisper_cpp.py` 仍用 `Semaphore(1)` 串行化 STT 进程，避免多轮同时抢占 CPU/内存 |
| TTS 线程 | `start.sh` 默认 `OMP_NUM_THREADS=2`、`MKL_NUM_THREADS=2` | 逐句合成、逐句推送；并发提高前先测 RTF 和内存峰值 |
| 音频上限 | `VOICE_MAX_AUDIO_SECONDS=30` | 保护 CPU 转写延迟；不是音频数据保留期限 |

模型和引擎路径可通过 `.env` 覆盖，方便未来切换；切换后必须同时更新安装脚本说明、模型 revision/hash 和本报告。代码层的 provider 接口与模型许可证是两个独立层次：实现同一个 `STTProvider` 接口，不会自动继承 Whisper 的模型许可。

当前 STT 结果仍会经过项目内 OpenCC T2S 词典做繁体到简体的文字规范化。这只是输出文字规范化，不是对识别准确率、专名或识别错误的保证。

## 7. 发布前检查清单

1. 保留 `docs/licenses/` 下相关许可证全文和 [`VOICE_THIRD_PARTY_NOTICES.md`](./licenses/VOICE_THIRD_PARTY_NOTICES.md)。
2. 发布 Docker 镜像、安装包、sidecar venv 或模型包时，同时携带第三方版权、许可证和 NOTICE（如有）。
3. 不删除模型文件内或模型仓库附带的许可证、README、模型卡和归属信息。
4. 记录实际使用的模型名称、量化格式、来源仓库、revision/commit 和文件 hash。
5. 检查新增 Python 包、系统库、编解码器、GPU/CPU 后端和模型依赖的许可证，并把 SBOM 与发布版本绑定。
6. 不将用户录音、转写文本或私有模型缓存提交到仓库；模型缓存仍属于部署资源，不是公共项目内容。
7. 如果替换成其他中文 ASR/TTS 模型，重新核查模型权重、训练/来源数据说明和再分发权限；不要只检查代码仓库许可证。
8. 如果启用 MeloTTS 非中文语言、可选加速后端或复用旧 venv，重新扫描实际安装文件，不能套用本报告对默认中文路径的结论。

## 8. 核查来源摘要

- Whisper README 的 License 节说明代码和模型权重按 MIT 发布；完整文本已保存为 `docs/licenses/whisper-MIT.txt`。
- whisper.cpp 与 ggml 的上游 LICENSE 为 MIT；对应文本已分别保存。
- MeloTTS 上游 LICENSE 为 MIT；MeloTTS-Chinese 模型卡 revision 标示 `license: mit`。
- BERT 模型卡 revision 标示 `license: apache-2.0`。
- OpenCC 的词典文件头标明 `License: Apache-2.0`，上游仓库 LICENSE 也为 Apache-2.0；项目内 vendored 文件保留了来源头。

如果上游许可证、模型卡或实际文件与本报告不一致，以发布时取得的具体文件和上游许可文本为准；在无法核实时，不应把该制品标为默认“可商用”。
