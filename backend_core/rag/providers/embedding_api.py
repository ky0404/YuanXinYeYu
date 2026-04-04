"""rag/providers/embedding_api.py
调用远程 Embedding API（支持 OpenAI 兼容 & 华为云 MaaS 标准 embeddings），不使用任何本地模型。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import aiohttp

from config.settings import settings

logger = logging.getLogger(__name__)


def _get_provider() -> str:
    # settings 里不一定加了这个字段，用 getattr 保底
    return (getattr(settings, "EMBEDDING_PROVIDER", "") or "openai_compat").strip().lower()


def _parse_openai_compat(body: Dict[str, Any]) -> List[List[float]]:
    # OpenAI embeddings: {"data":[{"embedding":[...]}]}
    data = body.get("data")
    if not isinstance(data, list) or not data:
        raise ValueError("OpenAI-compat 响应缺少 data 列表")
    embs: List[List[float]] = []
    for item in data:
        if not isinstance(item, dict) or "embedding" not in item:
            raise ValueError("OpenAI-compat data[i] 缺少 embedding")
        embs.append(item["embedding"])
    return embs


def _parse_huawei_maas(body: Dict[str, Any]) -> List[List[float]]:
    """
    华为云 MaaS embeddings 返回结构可能因版本不同略有差异：
    - 可能仍是 data[i].embedding
    - 可能是 embeddings: [[...], [...]]
    - 可能是 output / result 等字段
    我们做“多分支兼容解析”，拿到 float 向量即返回。
    """
    # 1) 最理想：data[i].embedding（有些实现确实这么返回）
    if isinstance(body.get("data"), list) and body["data"]:
        try:
            return _parse_openai_compat(body)
        except Exception:
            pass

    # 2) embeddings: [[...], ...]
    if isinstance(body.get("embeddings"), list) and body["embeddings"]:
        if isinstance(body["embeddings"][0], list):
            return body["embeddings"]

    # 3) output: {"embeddings":[...]} 或 {"data":[...]}
    output = body.get("output")
    if isinstance(output, dict):
        if isinstance(output.get("embeddings"), list) and output["embeddings"]:
            if isinstance(output["embeddings"][0], list):
                return output["embeddings"]
        if isinstance(output.get("data"), list) and output["data"]:
            # 可能 output.data[i].embedding
            try:
                return _parse_openai_compat(output)  # type: ignore[arg-type]
            except Exception:
                pass

    # 4) result: {"embeddings":...}
    result = body.get("result")
    if isinstance(result, dict):
        if isinstance(result.get("embeddings"), list) and result["embeddings"]:
            if isinstance(result["embeddings"][0], list):
                return result["embeddings"]

    raise ValueError(f"华为 MaaS embeddings 响应格式未识别: keys={list(body.keys())}")


async def get_embeddings(texts: List[str]) -> List[List[float]]:
    """批量调用 Embedding API，返回 embeddings: List[List[float]]"""
    if not settings.EMBEDDING_API_KEY:
        raise ValueError("EMBEDDING_API_KEY 未配置，无法调用 Embedding API")
    if not settings.EMBEDDING_API_BASE:
        raise ValueError("EMBEDDING_API_BASE 未配置，无法调用 Embedding API")

    provider = _get_provider()
    url = f"{settings.EMBEDDING_API_BASE.rstrip('/')}/embeddings"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.EMBEDDING_API_KEY}",
    }

    payload: Dict[str, Any] = {
        "model": settings.EMBEDDING_MODEL,
        "input": texts,
    }

    # 华为 MaaS 标准接口推荐带 encoding_format
    if provider in ("huawei_maas", "maas", "huaweimaas"):
        payload["encoding_format"] = "float"

    timeout = aiohttp.ClientTimeout(total=int(settings.EMBEDDING_TIMEOUT))
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            raw_text = await resp.text()
            if resp.status >= 400:
                raise ValueError(f"Embedding API HTTP {resp.status}: {raw_text[:400]}")
            body = await resp.json(content_type=None)

    try:
        if provider in ("huawei_maas", "maas", "huaweimaas"):
            embeddings = _parse_huawei_maas(body)
        else:
            embeddings = _parse_openai_compat(body)
    except Exception as exc:
        logger.error("[EmbeddingAPI] parse_failed provider=%s body=%s", provider, str(body)[:500])
        raise

    if embeddings and isinstance(embeddings[0], list):
        logger.debug(
            "[EmbeddingAPI] provider=%s model=%s texts=%d dims=%d",
            provider, settings.EMBEDDING_MODEL, len(texts), len(embeddings[0]),
        )
    return embeddings


async def get_single_embedding(text: str) -> List[float]:
    results = await get_embeddings([text])
    return results[0]