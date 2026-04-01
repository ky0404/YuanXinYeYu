"""一次性脚本：构建情感知识库向量数据库。"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

print("=" * 60)
print("开始构建情感知识库向量数据库")
print("=" * 60)

missing = []
try:
    import chromadb
    print("[OK] chromadb 已安装")
except ImportError:
    missing.append("chromadb")
    print("[NO] chromadb 未安装")

try:
    from sentence_transformers import SentenceTransformer
    print("[OK] sentence-transformers 已安装")
except ImportError:
    missing.append("sentence-transformers")
    print("[NO] sentence-transformers 未安装")

if missing:
    print("\n请先安装依赖：")
    print(f"pip install {' '.join(missing)}")
    sys.exit(1)

from knowledge.emotion_knowledge import KNOWLEDGE_BASE

print(f"\n知识条目数：{len(KNOWLEDGE_BASE)}")

db_path = os.path.join(project_root, "data", "chroma_db")
model_path = os.path.join(project_root, "data", "models")
os.makedirs(db_path, exist_ok=True)
os.makedirs(model_path, exist_ok=True)

print(f"向量库路径：{db_path}")
print(f"模型缓存路径：{model_path}")

client = chromadb.PersistentClient(path=db_path)
collection_name = "emotion_knowledge"

try:
    client.delete_collection(collection_name)
    print("已删除旧向量集合，准备重建")
except Exception:
    pass

model_candidates = [
    os.getenv("EMOTION_EMBEDDING_MODEL", "").strip(),
    "text2vec-base-chinese",
    "paraphrase-multilingual-MiniLM-L12-v2",
]

model = None
model_name = ""
for candidate in model_candidates:
    if not candidate:
        continue
    try:
        print(f"尝试加载嵌入模型：{candidate}")
        model = SentenceTransformer(candidate, cache_folder=model_path)
        model_name = candidate
        break
    except Exception as exc:
        print(f"加载失败：{candidate} -> {exc}")

if model is None:
    print("没有可用的嵌入模型，请先准备至少一个本地或可下载模型。")
    sys.exit(1)

print(f"\n使用嵌入模型：{model_name}")

collection = client.get_or_create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})

ids = []
docs = []
metadatas = []

for entry in KNOWLEDGE_BASE:
    # 自动补充缺少的字段（适配 Claude 版 emotion_knowledge 的逻辑）
    from knowledge.emotion_knowledge import _normalize_entry
    full_entry = _normalize_entry(entry)
    
    # 构造检索文本：加入关键词、分类、建议，提高召回率
    doc_text = " ".join(filter(bool, [
        " ".join(full_entry.get("keywords", [])),
        full_entry.get("category", ""),
        full_entry.get("topic", ""),
        full_entry.get("content", "")[:500],
        full_entry.get("advice", "")[:500]
    ]))
    
    ids.append(full_entry["id"])
    docs.append(doc_text)
    
    # 关键：将所有标签存入 metadata，这样 RAG retrieve 出来后才能拿到这些字段
    metadatas.append({
        "id": full_entry["id"],
        "category": full_entry.get("category", ""),
        "topic": full_entry.get("topic", ""),
        "audience": full_entry.get("audience", "通用"),
        "emotion_type": full_entry.get("emotion_type", "general"),
        "risk_level": full_entry.get("risk_level", "low")
    })

print("\n生成嵌入向量中（这可能需要一点时间）...")
embeddings = model.encode(docs, batch_size=16, show_progress_bar=True).tolist()

print("正在写入 ChromaDB...")
# 如果 collection 已存在，建议先 delete 再 add，或者使用 upsert
collection.add(
    ids=ids, 
    documents=docs, 
    embeddings=embeddings, 
    metadatas=metadatas
)
count = collection.count()
print(f"写入完成，条目数：{count}")

print("\n开始做 4 条检索测试：")
for query in [
    "我最近很焦虑，晚上总睡不着",
    "我和对象吵架了，不知道怎么沟通",
    "我很想谈恋爱，但不知道怎么开始",
    "我最近工作压力很大，感觉快撑不住了",
]:
    query_embedding = model.encode([query]).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=2, include=["metadatas", "distances"])
    hits = []
    for index, metadata in enumerate(results["metadatas"][0]):
        similarity = round(1 - results["distances"][0][index], 3)
        hits.append(f"{metadata['topic']}({similarity})")
    print(f"- {query} -> {', '.join(hits)}")

print("\n构建完成，可以重启服务使用最新 RAG。")
