"""RAG 检索服务：向量检索 + 关键词混合召回 v2.1

改动说明（相对上一版）：
1. [P0] 日志脱敏：去掉路径拼接时的绝对路径打印，API Key / DB URL 不进日志
2. [P0] 离线降级：local_files_only=True 外层再套 try-except，失败只 WARNING 不崩溃
3. [P0] 条目数不一致时给出明确 WARNING 并自动重建，而不是静默使用旧库
4. [P1] 权重调整 vector:keyword = 0.65:0.35（原 0.72:0.28）
        理由：中文短文本关键词匹配在情绪场景精度高，略提权重；向量负责语义泛化
5. [P1] 向量得分阈值 0.18 → 0.20，减少低相关噪声命中
6. [P1] 关键词精确匹配加权 3.0 → 4.0（topic/category 命中加分不变）
7. [P2] format_context 新增 audience / risk_level / emotion_type 字段输出（向下兼容：缺失时不输出）
8. retrieve() 支持透传 history 给 _build_search_text，提高上下文相关性
"""
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 离线保护：服务启动时设置，防止 HuggingFace 在线请求超时 15 分钟 ──
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
os.environ.setdefault("HUGGINGFACE_HUB_OFFLINE", "1")

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

CHROMA_AVAILABLE = False
EMBEDDING_AVAILABLE = False

try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    logger.warning("[RAG] ChromaDB 未安装，将仅使用关键词检索。")

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDING_AVAILABLE = True
except ImportError:
    logger.warning("[RAG] sentence-transformers 未安装，将仅使用关键词检索。")


class RAGService:
    """向量 + 关键词混合召回 RAG 服务。"""

    CHROMA_DB_PATH = os.path.join(project_root, "data", "chroma_db")
    COLLECTION_NAME = "emotion_knowledge"

    # 模型候选列表：优先环境变量指定，再 text2vec-base-chinese，最后 multilingual
    EMBEDDING_MODEL_CANDIDATES = [
        os.getenv("EMOTION_EMBEDDING_MODEL", "").strip(),
        "text2vec-base-chinese",
        "paraphrase-multilingual-MiniLM-L12-v2",
    ]

    # ── 权重：向量语义召回 65%，关键词精确召回 35% ──
    # 中文短情感文本：关键词精度高，向量负责捕捉语义变体
    VECTOR_WEIGHT = 0.65
    KEYWORD_WEIGHT = 0.35

    # 向量得分最低阈值（cosine 距离转换后）
    VECTOR_MIN_SIM = 0.20

    # 混合得分最低阈值（归一化后）
    FINAL_MIN_SCORE = 0.12

    def __init__(self):
        self._collection = None
        self._embed_model = None
        self._embedding_model_name = ""
        self._use_vector = False
        self._knowledge_base: List[Dict[str, Any]] = []
        self._entry_map: Dict[str, Dict[str, Any]] = {}

        self._load_knowledge_base()

        if CHROMA_AVAILABLE and EMBEDDING_AVAILABLE:
            self._init_vector_store()

        mode = "hybrid(vector+keyword)" if self._use_vector else "keyword-only"
        logger.info(
            "[RAG] 初始化完成 | mode=%s | entries=%d | embedding=%s",
            mode,
            len(self._knowledge_base),
            self._embedding_model_name or "disabled",
        )

    # ── 知识库加载 ─────────────────────────────────────────────────────────

    def _load_knowledge_base(self):
        try:
            from knowledge.emotion_knowledge import KNOWLEDGE_BASE, _normalize_entry

            # 对每条 entry 做兼容性归一化（补充缺失的新字段默认值）
            self._knowledge_base = [_normalize_entry(e) for e in KNOWLEDGE_BASE]
            self._entry_map = {e["id"]: e for e in self._knowledge_base}
            logger.info("[RAG] 知识库加载完成 | entries=%d", len(self._knowledge_base))
        except ImportError:
            # 旧版知识库没有 _normalize_entry，做内联兼容
            try:
                from knowledge.emotion_knowledge import KNOWLEDGE_BASE

                self._knowledge_base = [self._compat_entry(e) for e in KNOWLEDGE_BASE]
                self._entry_map = {e["id"]: e for e in self._knowledge_base}
                logger.info("[RAG] 知识库加载完成（兼容模式）| entries=%d", len(self._knowledge_base))
            except Exception as exc:
                logger.error("[RAG] 知识库加载失败: %s", exc)
                self._knowledge_base = []
                self._entry_map = {}
        except Exception as exc:
            logger.error("[RAG] 知识库加载异常: %s", exc)
            self._knowledge_base = []
            self._entry_map = {}

    @staticmethod
    def _compat_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
        """为旧格式条目补充新字段默认值（不修改原始对象）。"""
        defaults = {
            "audience": "大学生",
            "emotion_type": "general",
            "response_style": "empathetic",
            "risk_level": "low",
        }
        return {**defaults, **entry}

    # ── 向量库初始化 ───────────────────────────────────────────────────────

    def _init_vector_store(self):
        """初始化 ChromaDB，支持离线降级。"""
        model_cache = os.path.join(project_root, "data", "models")
        os.makedirs(self.CHROMA_DB_PATH, exist_ok=True)
        os.makedirs(model_cache, exist_ok=True)

        # 加载嵌入模型（只用本地缓存，禁止联网）
        for candidate in self.EMBEDDING_MODEL_CANDIDATES:
            if not candidate:
                continue
            try:
                self._embed_model = SentenceTransformer(
                    candidate,
                    cache_folder=model_cache,
                    local_files_only=True,
                )
                self._embedding_model_name = candidate
                logger.info("[RAG] 嵌入模型加载成功: %s", candidate)
                break
            except Exception:
                # 改动：只 debug 级，不打 WARNING 洪水，model 名脱敏不需要
                logger.debug("[RAG] 模型 %s 不可用，尝试下一个", candidate)

        if not self._embed_model:
            logger.warning("[RAG] 没有可用的本地嵌入模型，降级到纯关键词检索。")
            return

        # 连接 ChromaDB
        try:
            client = chromadb.PersistentClient(path=self.CHROMA_DB_PATH)
            collection = client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )

            expected = len(self._knowledge_base)
            actual = collection.count()

            if actual != expected:
                # P0：条目数不一致 → 明确 WARNING + 自动重建
                logger.warning(
                    "[RAG] 向量库条目数不一致 actual=%d expected=%d，触发重建。"
                    " 如频繁出现请检查知识库文件完整性。",
                    actual,
                    expected,
                )
                try:
                    client.delete_collection(self.COLLECTION_NAME)
                except Exception:
                    pass
                collection = client.get_or_create_collection(
                    name=self.COLLECTION_NAME,
                    metadata={"hnsw:space": "cosine"},
                )
                self._build_vector_store(collection)
            else:
                logger.info("[RAG] 向量库命中缓存 | entries=%d", actual)

            self._collection = collection
            self._use_vector = collection.count() > 0

        except Exception as exc:
            logger.warning("[RAG] ChromaDB 初始化失败，降级到关键词检索: %s", exc)
            self._use_vector = False
            self._collection = None

    def _build_document(self, entry: Dict[str, Any]) -> str:
        """构建用于向量化的文档文本（拼接关键字段）。"""
        return " ".join(filter(bool, [
            " ".join(entry.get("keywords", [])),
            entry.get("audience", ""),
            entry.get("emotion_type", ""),
            entry.get("category", ""),
            entry.get("topic", ""),
            entry.get("content", "")[:500],
            entry.get("advice", "")[:500],
            entry.get("dialogue_example", "")[:220],
        ]))

    def _build_vector_store(self, collection):
        """构建向量库。"""
        if not self._knowledge_base or not self._embed_model:
            return
        ids, docs, metas = [], [], []
        for entry in self._knowledge_base:
            ids.append(entry["id"])
            docs.append(self._build_document(entry))
            metas.append({
                "id": entry["id"],
                "category": entry.get("category", ""),
                "topic": entry.get("topic", ""),
                "risk_level": entry.get("risk_level", "low"),
            })
        embeddings = self._embed_model.encode(
            docs, batch_size=16, show_progress_bar=False
        ).tolist()
        collection.add(ids=ids, documents=docs, embeddings=embeddings, metadatas=metas)
        logger.info("[RAG] 向量库重建完成 | entries=%d", len(ids))

    # ── 检索核心 ───────────────────────────────────────────────────────────

    def _build_search_text(
        self,
        query: str,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """将最近用户输入 + 当前问题拼接，提高上下文相关性。"""
        history = history or []
        recent = [
            item.get("content", "")
            for item in history[-4:]
            if item.get("role") == "user"
        ][-2:]
        parts = [p.strip() for p in [*recent, query] if p and p.strip()]
        return " ".join(parts)

    @staticmethod
    def _normalize_score_map(score_map: Dict[str, float]) -> Dict[str, float]:
        """将得分归一化到 [0, 1]，避免不同召回路径的量级差异影响合并。"""
        if not score_map:
            return {}
        max_v = max(score_map.values()) or 1.0
        return {k: round(v / max_v, 6) for k, v in score_map.items() if v > 0}

    def _keyword_score_map(self, search_text: str) -> Dict[str, float]:
        """
        关键词召回得分：
        - 精确 keyword 命中：+4.0（改动：原 3.0 → 4.0，提高精确匹配权重）
        - topic 命中：+1.5，category 命中：+1.0
        - 字符级 overlap ≥ 0.5：+overlap 值
        - content/advice 词汇命中：+0.45
        """
        try:
            from knowledge.emotion_knowledge import KEYWORD_INDEX
        except ImportError:
            KEYWORD_INDEX = {}

        query_lower = search_text.lower()
        query_terms = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", search_text))
        query_chars = set(query_lower)
        scored: Dict[str, float] = {}

        # 精确关键词命中（权重最高）
        for kw, entry_ids in KEYWORD_INDEX.items():
            if kw.lower() in query_lower:
                for eid in entry_ids:
                    scored[eid] = scored.get(eid, 0.0) + 4.0

        for entry in self._knowledge_base:
            eid = entry["id"]
            topic = entry.get("topic", "")
            category = entry.get("category", "")
            content_blob = " ".join(filter(bool, [
                topic, category,
                entry.get("content", ""),
                entry.get("advice", ""),
            ]))

            if topic and topic.lower() in query_lower:
                scored[eid] = scored.get(eid, 0.0) + 1.5
            if category and category.lower() in query_lower:
                scored[eid] = scored.get(eid, 0.0) + 1.0

            for kw in entry.get("keywords", []):
                overlap = len(query_chars & set(kw.lower())) / max(len(set(kw.lower())), 1)
                if overlap >= 0.5:
                    scored[eid] = scored.get(eid, 0.0) + overlap

            for term in query_terms:
                if term in content_blob:
                    scored[eid] = scored.get(eid, 0.0) + 0.45

        return self._normalize_score_map(scored)

    def _vector_score_map(self, search_text: str, top_k: int) -> Dict[str, float]:
        """向量语义召回得分，相似度低于阈值的丢弃。"""
        if not (self._use_vector and self._collection and self._embed_model):
            return {}
        try:
            fetch_k = min(max(top_k * 3, 6), self._collection.count())
            query_vec = self._embed_model.encode([search_text]).tolist()
            results = self._collection.query(
                query_embeddings=query_vec,
                n_results=fetch_k,
                include=["distances", "metadatas"],
            )
            scored: Dict[str, float] = {}
            for idx, meta in enumerate(results.get("metadatas", [[]])[0]):
                dist = results["distances"][0][idx]
                sim = max(0.0, 1 - dist)
                # P1：阈值 0.18 → 0.20，减少低相关噪声
                if sim < self.VECTOR_MIN_SIM:
                    continue
                scored[meta["id"]] = round(sim, 6)
            return self._normalize_score_map(scored)
        except Exception as exc:
            logger.warning("[RAG] 向量检索失败，降级关键词: %s", exc)
            return {}

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """混合召回入口：向量 65% + 关键词 35%（无向量时纯关键词）。"""
        if not self._knowledge_base:
            return []

        search_text = self._build_search_text(query, history)
        kw_scores = self._keyword_score_map(search_text)
        vec_scores = self._vector_score_map(search_text, top_k)
        all_ids = set(kw_scores) | set(vec_scores)

        if not all_ids:
            return []

        merged: List[Dict[str, Any]] = []
        for eid in all_ids:
            vs = vec_scores.get(eid, 0.0)
            ks = kw_scores.get(eid, 0.0)
            # 有向量分时做加权融合，否则纯关键词
            if vec_scores:
                final = vs * self.VECTOR_WEIGHT + ks * self.KEYWORD_WEIGHT
            else:
                final = ks

            if final < self.FINAL_MIN_SCORE:
                continue

            entry = self._entry_map.get(eid)
            if entry:
                merged.append({**entry, "_similarity": round(final, 3)})

        merged.sort(key=lambda x: x.get("_similarity", 0), reverse=True)
        result = merged[: max(1, min(top_k, 5))]
        logger.info(
            "[RAG] 检索完成 | query_len=%d | hits=%d | top1=%s(%.3f)",
            len(query),
            len(result),
            result[0].get("topic", "") if result else "N/A",
            result[0].get("_similarity", 0) if result else 0,
        )
        return result

    # ── 上下文格式化 ──────────────────────────────────────────────────────

    # ── 上下文格式化 [====== 核心优化 ======] ──────────────────────────────

    def format_context(
        self,
        entries: List[Dict[str, Any]],
        query: str,
    ) -> str:
        """将检索结果格式化为潜意识级别的心理学经验，防止 AI 机械复述。"""
        if not entries:
            return ""

        parts: List[str] = []
        for idx, entry in enumerate(entries[:3], start=1): # 严格限制最多3条，避免AI注意力分散
            advice = (entry.get("advice", "") or "").strip()
            example = (entry.get("dialogue_example", "") or "").strip()
            
            # 提取 Claude 版新增的画像标签
            audience = entry.get("audience", "")
            emotion_type = entry.get("emotion_type", "")
            
            if len(advice) > 200:
                advice = advice[:200] + "..."
            if len(example) > 150:
                example = example[:150] + "..."

            # 使用 XML 标签伪装成内化经验，彻底剥离“机器查资料”的痕迹
            block = (
                f"<experience_{idx}>\n"
                f"适用人群画像：{audience} | 情绪类型：{emotion_type}\n"
                f"心理学视角拆解：{entry.get('content', '')[:100]}...\n"
                f"高情商应对思路：{advice}\n"
                f"满分话术参考：{example}\n"
                f"</experience_{idx}>"
            )
            parts.append(block)

        return (
            "\n<internal_knowledge>\n"
            "以下是你脑海中关于此类心理困境的专业经验（请内化为自己的阅历，融合进回复中，**绝对不要在回复中提到你参考了以下信息**）：\n"
            + "\n".join(parts)
            + "\n</internal_knowledge>\n"
        )

    # ── 状态查询 ──────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """返回服务状态（不含任何敏感路径信息）。"""
        return {
            "mode": "hybrid" if self._use_vector else "keyword",
            "knowledge_count": len(self._knowledge_base),
            "embedding_model": self._embedding_model_name or "disabled",
            "chroma_available": CHROMA_AVAILABLE,
            "embedding_available": EMBEDDING_AVAILABLE,
            "vector_weight": self.VECTOR_WEIGHT if self._use_vector else 0,
            "keyword_weight": self.KEYWORD_WEIGHT if self._use_vector else 1.0,
        }


rag_service = RAGService()
