"""agent/langfuse_client.py
Langfuse 追踪客户端。

设计原则：
  - 全部懒加载：import langfuse 仅在 LANGFUSE_ENABLED=true 时发生
  - 任何 Langfuse 操作失败均静默处理，绝不影响主业务
  - 提供 LangfuseTrace 上下文管理器，用于包裹单次分析调用
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

logger = logging.getLogger(__name__)

# 懒加载单例
_client: Any = None       # Langfuse 实例 or False（初始化失败）
_ready:  bool = False     # 是否已尝试过初始化


def _get_client() -> Optional[Any]:
    """懒加载并缓存 Langfuse 客户端（线程不安全，但 FastAPI 单进程场景无问题）。"""
    global _client, _ready

    from config.settings import settings  # noqa: PLC0415
    if not settings.LANGFUSE_ENABLED:
        return None

    if _ready:
        return _client if _client is not False else None

    _ready = True
    try:
        from langfuse import Langfuse  # noqa: PLC0415
        _client = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
        )
        logger.info(
            "[Langfuse] 客户端初始化成功 | host=%s",
            settings.LANGFUSE_HOST,
        )
    except ImportError:
        logger.warning(
            "[Langfuse] langfuse 包未安装，跳过追踪。"
            " 如需启用请 pip install langfuse --break-system-packages"
        )
        _client = False
    except Exception as exc:
        logger.warning("[Langfuse] 初始化失败，跳过追踪: %s", exc)
        _client = False

    return _client if _client is not False else None


# ── 上下文管理器 ──────────────────────────────────────────────────────────

class _NullTrace:
    """当 Langfuse 不可用时的空对象，所有方法均 noop。"""
    def start_llm(self, **_): pass
    def end_llm(self, **_):   pass
    def set_output(self, **_): pass
    def mark_error(self, **_): pass


class LangfuseTrace:
    """
    单次分析调用的 Langfuse 追踪对象。

    用法（context manager 风格）：
        with LangfuseTrace("analyze", {"text": text, "mode": mode}) as trace:
            trace.start_llm(model=settings.HUAWEI_MODEL, prompt=system_prompt)
            result = ...
            trace.end_llm(output=result)

    任何方法内部异常均被吞掉，不影响主流程。
    """

    def __init__(
        self,
        name:     str,
        input_kv: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._name     = name
        self._input    = input_kv
        self._metadata = metadata or {}
        self._trace     = None
        self._generation = None

    def __enter__(self) -> "LangfuseTrace":
        try:
            client = _get_client()
            if client:
                self._trace = client.trace(
                    name=self._name,
                    input=self._input,
                    metadata=self._metadata,
                )
        except Exception as exc:
            logger.debug("[Langfuse] trace.__enter__ 失败: %s", exc)
        return self

    def start_llm(
        self,
        model:  str,
        prompt: str,
        mode:   str = "",
    ) -> None:
        """记录 LLM generation 开始。"""
        try:
            if self._trace:
                self._generation = self._trace.generation(
                    name=f"llm_{mode or 'generate'}",
                    model=model,
                    input=prompt[:600],   # 截断，节省流量
                )
        except Exception as exc:
            logger.debug("[Langfuse] start_llm 失败: %s", exc)

    def end_llm(
        self,
        output:     Dict[str, Any],
        usage_dict: Optional[Dict[str, int]] = None,
    ) -> None:
        """记录 LLM generation 结束。"""
        try:
            if self._generation:
                self._generation.end(
                    output=str(output.get("reply", ""))[:600],
                    usage=usage_dict,
                )
        except Exception as exc:
            logger.debug("[Langfuse] end_llm 失败: %s", exc)

    def set_output(self, data: Dict[str, Any]) -> None:
        """更新 trace 级别的输出。"""
        try:
            if self._trace:
                self._trace.update(output=data)
        except Exception as exc:
            logger.debug("[Langfuse] set_output 失败: %s", exc)

    def mark_error(self, msg: str) -> None:
        try:
            if self._trace:
                self._trace.update(level="ERROR", status_message=msg)
        except Exception as exc:
            logger.debug("[Langfuse] mark_error 失败: %s", exc)

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type and self._trace:
                self.mark_error(str(exc_val))
        except Exception:
            pass
        return False   # 不吞掉异常，让上层处理


def flush() -> None:
    """服务关闭时 flush 所有未发送数据（在 shutdown_event 调用）。"""
    try:
        client = _get_client()
        if client:
            client.flush()
            logger.info("[Langfuse] flush 完成")
    except Exception as exc:
        logger.debug("[Langfuse] flush 失败: %s", exc)