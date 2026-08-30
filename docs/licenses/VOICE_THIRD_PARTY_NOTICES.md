# Edu_Agent Voice Third-Party Notices

Audit date: **2026-08-30**. This notice covers the current browser-input voice
path and optional local MeloTTS sidecar. It is not a statement that the whole
voice stack is MIT, nor a substitute for the notices/SBOM of a shipped image.

## Runtime boundary

- Speech input uses browser `SpeechRecognition` / `webkitSpeechRecognition`.
  This is a platform API, not MIT software distributed by this repository.
  Browser/vendor recognition services have their own availability, privacy,
  regional, pricing, and commercial terms.
- Edu_Agent sends final recognized text to its backend; it does not upload call
  input PCM to that backend. The browser may still process audio remotely.
- Spoken output optionally uses a locally installed MeloTTS Chinese sidecar.
  Source, model caches, wheels, native libraries, and NLTK data are downloaded
  during deployment into gitignored directories.

## Pinned source and model assets

| Asset | Purpose | Pinned revision | License/notice |
|---|---|---|---|
| [MeloTTS](https://github.com/myshell-ai/MeloTTS) | TTS inference source | `209145371cff8fc3bd60d7be902ea69cbdb7965a` | MIT. Retain the upstream copyright and [`melotts-MIT.txt`](melotts-MIT.txt) when distributing source/substantial portions |
| [MeloTTS-Chinese](https://huggingface.co/myshell-ai/MeloTTS-Chinese) | TTS configuration and weights | `af5d207a364ea4208c6f589c89f57f88414bdd16` | Model metadata/card marks MIT. If redistributed, retain model card, README, license, revision and hashes; this label does not grant unrelated data/trademark rights |
| [`bert-base-multilingual-uncased`](https://huggingface.co/google-bert/bert-base-multilingual-uncased) | Chinese/mixed-English BERT features and tokenizer | `7cbf9a625e29989f6b9c6c2fa68234c304f7e38f` | Apache-2.0; retain model card, license, copyright and NOTICE if supplied |
| [`bert-base-uncased`](https://huggingface.co/google-bert/bert-base-uncased) | Mixed-English tokenizer | `86b5e0934494bd15c9632b12f734a8a67f723594` | Apache-2.0; retain model card and license for redistributed tokenizer files |

These model/source files are **not committed to this Git repository**. Downloading
them at deployment avoids repository redistribution, but does not waive their
license, attribution, model-card, data, trademark, privacy, or notice obligations.

## Direct sidecar dependencies

Exact versions are in `backend/voice_sidecar/requirements.txt`.

| Packages | License category / required boundary |
|---|---|
| `fastapi`, `pydantic` | MIT |
| `uvicorn` | BSD-3-Clause |
| `torch`, `torchaudio` | PyTorch/torchaudio distributions contain Apache-2.0, BSD-2/3-Clause, BSL-1.0, MIT and other bundled notices; preserve the actual wheel notices rather than labeling them only MIT |
| `transformers`, `huggingface_hub` | Apache-2.0 |
| `numpy`, `scipy`, `soundfile` | BSD-3-Clause plus actual binary-wheel/native notices; `soundfile` may carry an LGPL-2.1 `libsndfile` boundary |
| `librosa` | ISC |
| `tqdm` | MPL-2.0 AND MIT |
| `jieba`, `pypinyin`, `cn2an` | MIT |
| `g2p_en`, `nltk` | Apache-2.0; NLTK data retains its own terms |

NLTK's data index marks both averaged-perceptron tagger packages MIT. Its
CMUdict entry states research and commercial use is unrestricted and requests
acknowledgement of Carnegie Mellon University; preserve the accompanying data
README/attribution when redistributing it.

Resolved transitive packages and native libraries vary by target platform.
Before shipping a venv, container, VM, or offline bundle, preserve the actual
`LICENSE`, `COPYING`, `NOTICE`, `*.dist-info/licenses`, model-card and NLTK data
files and produce a versioned SBOM.

## Browser service notice

Compatibility information: [MDN SpeechRecognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition)
and the [Web Speech API draft](https://wicg.github.io/speech-api/#speechreco-section).
Review the terms/privacy policy of the browser actually deployed, including
[Google Terms](https://policies.google.com/terms),
[Google Privacy](https://policies.google.com/privacy),
[Microsoft Services Agreement](https://www.microsoft.com/en-us/servicesagreement),
and [Microsoft Privacy Statement](https://www.microsoft.com/en-us/privacy/privacystatement)
where applicable. Edu_Agent does not grant access to or promise free commercial
use of a browser vendor's recognition service.

For the repository/model audit procedure and complete release checklist, see
[`../VOICE_LICENSES.md`](../VOICE_LICENSES.md).
