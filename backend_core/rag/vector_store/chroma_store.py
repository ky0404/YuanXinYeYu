"""rag/vector_store/chroma_store.py
ChromaDB 向量存储，使用 API Embedding（无本地模型）。
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from config.settings import settings
from rag.types import RagDoc

logger = logging.getLogger(__name__)

_client = None
_collection = None
_VECTOR_MIN_SIM = 0.15  # 余弦相似度阈值


def _get_client():
    """懒加载 ChromaDB PersistentClient。"""
    global _client
    if _client is None:
        import chromadb  # noqa: PLC0415
        os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        logger.info("[VectorStore] ChromaDB 初始化 | dir=%s", settings.CHROMA_PERSIST_DIR)
    return _client


def _get_collection():
    global _collection
    if _collection is None:
        client = _get_client()
        _collection = client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("[VectorStore] collection=%s count=%d",
                    settings.CHROMA_COLLECTION, _collection.count())
    return _collection


async def add_documents(
    doc_ids: List[str],
    texts:   List[str],
    metadatas: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """
    添加/更新文档（upsert）。
    Embedding 通过 API 获取，不使用本地模型。
    """
    from rag.providers.embedding_api import get_embeddings  # noqa: PLC0415

    embeddings = await get_embeddings(texts)
    col = _get_collection()
    metas = metadatas or [{} for _ in texts]
    col.upsert(
        ids=doc_ids,
        documents=texts,
        embeddings=embeddings,
        metadatas=metas,
    )
    logger.info("[VectorStore] upsert %d docs", len(doc_ids))


async def query(query_text: str, top_k: int = 4) -> List[RagDoc]:
    """
    向量检索，返回相似度 ≥ 阈值的 RagDoc 列表。
    """
    from rag.providers.embedding_api import get_single_embedding  # noqa: PLC0415

    col = _get_collection()
    if col.count() == 0:
        logger.debug("[VectorStore] 集合为空，跳过检索")
        return []

    query_vec = await get_single_embedding(query_text)
    n = min(top_k, col.count())

    results = col.query(
        query_embeddings=[query_vec],
        n_results=n,
        include=["documents", "metadatas", "distances"],
    )

    docs: List[RagDoc] = []
    for i, (text, meta, dist) in enumerate(zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    )):
        sim = max(0.0, 1.0 - float(dist))
        if sim < _VECTOR_MIN_SIM:
            continue
        docs.append(RagDoc(
            doc_id=results["ids"][0][i],
            text=text,
            score=round(sim, 4),
            source="vector",
            metadata=meta or {},
        ))

    docs.sort(key=lambda d: d.score, reverse=True)
    logger.info("[VectorStore] query hits=%d top_sim=%.3f",
                len(docs), docs[0].score if docs else 0)
    return docs[:top_k]


def get_count() -> int:
    try:
        return _get_collection().count()
    except Exception:
        return 0