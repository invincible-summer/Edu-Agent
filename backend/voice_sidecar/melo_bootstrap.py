"""挂载 MeloTTS 源码并中和其「导入期」的 copyleft 依赖（仅中文合成）。

MeloTTS 的 melo/text/cleaner.py 在 import 期聚合全部语言模块，其中
japanese.py / korean.py 顶层导入：

  - pykakasi（GPLv3+）：模块级还会调用 kakasi().setMode()/getConverter()
  - num2words（LGPL）：仅导入符号，函数内才调用

两者在中文（ZH/ZH_MIX_EN）合成路径上永远不会执行。这里在导入 melo 之前
向 sys.modules 注入行为安全的 stub，使 GPL/LGPL 代码完全不进入本进程，
仓库与部署物也就无需携带任何 copyleft 组件（docs/VOICE_LICENSES.md §3）。
真实安装的 mecab-python3 / unidic-lite / anyascii / jamo 均为宽松许可
（BSD/MIT），保留真实包。
"""
from __future__ import annotations

import os
import sys
import types

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
MELO_ROOT = os.environ.get("MELO_ROOT") or os.path.abspath(
    os.path.join(_THIS_DIR, "..", "vendor", "MeloTTS"))


class _KakasiConverterStub:
    def do(self, text: str) -> str:
        raise RuntimeError("pykakasi stub：日语路径未安装（中文合成不需要）")


class _KakasiStub:
    def setMode(self, *args, **kwargs) -> None:
        pass

    def getConverter(self) -> _KakasiStub:
        return _KakasiStub()


def _install_stubs() -> None:
    if "pykakasi" not in sys.modules:
        pykakasi = types.ModuleType("pykakasi")
        pykakasi.kakasi = _KakasiStub  # japanese.py 顶层 kakasi() 构造
        sys.modules["pykakasi"] = pykakasi
    if "num2words" not in sys.modules:
        def _num2words(*args, **kwargs):
            raise RuntimeError("num2words stub：日/韩数字规范化未安装（中文合成不需要）")
        num2words = types.ModuleType("num2words")
        num2words.num2words = _num2words
        sys.modules["num2words"] = num2words


def bootstrap() -> str:
    """把 MeloTTS 源码目录挂到 sys.path 并注入 stub；返回该目录。"""
    if os.path.isdir(MELO_ROOT) and MELO_ROOT not in sys.path:
        sys.path.insert(0, MELO_ROOT)
    _install_stubs()
    return MELO_ROOT
