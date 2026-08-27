"""统一原生多模态通道（NATIVE_MULTIMODAL_*）契约。

一个原生多模态模型（如 glm-5.3-flash）同时接管主 LLM 与视觉/OCR 通道：
  - _resolve_native_channel 纯解析（key+model 双非空才生效）；
  - Settings 字段接管与 GLM-5.3 系能力默认翻转（reload config 重建类体
    默认值；显式 env 永远可以覆盖自动默认）；
  - _vision_once 在原生通道下不再下发 thinking.type=disabled（GLM-5.3 系
    仅支持 enabled），仅保留最低思考强度；
  - AsyncLLMClient stream/complete 的 clear_thinking / tool_stream /
    disable_thinking 能力门控。

存储沙箱按 AGENTS.md 规范继承 StorageSandboxTestCase（本文件不落盘，
仅防御性兜底）。
"""
from __future__ import annotations

import importlib
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests.storage_sandbox import StorageSandboxTestCase  # noqa: E402


def _reload_with_env(extra: dict):
    """patch 环境变量后 reload app.core.config，返回重载后的模块。

    dataclass 字段默认值在类体执行期求值，只能靠 reload 重建。注意：reload
    会把 ``config.settings`` 重绑到新对象——若不还原 identity，后续测试里
    storage_sandbox 会 patch 到新对象，而早先 ``from .config import settings``
    的消费者仍持旧对象，沙箱即写穿生产目录。因此用方必须在 cleanup 中把
    ``config.settings`` 赋回原对象（见 TestSettingsTakeover.setUp）。
    """
    from app.core import config
    with patch.dict(os.environ, extra, clear=False):
        return importlib.reload(config)


class TestResolveNativeChannel(StorageSandboxTestCase):
    def test_full_channel_configured(self):
        from app.core.config import _resolve_native_channel
        out = _resolve_native_channel({
            "NATIVE_MULTIMODAL_BASE_URL": "https://native.example/v1",
            "NATIVE_MULTIMODAL_API_KEY": "nk",
            "NATIVE_MULTIMODAL_MODEL": "glm-5.3-flash",
        })
        self.assertTrue(out["configured"])
        self.assertEqual(out["base_url"], "https://native.example/v1")
        self.assertEqual(out["api_key"], "nk")
        self.assertEqual(out["model"], "glm-5.3-flash")

    def test_key_or_model_missing_means_off(self):
        from app.core.config import _resolve_native_channel
        base = {"NATIVE_MULTIMODAL_BASE_URL": "https://native.example/v1"}
        for env in (
            {**base, "NATIVE_MULTIMODAL_API_KEY": "nk"},
            {**base, "NATIVE_MULTIMODAL_MODEL": "glm-5.3-flash"},
            {},
        ):
            out = _resolve_native_channel(env)
            self.assertFalse(out["configured"])
            # 未生效时三字段强制为空：填了 model/base 但 key 留空也不允许
            # 穿透 or-链混入旧通道（key 走旧端点 / 旧 key 配新模型的串台）。
            self.assertEqual(out, {"base_url": "", "api_key": "", "model": "",
                                   "configured": False})

    def test_partial_fill_never_leaks_into_legacy_channels(self):
        # 真实场景：base/model 已填、key 留占位——必须完全回落旧双通道。
        mod = _reload_with_env({
            "NATIVE_MULTIMODAL_BASE_URL": "https://native.example/v1",
            "NATIVE_MULTIMODAL_API_KEY": "",
            "NATIVE_MULTIMODAL_MODEL": "glm-5.3-flash",
            "LLM_BASE_URL": "https://legacy.example/v1",
            "LLM_API_KEY": "lk",
            "LLM_MODEL": "legacy-text",
            "MULTIMODAL_BASE_URL": "https://vis.example/v1",
            "MULTIMODAL_API_KEY": "vk",
            "MULTIMODAL_MODEL": "legacy-vision",
        })
        s = mod.settings
        self.assertFalse(s.native_multimodal_configured)
        self.assertEqual(s.llm_model, "legacy-text")
        self.assertEqual(s.llm_base_url, "https://legacy.example/v1")
        self.assertEqual(s.llm_api_key, "lk")
        self.assertEqual(s.multimodal_model, "legacy-vision")
        self.assertEqual(s.multimodal_base_url, "https://vis.example/v1")
        self.assertEqual(s.multimodal_api_key, "vk")
        self.assertTrue(s.llm_supports_disable_thinking)
        self.assertIsNone(s.llm_thinking_clear)
        self.assertFalse(s.llm_tool_stream)

    def test_values_are_stripped(self):
        from app.core.config import _resolve_native_channel
        out = _resolve_native_channel({
            "NATIVE_MULTIMODAL_BASE_URL": "  https://native.example/v1  ",
            "NATIVE_MULTIMODAL_API_KEY": " nk ",
            "NATIVE_MULTIMODAL_MODEL": " glm-5.3-flash ",
        })
        self.assertTrue(out["configured"])
        self.assertEqual(out["api_key"], "nk")
        self.assertEqual(out["model"], "glm-5.3-flash")


class TestSettingsTakeover(StorageSandboxTestCase):
    """原生通道生效时 llm_*/multimodal_* 同时指向该通道，能力默认翻转。"""

    _NATIVE = {
        "NATIVE_MULTIMODAL_BASE_URL": "https://native.example/v1",
        "NATIVE_MULTIMODAL_API_KEY": "nk",
        "NATIVE_MULTIMODAL_MODEL": "glm-5.3-flash",
    }
    _LEGACY = {
        "LLM_BASE_URL": "https://legacy.example/v1",
        "LLM_API_KEY": "lk",
        "LLM_MODEL": "legacy-text",
        "MULTIMODAL_BASE_URL": "https://vis.example/v1",
        "MULTIMODAL_API_KEY": "vk",
        "MULTIMODAL_MODEL": "legacy-vision",
    }

    def setUp(self):
        super().setUp()
        from app.core import config
        self._config = config
        self._original_settings = config.settings
        self.addCleanup(self._restore_settings_identity)

    def _restore_settings_identity(self):
        self._config.settings = self._original_settings

    def test_native_channel_takes_over_both_channels(self):
        mod = _reload_with_env({**self._LEGACY, **self._NATIVE})
        s = mod.settings
        self.assertTrue(s.native_multimodal_configured)
        # 主 LLM 通道被接管（LLM_*/DEEPSEEK_* 被忽略）
        self.assertEqual(s.llm_base_url, "https://native.example/v1")
        self.assertEqual(s.llm_api_key, "nk")
        self.assertEqual(s.llm_model, "glm-5.3-flash")
        # 视觉/OCR 通道被接管（MULTIMODAL_* 被忽略）
        self.assertEqual(s.multimodal_base_url, "https://native.example/v1")
        self.assertEqual(s.multimodal_api_key, "nk")
        self.assertEqual(s.multimodal_model, "glm-5.3-flash")
        # GLM-5.3 系自动适配：思考不可关闭、effort 支持、OCR 不再请求关思考
        self.assertFalse(s.llm_supports_disable_thinking)
        self.assertTrue(s.llm_supports_reasoning_effort)
        self.assertFalse(s.multimodal_disable_thinking)
        self.assertFalse(s.llm_thinking_clear)
        self.assertTrue(s.llm_tool_stream)

    def test_explicit_env_overrides_native_defaults(self):
        mod = _reload_with_env({**self._NATIVE,
                                "LLM_SUPPORTS_DISABLE_THINKING": "1",
                                "LLM_SUPPORTS_REASONING_EFFORT": "0",
                                "MULTIMODAL_DISABLE_THINKING": "1",
                                "LLM_THINKING_CLEAR": "1",
                                "LLM_TOOL_STREAM": "0"})
        s = mod.settings
        self.assertTrue(s.llm_supports_disable_thinking)
        self.assertFalse(s.llm_supports_reasoning_effort)
        self.assertTrue(s.multimodal_disable_thinking)
        self.assertTrue(s.llm_thinking_clear)
        self.assertFalse(s.llm_tool_stream)

    def test_unset_native_keeps_legacy_dual_channel(self):
        mod = _reload_with_env({**self._LEGACY,
                                "NATIVE_MULTIMODAL_BASE_URL": "",
                                "NATIVE_MULTIMODAL_API_KEY": "",
                                "NATIVE_MULTIMODAL_MODEL": ""})
        s = mod.settings
        self.assertFalse(s.native_multimodal_configured)
        self.assertEqual(s.llm_base_url, "https://legacy.example/v1")
        self.assertEqual(s.llm_api_key, "lk")
        self.assertEqual(s.llm_model, "legacy-text")
        self.assertEqual(s.multimodal_base_url, "https://vis.example/v1")
        self.assertEqual(s.multimodal_api_key, "vk")
        self.assertEqual(s.multimodal_model, "legacy-vision")
        # 与历史行为逐字段一致
        self.assertTrue(s.llm_supports_disable_thinking)
        self.assertFalse(s.llm_supports_reasoning_effort)
        self.assertTrue(s.multimodal_disable_thinking)
        self.assertIsNone(s.llm_thinking_clear)
        self.assertFalse(s.llm_tool_stream)

    def test_unset_native_keeps_deepseek_aliases(self):
        mod = _reload_with_env({
            "NATIVE_MULTIMODAL_BASE_URL": "",
            "NATIVE_MULTIMODAL_API_KEY": "",
            "NATIVE_MULTIMODAL_MODEL": "",
            "LLM_BASE_URL": "", "LLM_API_KEY": "", "LLM_MODEL": "",
            "DEEPSEEK_BASE_URL": "https://ds.example/v1",
            "DEEPSEEK_API_KEY": "dk",
            "DEEPSEEK_MODEL_REASONING": "ds-reason",
        })
        s = mod.settings
        self.assertEqual(s.llm_base_url, "https://ds.example/v1")
        self.assertEqual(s.llm_api_key, "dk")
        self.assertEqual(s.llm_model, "ds-reason")

    def test_native_empty_base_falls_back_to_llm_base(self):
        mod = _reload_with_env({**self._LEGACY,
                                "NATIVE_MULTIMODAL_BASE_URL": "",
                                "NATIVE_MULTIMODAL_API_KEY": "nk",
                                "NATIVE_MULTIMODAL_MODEL": "glm-5.3-flash"})
        s = mod.settings
        self.assertTrue(s.native_multimodal_configured)
        # base 留空：主通道回落 LLM_BASE_URL，视觉通道保持空串
        # （ocr.py / get_multimodal_llm 消费端各自再回落 llm_base_url）。
        self.assertEqual(s.llm_base_url, "https://legacy.example/v1")
        self.assertEqual(s.llm_api_key, "nk")
        self.assertEqual(s.multimodal_base_url, "")
        self.assertEqual(s.multimodal_api_key, "nk")


class _FakeCompletions:
    def __init__(self, response_builder):
        self.captured: list[dict] = []
        self._response_builder = response_builder

    async def create(self, **kwargs):
        self.captured.append(kwargs)
        return self._response_builder()


def _stream_response():
    async def agen():
        yield SimpleNamespace(
            usage=None,
            choices=[SimpleNamespace(
                finish_reason="stop",
                delta=SimpleNamespace(content="ok", reasoning_content=None,
                                      tool_calls=None))])
    return agen()


def _complete_response():
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        usage=None)


class TestVisionOnceControls(StorageSandboxTestCase):
    """_vision_once：原生通道下 OCR 只发 reasoning_effort=low。"""

    def _run(self):
        from app.core import ocr
        fake = SimpleNamespace(
            chat=SimpleNamespace(completions=_FakeCompletions(_complete_response)))
        text = None

        async def call():
            nonlocal text
            text = await ocr._vision_once(fake, "m", "prompt", "AAAA")

        import asyncio
        asyncio.run(call())
        return text, fake.chat.completions.captured

    def test_native_channel_sends_effort_only(self):
        from app.core import ocr
        with patch.object(ocr.settings, "native_multimodal_configured", True), \
                patch.object(ocr.settings, "multimodal_disable_thinking", True):
            text, captured = self._run()
        self.assertEqual(text, "ok")
        self.assertEqual(captured[0]["extra_body"], {"reasoning_effort": "low"})

    def test_non_native_channel_sends_disable_thinking(self):
        from app.core import ocr
        with patch.object(ocr.settings, "native_multimodal_configured", False), \
                patch.object(ocr.settings, "multimodal_disable_thinking", True):
            _, captured = self._run()
        self.assertEqual(captured[0]["extra_body"],
                         {"reasoning_effort": "low",
                          "thinking": {"type": "disabled"}})

    def test_disable_thinking_off_sends_nothing(self):
        from app.core import ocr
        with patch.object(ocr.settings, "native_multimodal_configured", True), \
                patch.object(ocr.settings, "multimodal_disable_thinking", False):
            _, captured = self._run()
        self.assertNotIn("extra_body", captured[0])


class TestLLMRequestControls(StorageSandboxTestCase):
    """AsyncLLMClient：clear_thinking / tool_stream / disable_thinking 门控。"""

    def _client(self, response_builder):
        from app.core.llm_async import AsyncLLMClient
        c = AsyncLLMClient()
        fake = _FakeCompletions(response_builder)
        c.client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
        return c, fake

    def _collect(self, agen):
        import asyncio
        out = []
        async def drain():
            async for ev in agen:
                out.append(ev)
        asyncio.run(drain())
        return out

    def test_stream_sends_clear_thinking_and_tool_stream(self):
        from app.core.llm_async import settings
        with patch.object(settings, "llm_thinking_clear", False), \
                patch.object(settings, "llm_tool_stream", True), \
                patch.object(settings, "llm_supports_disable_thinking", False):
            client, fake = self._client(_stream_response)
            events = self._collect(client.stream(
                [{"role": "user", "content": "hi"}],
                tools=[{"type": "function", "function": {"name": "f"}}]))
        self.assertTrue(any(e["kind"] == "done" for e in events))
        self.assertEqual(fake.captured[0]["extra_body"],
                         {"thinking": {"type": "enabled", "clear_thinking": False},
                          "tool_stream": True})

    def test_stream_budget_merges_clear_thinking(self):
        from app.core.llm_async import settings
        with patch.object(settings, "llm_thinking_clear", False), \
                patch.object(settings, "llm_tool_stream", False):
            client, fake = self._client(_stream_response)
            self._collect(client.stream([{"role": "user", "content": "hi"}],
                                        reasoning_budget_tokens=1000))
        self.assertEqual(fake.captured[0]["extra_body"],
                         {"thinking": {"type": "enabled", "budget_tokens": 1000,
                                       "clear_thinking": False}})

    def test_stream_disable_thinking_gated_by_capability(self):
        from app.core.llm_async import settings
        # 支持关思考（历史默认）：照常下发 disabled
        with patch.object(settings, "llm_thinking_clear", None), \
                patch.object(settings, "llm_supports_disable_thinking", True):
            client, fake = self._client(_stream_response)
            self._collect(client.stream([{"role": "user", "content": "hi"}],
                                        disable_thinking=True))
        self.assertEqual(fake.captured[0]["extra_body"],
                         {"thinking": {"type": "disabled"}})
        # 不支持（GLM-5.3 系原生通道默认）：本地跳过，不吃 400 往返
        with patch.object(settings, "llm_thinking_clear", None), \
                patch.object(settings, "llm_supports_disable_thinking", False):
            client, fake = self._client(_stream_response)
            self._collect(client.stream([{"role": "user", "content": "hi"}],
                                        disable_thinking=True))
        self.assertNotIn("extra_body", fake.captured[0])

    def test_complete_sends_clear_thinking(self):
        from app.core.llm_async import settings
        with patch.object(settings, "llm_thinking_clear", False), \
                patch.object(settings, "llm_tool_stream", True):
            client, fake = self._client(_complete_response)
            import asyncio
            content, usage = asyncio.run(client.complete(
                [{"role": "user", "content": "hi"}]))
        self.assertEqual(content, "ok")
        self.assertEqual(fake.captured[0]["extra_body"],
                         {"thinking": {"type": "enabled", "clear_thinking": False}})


if __name__ == "__main__":
    unittest.main()
