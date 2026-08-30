# Edu_Agent 语音第三方声明

本文件配合 [`docs/VOICE_LICENSES.md`](../VOICE_LICENSES.md) 使用，列出当前默认语音安装方案中由项目主动管理的代码、模型和数据制品。它不是对动态 pip 依赖的替代清单；如果分发 sidecar venv 或容器镜像，应按实际 lock/SBOM 追加每个 wheel、系统库和 NOTICE。

## 默认 STT

- **OpenAI Whisper**：代码与官方模型权重按上游 README 的 MIT 表述核查。许可证全文：[`whisper-MIT.txt`](./whisper-MIT.txt)。
- **当前模型文件**：`backend/models/voice/whisper/ggml-small-q5_1.bin`，从 `ggerganov/whisper.cpp` 模型仓库获取；核查 revision：`5359861c739e955e79d9a303bcbc70fb988958b1`，上游文件 SHA：`6fe57ddcfdd1c6b07cdcc73aaf620810ce5fc771`。安装脚本还会输出本地 SHA-256。GGML 量化/格式转换不改变 Whisper 权利来源；发布时保留模型来源、revision 和 hash。
- **whisper.cpp**：CPU 推理引擎，核查 commit：`c4ac0012a8f5a2082dfca6aad4ddfd8b2c02b337`。许可证全文：[`whisper.cpp-MIT.txt`](./whisper.cpp-MIT.txt)。
- **ggml**：whisper.cpp 默认 CPU 构建使用的底层库，许可证全文：[`ggml-MIT.txt`](./ggml-MIT.txt)。

## 默认 TTS

- **MeloTTS**：代码，核查 commit：`209145371cff8fc3bd60d7be902ea69cbdb7965a`。许可证全文：[`melotts-MIT.txt`](./melotts-MIT.txt)。
- **MeloTTS-Chinese**：`checkpoint.pth` 等模型文件，核查 revision：`af5d207a364ea4208c6f589c89f57f88414bdd16`，模型卡标示 MIT。发布时保留模型仓库 README/许可信息。
- **bert-base-multilingual-uncased**：MeloTTS 中文前端实际读取的模型，核查 revision：`7cbf9a625e29989f6b9c6c2fa68234c304f7e38f`，模型卡标示 Apache-2.0。许可证全文：[`Apache-2.0.txt`](./Apache-2.0.txt)。

## Vendored 文字数据

- `backend/app/voice/zh_t2s_chars.txt`
- `backend/app/voice/zh_t2s_phrases.txt`

上述文件来自 OpenCC 的 `TSCharacters.txt` / `TSPhrases.txt`，文件头保留来源和 `Apache-2.0` 说明；核查上游 commit：`26753884f1984add422f3b0249ccee8613deaff6`。许可证全文：[`Apache-2.0.txt`](./Apache-2.0.txt)。这些数据只做繁体到简体文字规范化，不授予音频、用户内容或其他数据权利。

## sidecar 依赖声明

安装脚本只主动安装中文 sidecar 所需的依赖。当前核查的直接依赖及其来源许可证包括：

| 依赖/制品 | 许可证 | 本项目留档/注意 |
|---|---|---|
| `fastapi`、`pydantic`、`jieba`、`pypinyin`、`cn2an`、`gruut`、`gruut_ipa` | MIT | 分发 wheel/镜像时保留各自 `.dist-info` license |
| `transformers`、`cached-path`、`huggingface-hub`、`sentencepiece`、`jamo`、`nltk`、`g2p_en` | Apache-2.0 或 Apache Software License | 同时保留 Apache-2.0 文本及各包归属；实际包以 SBOM 为准 |
| `numpy`、`soundfile`、`mecab-python3`、`torchaudio` | BSD 系列 | 本仓库额外留档 `docs/licenses/BSD-3-Clause.txt`；`soundfile` 打包的 libsndfile/编解码器可能带独立 LGPL/BSD 条款 |
| `librosa` | ISC | 本仓库额外留档 `docs/licenses/ISC.txt`；其依赖仍需按实际 wheel 扫描 |
| `unidic-lite`、`anyascii`、`fugashi` | MIT、ISC、MIT AND BSD-3-Clause 等 | 各包 `.dist-info/licenses/` 是实际声明来源 |
| `torch` CPU wheel | 多许可证组合（包括 Apache-2.0、BSD、MIT、BSL 等） | 必须随实际 wheel 的 `licenses/` 和第三方目录分发，不能用本表替代完整归属 |
| `libsndfile` 及其编解码器 | 由 `soundfile` wheel 实际携带的 LGPL/BSD 等组件 | 若分发该 wheel/镜像，保留 wheel 中的 `COPYING`、license notes 和对应源/归属 |

动态解析的完整依赖仍必须在构建发布物时生成 SBOM。为便于默认 `soundfile` wheel 的合规归档，本目录另存 BSD-3-Clause、ISC 和 LGPL-2.1 文本；这些文件不表示所有动态依赖都只有这三种许可证。`unidecode`、`pykakasi`、`num2words` 和完整 `unidic` 不属于默认安装方案：前两者由安装策略排除/stub，完整 `unidic` 不安装。复用旧 venv 或启用其他 MeloTTS 语言前，必须重新扫描实际包和文件。

## 发布时的最小归档内容

发布 Docker 镜像、安装包、sidecar 或模型包时，至少携带：

1. 本目录中与发布物实际包含的组件对应的 MIT/Apache-2.0 全文；
2. 本声明文件和 `docs/VOICE_LICENSES.md`，或等价的可见第三方声明页；
3. 模型仓库附带的 README、LICENSE、NOTICE（如果存在）；
4. 动态 Python/系统依赖的版本化 SBOM 及其 license/NOTICE 文件；
5. 实际模型名称、量化格式、来源 revision/commit、文件 hash 和任何本地修改说明。
