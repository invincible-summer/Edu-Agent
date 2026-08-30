#!/usr/bin/env bash
# 语音组件安装脚本（许可证核实与合规声明：docs/VOICE_LICENSES.md）。
#
#   1. 编译 whisper.cpp        -> backend/vendor/whisper.cpp/build/bin/whisper-cli
#   2. 下载 Whisper 量化模型    -> backend/models/voice/whisper/ggml-<size>.bin
#   3. 建 MeloTTS sidecar venv  -> backend/voice_sidecar/.venv（中文精简依赖）
#   4. 克隆 MeloTTS 源码        -> backend/vendor/MeloTTS（sys.path 挂载，不 pip 安装）
#   5. 预下载中文 TTS 模型       -> backend/models/voice/hf（HF_HOME，之后离线运行）
#   6. 打印启用的 .env 片段
#
# 用法：
#   bash deploy/install_voice.sh                     # 默认 ggml-base-q5_1
#   VOICE_WHISPER_SIZE=small-q5_1 bash deploy/install_voice.sh
#
# 磁盘预算（2C8G/8GB 系统盘适用）：whisper.cpp+base-q5_1 约 0.3 GB；
# sidecar venv 约 1.5-2 GB；MeloTTS-Chinese + bert-base-multilingual-uncased
# 约 0.9 GB。全程 --no-cache-dir，不安装 unidic（省 1 GB，见许可证文档 §3）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
VENDOR="$BACKEND/vendor"
MODELS="$BACKEND/models/voice"
SIDECAR="$BACKEND/voice_sidecar"
WHISPER_SIZE="${VOICE_WHISPER_SIZE:-base-q5_1}"
PY="${PYTHON_BIN:-python3}"
JOBS="${JOBS:-2}"

log() { echo "[install_voice] $*"; }

need_cmd() {
    command -v "$1" &>/dev/null || { echo "缺少 $1，请先安装（apt install $2）" >&2; exit 1; }
}

# --------------------------------------------------------------------------
log "步骤 0/5：检查工具链"
need_cmd git "git"
need_cmd "$PY" "python3 python3.11-venv"
if command -v cmake &>/dev/null; then BUILD_TOOL="cmake"; else BUILD_TOOL="make"; fi
log "构建工具：$BUILD_TOOL"

# --------------------------------------------------------------------------
log "步骤 1/5：编译 whisper.cpp (MIT)"
if [ ! -d "$VENDOR/whisper.cpp/.git" ]; then
    git clone --depth 1 https://github.com/ggml-org/whisper.cpp "$VENDOR/whisper.cpp"
fi
(
    cd "$VENDOR/whisper.cpp"
    if [ "$BUILD_TOOL" = "cmake" ]; then
        cmake -B build -DCMAKE_BUILD_TYPE=Release >/dev/null
        cmake --build build --config Release -j"$JOBS" >/dev/null
    else
        make -j"$JOBS" >/dev/null
    fi
)
WHISPER_BIN="$(find "$VENDOR/whisper.cpp/build/bin" "$VENDOR/whisper.cpp" \
    -maxdepth 2 -type f -name whisper-cli 2>/dev/null | head -1 || true)"
if [ -z "$WHISPER_BIN" ]; then
    WHISPER_BIN="$(find "$VENDOR/whisper.cpp" -maxdepth 1 -type f -name main 2>/dev/null | head -1 || true)"
fi
[ -n "$WHISPER_BIN" ] || { echo "whisper.cpp 编译产物未找到" >&2; exit 1; }
log "whisper-cli: $WHISPER_BIN"

# --------------------------------------------------------------------------
log "步骤 2/5：下载 Whisper 模型 ggml-$WHISPER_SIZE.bin (MIT)"
mkdir -p "$MODELS/whisper"
MODEL_FILE="$MODELS/whisper/ggml-$WHISPER_SIZE.bin"
if [ ! -f "$MODEL_FILE" ]; then
    (cd "$VENDOR/whisper.cpp" && bash ./models/download-ggml-model.sh "$WHISPER_SIZE")
    mv "$VENDOR/whisper.cpp/models/ggml-$WHISPER_SIZE.bin" "$MODEL_FILE"
fi
log "模型: $MODEL_FILE ($(du -h "$MODEL_FILE" | cut -f1))"

# --------------------------------------------------------------------------
log "步骤 3/5：sidecar venv（CPU-only torch + 中文精简依赖）"
if [ ! -x "$SIDECAR/.venv/bin/python" ]; then
    "$PY" -m venv "$SIDECAR/.venv"
fi
PIP=("$SIDECAR/.venv/bin/python" -m pip install --no-cache-dir)
"${PIP[@]}" --upgrade pip -q
# torch/torchaudio CPU 版必须单独先装（requirements.txt 顶部有说明）。
"${PIP[@]}" torch torchaudio --index-url https://download.pytorch.org/whl/cpu -q
"${PIP[@]}" -r "$SIDECAR/requirements.txt" -q
log "sidecar venv 就绪 ($(du -sh "$SIDECAR/.venv" | cut -f1))"

# --------------------------------------------------------------------------
log "步骤 4/5：克隆 MeloTTS 源码并预下载中文模型 (MIT)"
if [ ! -d "$VENDOR/MeloTTS/.git" ]; then
    git clone --depth 1 https://github.com/myshell-ai/MeloTTS "$VENDOR/MeloTTS"
fi
mkdir -p "$MODELS/hf"
# g2p_en（英文单词音素化，ZH_MIX_EN 嵌英需要）在 import 期加载 NLTK 语料。
# nltk.download 走的 raw.githubusercontent 在部分网络下被代理拦截，curl
# 直连可用——三个包共约 5 MB（cmudict 公有领域 / tagger Apache 系）。
# 注意 NLTK >= 3.9 的 pos_tag 改用新命名 averaged_perceptron_tagger_eng，
# 旧名 averaged_perceptron_tagger 保留给 < 3.9。
mkdir -p "$SIDECAR/.venv/nltk_data/corpora" "$SIDECAR/.venv/nltk_data/taggers"
NLTK_BASE="https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages"
[ -f "$SIDECAR/.venv/nltk_data/corpora/cmudict.zip" ] || \
    curl -fsSL --max-time 120 "$NLTK_BASE/corpora/cmudict.zip" \
        -o "$SIDECAR/.venv/nltk_data/corpora/cmudict.zip" \
    || "$SIDECAR/.venv/bin/python" -m nltk.downloader cmudict averaged_perceptron_tagger
[ -f "$SIDECAR/.venv/nltk_data/taggers/averaged_perceptron_tagger.zip" ] || \
    curl -fsSL --max-time 120 "$NLTK_BASE/taggers/averaged_perceptron_tagger.zip" \
        -o "$SIDECAR/.venv/nltk_data/taggers/averaged_perceptron_tagger.zip" || true
[ -f "$SIDECAR/.venv/nltk_data/taggers/averaged_perceptron_tagger_eng.zip" ] || \
    curl -fsSL --max-time 120 "$NLTK_BASE/taggers/averaged_perceptron_tagger_eng.zip" \
        -o "$SIDECAR/.venv/nltk_data/taggers/averaged_perceptron_tagger_eng.zip" || true
# 让 melo 自己按它的缓存布局下载一次（checkpoint + bert-base-multilingual-
# uncased + 各语言 tokenizer，共约 0.9 GB）；运行期以 HF_HUB_OFFLINE=1
# 复用同一 HF_HOME。导入前先过 bootstrap（中和 GPL 系导入期依赖）。
cd "$SIDECAR"
MELO_ROOT="$VENDOR/MeloTTS" HF_HOME="$MODELS/hf" \
    ./.venv/bin/python - <<'PYEOF'
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath("app.py")))
from melo_bootstrap import bootstrap
bootstrap()
from melo.api import TTS
tts = TTS(language="ZH", device="cpu")
tts.tts_to_file(text="模型预下载完成。", speaker_id=tts.hps.data.spk2id["ZH"],
                output_path="/tmp/melo_warmup.wav", speed=1.0)
print("[install_voice] warmup synthesis OK")
PYEOF
log "TTS 模型缓存: $MODELS/hf ($(du -sh "$MODELS/hf" | cut -f1))"

# --------------------------------------------------------------------------
log "步骤 5/5：完成。把下面片段放进 $ROOT/.env 即可启用语音："
cat <<ENV

VOICE_STT_PROVIDER=whisper
VOICE_WHISPER_BIN=$WHISPER_BIN
VOICE_WHISPER_MODEL=$MODEL_FILE
VOICE_WHISPER_LANG=zh
VOICE_TTS_PROVIDER=melo
VOICE_TTS_BASE_URL=http://127.0.0.1:8130
ENV
log "然后 ./start.sh 正常启动（sidecar 会自动拉起）。"
