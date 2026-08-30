# 语音组件许可证核实与声明（STT / TTS）

> 核实日期：2026-08-30。本文档是 Edu_Agent 语音功能（可插拔 STT/TTS 插件层）所依赖的
> 全部第三方组件的许可证核实报告与合规声明。核实方式：直接抓取各上游仓库的
> `LICENSE`/`README` 原文与 Hugging Face 模型卡 license 元数据，逐项区分「代码 License」
> 与「模型权重 License」。许可文本全文已随仓库保存在 [`docs/licenses/`](./licenses/)。

## 1. 结论（先读这里）

**当前默认语音链路（whisper.cpp + Whisper 量化权重 + MeloTTS-Chinese）全部由 MIT / Apache-2.0
宽松许可证覆盖，可以免费用于商业产品与比赛，且允许 Edu_Agent 保持闭源。**

需要履行的义务只有一条：**在分发（公开仓库、比赛提交、产品发行包）时保留以下版权与许可声明**
（即保留 `docs/licenses/` 下的文本，勿删除），并在 README 之类的可见位置做第三方组件声明。

| 组件 | 用途 | 代码 License | 权重 License | 商用 | 闭源共存 |
|---|---|---|---|---|---|
| OpenAI Whisper（ggml 量化权重） | STT 模型 | MIT（`Copyright (c) 2022 OpenAI`） | **MIT**（README 明文覆盖 weights） | ✅ | ✅ |
| whisper.cpp | STT 推理引擎 | MIT（`Copyright (c) 2023-2026 The ggml authors`） | 随上游权重（MIT） | ✅ | ✅ |
| ggml（whisper.cpp 内置依赖） | 张量库 | MIT（同上版权行） | — | ✅ | ✅ |
| MeloTTS | TTS 引擎 | MIT（`Copyright (c) 2024 MyShell.ai`） | — | ✅ | ✅ |
| MeloTTS-Chinese（checkpoint.pth ≈208 MB） | TTS 中文声学模型 | — | **MIT**（HF 卡 `license: mit`） | ✅ | ✅ |
| bert-base-multilingual-uncased | MeloTTS 中文前端 BERT | — | **Apache-2.0** | ✅ | ✅ |
| torch / transformers / jieba / pypinyin / cn2an / g2p_en 等 | 运行时依赖 | BSD / Apache-2.0 / MIT | — | ✅ | ✅ |
| OpenCC（TSCharacters/TSPhrases 词典） | STT 转写繁→简兜底（vendored 于 `backend/app/voice/zh_t2s_*.txt`） | **Apache-2.0**（词典数据随库同证） | — | ✅ | ✅ |

## 2. 关键原文引用（核实于 2026-08-30）

- **Whisper 代码 + 权重同为 MIT** — README License 节原话：
  > "Whisper's code and model weights are released under the MIT License."
  来源：<https://raw.githubusercontent.com/openai/whisper/main/README.md>；
  LICENSE 全文：<https://raw.githubusercontent.com/openai/whisper/main/LICENSE>
- **whisper.cpp**：LICENSE 为 MIT（`Copyright (c) 2023-2026 The ggml authors`），
  <https://raw.githubusercontent.com/ggml-org/whisper.cpp/master/LICENSE>；
  其内置 ggml 同为 MIT，<https://raw.githubusercontent.com/ggml-org/ggml/master/LICENSE>。
  官方托管的 ggml 转换模型（如 `ggml-base-q5_1.bin`）发布在
  <https://huggingface.co/ggerganov/whisper.cpp>，仓库 license 元数据为 **MIT**——ggml
  转换只是对 MIT 权重的格式重打包，不引入新条款。
- **MeloTTS**：LICENSE 为 MIT（`Copyright (c) 2024 MyShell.ai`），
  <https://raw.githubusercontent.com/myshell-ai/MeloTTS/main/LICENSE>；README 原话：
  > "This library is under MIT License, which means it is free for both commercial and non-commercial use."
- **MeloTTS-Chinese 权重**：HF 卡 <https://huggingface.co/myshell-ai/MeloTTS-Chinese>
  license 字段为 `mit`，主文件 `checkpoint.pth` ≈207.8 MB。
- **中文模式实际下载的辅助模型**（源码链路已核实：`melo/api.py` `language='ZH'` →
  `ZH_MIX_EN` 前端 → `melo/text/chinese_mix.py` 调用
  `bert-base-multilingual-uncased`）：Google 发布，Apache-2.0，
  <https://huggingface.co/google-bert/bert-base-multilingual-uncased>。

## 3. 已排除/中和的许可风险点

MeloTTS 的完整依赖清单里混有 copyleft 组件。本项目的策略分两层（实施见
`deploy/install_voice.sh` 与 `backend/voice_sidecar/melo_bootstrap.py`）：

**（a）完全不安装（进程与部署物中零存在）：**

| 组件 | License | 处置 |
|---|---|---|
| `unidecode` | **GPL-2.0+**（PyPI 元数据，无例外条款） | MeloTTS 源码中**零 import**（继承自 Bert-VITS2 谱系的僵尸依赖），直接不装 |
| `pykakasi` | **GPLv3+** | 仅日语路径使用，但 `melo/text/japanese.py` 在**模块导入期**引用它 → `melo_bootstrap.py` 在导入 melo 之前向 `sys.modules` 注入行为安全的 stub，GPL 代码不进入进程 |
| `num2words` | **LGPL** | 同上，仅日/韩数字规范化使用，导入期被 stub 中和 |
| `unidic` 完整词典 | GPL/LGPL/BSD 三选（约 1 GB 磁盘） | 不装；改用 `unidic-lite`（见下） |
| `eng_to_ipa` | PyPI 无许可声明 | 未被中文路径 import，不装 |

**（b）导入期需要、中文合成不执行、但许可证全部宽松，正常安装：**
`melo/text/cleaner.py` 在 import 期聚合全部语言模块，因此以下包必须存在
（全部 MIT/BSD/Apache 系，磁盘开销小）：

| 组件 | License | 存在原因 |
|---|---|---|
| `mecab-python3` / `unidic-lite` | BSD / MIT+WTFPL（词典数据 BSD，仅约 15 MB） | `japanese.py` 模块级初始化 MeCab tagger |
| `fugashi` | MIT AND BSD-3-Clause | transformers 的日文 tokenizer 初始化 |
| `anyascii` / `jamo` | MIT / Apache-2.0 | `korean.py` 顶层导入 |
| `gruut` / `gruut_ipa` | MIT | 法/西语 phonemizer 顶层导入 |
| `nltk` + cmudict / averaged_perceptron_tagger 数据 | Apache-2.0 / cmudict 公有领域 | `g2p_en`（中英混读的英文单词音素化，**中文路径真实使用**）导入期加载 |

即：**最终运行进程内不含任何 GPL/LGPL/无许可声明的代码**；中文合成链路执行到的
每个包均为 MIT/BSD/Apache 宽松许可。

另有两点说明（不影响结论）：

1. Hugging Face 上 OpenAI 官方镜像 `openai/whisper-*` 的卡片元数据标的是
   `apache-2.0`，与 GitHub README 的 MIT 表述不一致。两者都是宽松许可（商用、闭源均可），
   本项目以 OpenAI 自己在 GitHub 仓库的 MIT 表述为准，并在 `docs/licenses/` 同时保留了
   MIT 文本。
2. Microsoft `deberta-v3` 官方模型卡为 MIT 且无 NC 条款；且** MeloTTS 全部源码不使用
   deberta**（英文模式用的也是 Apache-2.0 的 `bert-base-uncased`），与本链路无关。

## 4. 使用方式的合法性确认

- **商业产品**：MIT 与 Apache-2.0 均允许商业使用、修改、分发、集成进闭源产品，无登记或
  付费要求。唯一实质义务是在分发时保留原作者版权声明与许可文本（本文档 + `docs/licenses/`
  即为履行该义务）。
- **比赛**：无论评审是否公开代码，上述许可对比赛使用均无任何限制。
- **闭源**：使用 MIT/Apache 组件不触发开源传染，Edu_Agent 主体可保持闭源。
- **SaaS 形态**：仅在网络服务中调用（不分发二进制）时，MIT/Apache 连分发义务都不触发；
  保留声明是公开仓库（比赛提交）场景下的最佳实践。

## 5. 服务器资源评估（2 vCPU / 8 GB RAM / 8 GB 系统盘，无 GPU）

| 项 | 数字 | 结论 |
|---|---|---|
| 内存峰值 | whisper base 量化 ≈0.4 GB + MeloTTS 加载 ≈1.5–2.5 GB + 现有服务 ≈1 GB | 共约 3–4 GB，8 GB 充足 |
| 磁盘（精简安装） | whisper.cpp + base-q5_1 ≈0.3 GB；MeloTTS ZH 精简 ≈2.5–3 GB（CPU torch ≈1 GB、checkpoint 0.2 GB、BERT 0.7 GB） | 共约 3 GB；安装全程 `--no-cache-dir`，8 GB 系统盘可容纳 |
| STT 延迟 | base-q5_1 在 2 核约 3–6× 实时（AVX2 vCPU） | 10 秒语音约 2–4 秒转完 |
| TTS 延迟 | MeloTTS 在 2 核 RTF≈1–1.5（主要瓶颈） | 按句合成逐句推送，首句数秒内开播，电话式体感可用 |
| 并发 | 单用户/低并发 | 高并发需先升 CPU（4C）而非换模型 |

模型与引擎路径均可通过 `.env` 更换（如 `small-q5_1` 换更高中文准确率、未来替换
SenseVoice/CosyVoice 等），插件接口见 `backend/app/voice/`。

## 6. 声明义务清单（保留即合规）

分发本仓库或基于其构建的产品时，需保留以下文件：

1. `docs/licenses/whisper-MIT.txt` — Whisper 代码与权重（MIT, (c) 2022 OpenAI）
2. `docs/licenses/whisper.cpp-MIT.txt` — whisper.cpp（MIT, (c) 2023-2026 The ggml authors）
3. `docs/licenses/ggml-MIT.txt` — ggml（MIT, (c) 2023-2026 The ggml authors）
4. `docs/licenses/melotts-MIT.txt` — MeloTTS 代码与 MeloTTS-Chinese 权重（MIT, (c) 2024 MyShell.ai）
5. `docs/licenses/Apache-2.0.txt` — bert-base-multilingual-uncased 等 Apache-2.0 组件

README 的「第三方组件与许可证」小节指向本文档。
