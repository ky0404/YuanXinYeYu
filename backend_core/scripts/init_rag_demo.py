#!/usr/bin/env python3
"""scripts/init_rag_demo.py
一键初始化 RAG Demo 数据：
  1. 往 KG SQLite 插入 7 个节点 + 8 条边（心理知识图谱）
  2. 往 ChromaDB 插入 6 条向量文档（调用 Embedding API）

运行方式：
  cd ~/emotion_analysis_service
  python3 scripts/init_rag_demo.py
"""
from __future__ import annotations

import asyncio
import os
import sys

# ── 路径设置（必须在 import project 模块之前）────────────────────────────
_script_dir  = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
sys.path.insert(0, _project_root)

from config.settings import settings  # noqa: E402

print("=" * 60)
print("暖心树洞 RAG 知识库初始化脚本 v1.0")
print(f"KG SQLite  : {settings.KG_SQLITE_PATH}")
print(f"Chroma dir : {settings.CHROMA_PERSIST_DIR}")
print(f"Emb model  : {settings.EMBEDDING_MODEL}")
print("=" * 60)


# ══════════════════════════════════════════════════════════
# Step 1: 图谱节点 + 边（同步，SQLite）
# ══════════════════════════════════════════════════════════

def init_graph() -> None:
    from rag.graph.graph_store import add_edge, add_node, get_node_count  # noqa: PLC0415

    nodes = [
        {
            "node_id": "cbt_therapy",
            "name":    "CBT 认知行为疗法",
            "node_type": "therapy",
            "properties": {
                "description": (
                    "CBT 是针对焦虑、抑郁、压力的核心心理治疗方法，"
                    "通过识别和重构负性自动思维，改变行为模式，已有大量循证研究支持。"
                )
            },
            "embedding_text": "CBT 认知行为疗法 焦虑 抑郁 压力 心理治疗 自动思维",
        },
        {
            "node_id": "crisis_hotline_bj",
            "name":    "北京心理危机研究院热线",
            "node_type": "resource",
            "properties": {"resource": "010-82951332", "available": "24小时"},
            "embedding_text": "北京心理危机热线 自杀预防 危机干预 010-82951332",
        },
        {
            "node_id": "crisis_hotline_national",
            "name":    "全国心理援助热线",
            "node_type": "resource",
            "properties": {"resource": "400-161-9995", "available": "24小时"},
            "embedding_text": "全国心理援助热线 危机干预 自杀预防 400-161-9995",
        },
        {
            "node_id": "exam_anxiety",
            "name":    "考试焦虑",
            "node_type": "symptom",
            "properties": {
                "description": (
                    "考试焦虑是大学生最常见的心理困扰，表现为注意力无法集中、"
                    "睡眠障碍、身体紧绷。核心干预：任务分解 + 番茄工作法 + 接受不完美。"
                )
            },
            "embedding_text": "考试焦虑 期末 压力 绩点 GPA 复习 学业压力",
        },
        {
            "node_id": "social_anxiety",
            "name":    "社交焦虑",
            "node_type": "symptom",
            "properties": {
                "description": (
                    "社交焦虑是对他人评价的过度恐惧，导致在人际场合中出现脸红、"
                    "心跳加速等生理反应和回避行为。暴露疗法和认知重构是主流干预方式。"
                )
            },
            "embedding_text": "社交焦虑 社恐 发言恐惧 人际关系 不敢说话",
        },
        {
            "node_id": "student_mental_health",
            "name":    "大学生心理健康",
            "node_type": "topic",
            "properties": {
                "description": (
                    "大学生心理健康涵盖学业压力、宿舍人际、恋爱情感、就业焦虑、"
                    "自我认同等核心议题，是高校心理工作的重点领域。"
                )
            },
            "embedding_text": "大学生心理健康 心理问题 大学 心理咨询",
        },
        {
            "node_id": "depression_recognition",
            "name":    "抑郁情绪识别",
            "node_type": "knowledge",
            "properties": {
                "description": (
                    "持续两周以上的情绪低落、兴趣丧失、睡眠食欲改变，"
                    "可能是抑郁的信号，需认真对待。寻求心理咨询不是软弱，是对自己负责。"
                )
            },
            "embedding_text": "抑郁 情绪低落 没意思 不想动 什么都提不起劲",
        },
    ]

    edges = [
        ("cbt_therapy",          "exam_anxiety",          "治疗方法", 1.0),
        ("cbt_therapy",          "social_anxiety",         "治疗方法", 1.0),
        ("cbt_therapy",          "depression_recognition", "治疗方法", 0.9),
        ("student_mental_health","exam_anxiety",           "常见问题", 1.0),
        ("student_mental_health","social_anxiety",         "常见问题", 1.0),
        ("student_mental_health","depression_recognition", "常见问题", 0.9),
        ("crisis_hotline_bj",    "crisis_hotline_national","同类资源", 0.8),
        ("depression_recognition","crisis_hotline_national","危机资源",  1.0),
    ]

    existing = get_node_count()
    if existing > 0:
        print(f"[KG] 图谱已有 {existing} 个节点，跳过重复插入")
        return

    for n in nodes:
        add_node(**n)
        print(f"  [KG] 节点: {n['name']}")

    for src, dst, rel, w in edges:
        add_edge(src, dst, rel, w)
        print(f"  [KG] 边: {src} --[{rel}]--> {dst}")

    print(f"[KG] ✅ 已插入 {len(nodes)} 节点 + {len(edges)} 条边")


# ══════════════════════════════════════════════════════════
# Step 2: Chroma 向量文档（异步，调用 Embedding API）
# ══════════════════════════════════════════════════════════

async def init_vector() -> None:
    if not settings.EMBEDDING_API_KEY:
        print("[Chroma] ⚠️  EMBEDDING_API_KEY 未配置，跳过向量文档插入")
        print("         请在 .env 中配置后重新运行此脚本。")
        return
    if not settings.EMBEDDING_API_BASE:
        print("[Chroma] ⚠️  EMBEDDING_API_BASE 未配置，跳过向量文档插入")
        return

    from rag.vector_store.chroma_store import add_documents, get_count  # noqa: PLC0415

    existing = get_count()
    if existing > 0:
        print(f"[Chroma] 向量库已有 {existing} 条文档，跳过重复插入")
        return

    docs = [
        {
            "id":   "v_exam_anxiety",
            "text": (
                "考试焦虑应对：把'复习全部'拆成'今天只搞定这三章'，番茄工作法25分钟+休息5分钟。"
                "考前30分钟做腹式呼吸，不要再翻新内容。接受不完美，及格就是胜利。"
            ),
            "meta": {"topic": "考试焦虑", "audience": "大学生"},
        },
        {
            "id":   "v_cbt_basics",
            "text": (
                "CBT认知行为疗法核心：识别自动思维（如'我肯定会失败'）→ 质疑证据 → 替换为平衡思维。"
                "适用于焦虑、抑郁、完美主义。行动实验：预测后实际做一件小事，收集反驳证据。"
            ),
            "meta": {"topic": "CBT疗法", "audience": "大学生"},
        },
        {
            "id":   "v_social_anxiety",
            "text": (
                "社交焦虑改善：每天做一件小的社交行为（问同学借支笔）。"
                "注意力外转：把注意力放在对方说了什么，而不是'我现在看起来怎样'。"
                "回避会让焦虑短期缓解但长期加重。"
            ),
            "meta": {"topic": "社交焦虑", "audience": "大学生"},
        },
        {
            "id":   "v_crisis_resources",
            "text": (
                "心理危机资源：北京心理危机研究院热线 010-82951332（24小时）；"
                "全国心理援助热线 400-161-9995（24小时）。"
                "如有自伤念头，请立即联系信任的人或拨打热线，这不是软弱，是保护自己。"
            ),
            "meta": {"topic": "危机干预", "audience": "大学生", "risk_level": "urgent"},
        },
        {
            "id":   "v_romantic_breakup",
            "text": (
                "失恋疗愈：允许自己悲伤，断联是最好的恢复药。"
                "不要靠新欢掩盖旧痛。重建日常节律：睡眠、饮食、运动。"
                "找回恋爱期间搁置的爱好，重建'没有ta的自己'。"
            ),
            "meta": {"topic": "失恋情感", "audience": "大学生"},
        },
        {
            "id":   "v_dormitory_conflict",
            "text": (
                "宿舍矛盾处理：就事论事不针对人格，'你昨晚打游戏声音影响了我睡觉'比'你太自私'更有效。"
                "找共同规则：'我们能不能定一个作息公约？'。室友不需要成为朋友，能互相尊重就够了。"
            ),
            "meta": {"topic": "宿舍冲突", "audience": "大学生"},
        },
    ]

    doc_ids  = [d["id"]   for d in docs]
    texts    = [d["text"] for d in docs]
    metadatas = [d["meta"] for d in docs]

    print(f"[Chroma] 调用 Embedding API 为 {len(docs)} 条文档生成向量...")
    try:
        await add_documents(doc_ids, texts, metadatas)
        print(f"[Chroma] ✅ 已插入 {len(docs)} 条向量文档")
    except Exception as exc:
        print(f"[Chroma] ❌ 插入失败: {exc}")
        print("  请检查 EMBEDDING_API_KEY / EMBEDDING_API_BASE 配置是否正确")


# ══════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════

async def main() -> None:
    print("\n▶ Step 1: 初始化知识图谱（SQLite）")
    try:
        init_graph()
    except Exception as exc:
        print(f"[KG] ❌ 失败: {exc}")

    print("\n▶ Step 2: 初始化向量文档（ChromaDB + Embedding API）")
    await init_vector()

    print("\n" + "=" * 60)
    print("✅ 初始化完成！可执行验收：")
    print("  python3 -c \"from rag.graph.graph_store import get_node_count; print('KG nodes:', get_node_count())\"")
    print("  python3 -c \"from rag.vector_store.chroma_store import get_count; import asyncio; print('Chroma docs:', get_count())\"")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())