#!/usr/bin/env bash
# Prepare the browser-input voice stack: MeloTTS sidecar only.
# License and third-party notices: docs/VOICE_LICENSES.md.
#
# Browser Speech Recognition is provided by the browser and is not installed
# or uploaded by this script. The backend receives final text only; this
# script installs the local TTS service used for spoken replies.
#
#   1. Create backend/voice_sidecar/.venv
#   2. Install CPU-only PyTorch and the audited Chinese TTS dependencies
#   3. Checkout the pinned MeloTTS source
#   4. Warm up the MeloTTS-Chinese model cache
#   5. Print the TTS .env fragment
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
VENDOR="$BACKEND/vendor"
MODELS="$BACKEND/models/voice"
SIDECAR="$BACKEND/voice_sidecar"
MELO_REF="${VOICE_MELO_REF:-209145371cff8fc3bd60d7be902ea69cbdb7965a}"
PY="${PYTHON_BIN:-python3}"

log() { echo "[install_voice] $*"; }

need_cmd() {
    command -v "$1" &>/dev/null || {
        echo "缺少 $1，请先安装（apt install $2）" >&2
        exit 1
    }
}

checkout_revision() {
    local url="$1" repo="$2" revision="$3"
    if [ ! -d "$repo/.git" ]; then
        git clone --filter=blob:none --no-checkout "$url" "$repo"
    fi
    if ! git -C "$repo" cat-file -e "$revision^{commit}" 2>/dev/null; then
        git -C "$repo" fetch --depth=1 origin "$revision"
    fi
    git -C "$repo" checkout --force --detach "$revision"
}

# --------------------------------------------------------------------------
log "步骤 1/4：检查工具链"
need_cmd git "git"
need_cmd curl "curl"
need_cmd "$PY" "python3 python3.11-venv"
mkdir -p "$VENDOR" "$MODELS/hf"

# Clean model caches from the upstream all-language import path. The guarded
# bootstrap below needs only MeloTTS-Chinese, bert-base-multilingual-uncased,
# and the bert-base-uncased tokenizer for embedded English text.
for repo_id in \
    models--dbmdz--bert-base-french-europeana-cased \
    models--dccuchile--bert-base-spanish-wwm-uncased \
    models--tohoku-nlp--bert-base-japanese-v3 \
    models--kykim--bert-kor-base; do
    rm -rf "$MODELS/hf/hub/$repo_id" "$MODELS/hf/hub/.locks/$repo_id"
done

# --------------------------------------------------------------------------
log "步骤 2/4：sidecar venv（CPU-only torch + 已审计中文依赖）"
if [ ! -x "$SIDECAR/.venv/bin/python" ]; then
    "$PY" -m venv "$SIDECAR/.venv"
fi
PIP=("$SIDECAR/.venv/bin/python" -m pip install --no-cache-dir)
"${PIP[@]}" --upgrade pip -q
"${PIP[@]}" torch torchaudio --index-url https://download.pytorch.org/whl/cpu -q
"${PIP[@]}" -r "$SIDECAR/requirements.txt" -q
# These packages belong only to unused non-Chinese MeloTTS language paths.
# melo_bootstrap supplies fail-loud stubs for the Chinese-only service, so
# reused virtualenvs do not accidentally retain those language packages.
"$SIDECAR/.venv/bin/python" -m pip uninstall --yes num2words pykakasi mecab-python3 unidic-lite anyascii jamo gruut gruut-ipa g2pkk eng_to_ipa unidecode -q 2>/dev/null || true
log "sidecar venv 就绪 ($(du -sh "$SIDECAR/.venv" | cut -f1))"

# --------------------------------------------------------------------------
log "步骤 3/4：检出 MeloTTS 源码并预下载中文模型"
checkout_revision \
    https://github.com/myshell-ai/MeloTTS \
    "$VENDOR/MeloTTS" "$MELO_REF"
log "MeloTTS revision: $(git -C "$VENDOR/MeloTTS" rev-parse HEAD)"

# g2p_en loads NLTK data during import for mixed Chinese/English text.
mkdir -p "$SIDECAR/.venv/nltk_data/corpora" "$SIDECAR/.venv/nltk_data/taggers"
NLTK_BASE="https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages"
[ -f "$SIDECAR/.venv/nltk_data/corpora/cmudict.zip" ] || \
    curl -fsSL --max-time 120 "$NLTK_BASE/corpora/cmudict.zip" \
        -o "$SIDECAR/.venv/nltk_data/corpora/cmudict.zip" \
    || "$SIDECAR/.venv/bin/python" -m nltk.downloader cmudict
[ -f "$SIDECAR/.venv/nltk_data/taggers/averaged_perceptron_tagger.zip" ] || \
    curl -fsSL --max-time 120 "$NLTK_BASE/taggers/averaged_perceptron_tagger.zip" \
        -o "$SIDECAR/.venv/nltk_data/taggers/averaged_perceptron_tagger.zip" || true
[ -f "$SIDECAR/.venv/nltk_data/taggers/averaged_perceptron_tagger_eng.zip" ] || \
    curl -fsSL --max-time 120 "$NLTK_BASE/taggers/averaged_perceptron_tagger_eng.zip" \
        -o "$SIDECAR/.venv/nltk_data/taggers/averaged_perceptron_tagger_eng.zip" || true

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
tts.tts_to_file(
    text="模型预下载完成。",
    speaker_id=tts.hps.data.spk2id["ZH"],
    output_path="/tmp/melo_warmup.wav",
    speed=1.0,
)
print("[install_voice] warmup synthesis OK")
PYEOF
log "TTS 模型缓存: $MODELS/hf ($(du -sh "$MODELS/hf" | cut -f1))"

# --------------------------------------------------------------------------
log "步骤 4/4：完成。将以下片段放入 $ROOT/.env 以启用 MeloTTS："
cat <<ENV

# STT is always browser Speech Recognition; no server STT is installed.
VOICE_TTS_PROVIDER=melo
VOICE_TTS_BASE_URL=http://127.0.0.1:8130
ENV
log "然后 ./start.sh 正常启动（sidecar 会自动拉起）。"
