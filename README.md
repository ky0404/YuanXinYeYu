
---

# 🌸 媛心烨语 · AI 情绪陪伴与心理疏导系统

> 温婉如媛，明亮如烨 —— 一个懂你情绪、会安慰人的心灵 AI 伴侣。

[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-blue)](https://reactjs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-状态机-orange)](https://langchain-ai.github.io/langgraph/)
[![Langfuse](https://img.shields.io/badge/Langfuse-可观测性-purple)](https://langfuse.com)
[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

🔗 **线上体验**：[https://dukkha.top](https://dukkha.top)

---

## ✨ 项目简介

**媛心烨语（YuanXinYeYu）** 是一款面向大学生群体的**生产级 AI 情绪陪伴系统**，整合了大语言模型与专业心理学知识库，通过自然语言理解与共情式引导，为用户提供安全、温暖、私密的情绪倾诉空间。

系统采用 **前后端分离架构**，以 **LangGraph 状态机** 编排核心业务流程，实现了**三混合 RAG 检索增强**、**四级危机干预 SOP**、**全链路可观测性**等生产级特性，已部署于腾讯云（2核2G）并稳定对外服务。

### 核心评测数据（生产环境，100条用例）
| 指标 | 数值 |
|------|------|
| 评测成功率 | **100.0%**（100/100）|
| 风险识别准确率 | **98.0%** |
| 情绪分类准确率 | **90.0%** |
| 延迟 P50 / P95 / P99 | **5.2s / 8.3s / 10.1s** |
| 运行内存（实测） | **129.3 MB** |

---

## 🎯 核心功能

| 功能模块 | 技术实现 | 说明 |
|---------|---------|------|
| 💬 智能情绪陪伴 | LangGraph + DeepSeek v3.2 | 三种模式（智能分析/暖心夸夸/温柔安慰） |
| 🧠 三混合 RAG | VectorRAG + GraphRAG + BM25 | 自动路由，25条专业心理知识库 |
| 🚦 四级危机干预 | 关键词 + LLM + 安全后处理 | 98.0% 风险识别准确率 |
| ⚡ SSE 流式输出 | FastAPI Server-Sent Events | 打字机效果，线上验证成功 |
| 📝 RLHF 反馈闭环 | WebSocket 双向通信 | 点赞/踩/重新生成，支持后续 DPO |
| 📊 情绪趋势追踪 | ECharts + 时间序列分析 | 7天/30天情绪变化曲线 |
| 🔒 隐私安全 | JWT + HttpOnly Cookie + 数据脱敏 | 游客模式 + 一键清空 |
| 📈 全链路监控 | Prometheus + Langfuse | `/metrics` 端点 + 链路追踪 |

---

## 🛠 技术栈

### 后端
- **Web 框架**：FastAPI 0.109 + Uvicorn（factory 模式）
- **状态机编排**：LangGraph（4节点线性 Pipeline：risk → rag → llm → safety）
- **大语言模型**：华为云 Pangu MaaS DeepSeek v3.2（OpenAI 兼容接口）
- **向量数据库**：ChromaDB（持久化向量存储）
- **嵌入模型**：华为云 MaaS bge-m3（API 调用，零本地内存占用）
- **关键词检索**：BM25（`bm25_retriever.py`，25条文档索引）
- **知识图谱**：SQLite 实现的轻量级 GraphRAG
- **语义缓存**：纯内存实现，相似度阈值 92%
- **数据库**：SQLite（开发）/ MySQL（生产）
- **ORM**：SQLAlchemy 2.0 + Pydantic 2
- **可观测性**：Langfuse（链路追踪）+ Prometheus（指标暴露）
- **限流**：IP 滑动窗口 + 游客每日额度（GuestQuota 表）
- **部署**：systemd + Nginx 反代 + Gunicorn

### 前端
- **框架**：React 19 + TypeScript 5.9+
- **构建工具**：Vite 8
- **UI 组件库**：Ant Design 6
- **HTTP 客户端**：Axios
- **数据可视化**：ECharts 5
- **实时通信**：WebSocket（控制通道）+ SSE（流式输出）
- **PWA 支持**：可安装为桌面 / 移动端应用

---

## 🧩 核心架构详解

### 1. LangGraph 状态机编排（`agent/graph.py`）

系统将核心业务流程重构为**4节点线性状态机**，实现清晰的业务流转与优雅的故障降级：

```
用户输入
  ↓
[risk_detect]   ← 关键词 + LLM 四级风险识别
  ↓
[rag_retrieve]  ← 三混合 RAG 检索（VectorRAG + GraphRAG + BM25 + RRF 融合）
  ↓
[llm_generate]  ← 华为云 DeepSeek v3.2 生成回复 + Langfuse 追踪
  ↓
[safety_check]  ← urgent 级别强制追加心理援助热线
  ↓
SSE 流式推送给前端（token 逐字输出）
```

**设计亮点**：
- 懒加载单例编译（`_compiled_graph`），节省内存约 20MB
- 任意节点失败自动降级到旧函数式链路（`core/analysis.py`）
- `USE_LANGGRAPH` 环境变量一键灰度切换
- 全局 `AgentState` TypedDict，节点间无副作用传递

**运行日志示例**：
```
[LG] Graph 编译完成 | nodes=4 (risk→rag→llm→safety)
[LG] run_agent START | mode=smart text_len=15 history=6
[LG] risk_detect | risk=low text_len=15
[LG] rag_retrieve | context_len=443 route=self refs=4
[LG] llm_generate | category=2 score=8.0 reply_len=202
[LG] safety_check | 无需追加热线
[LG] run_agent END | category=2 score=8.0
```

---

### 2. 三混合 RAG 检索系统（`rag/`）

**Self-RAG 路由策略**（`rag/router.py`）：
| 路由类型 | 触发条件 | 检索方式 |
|---------|---------|---------|
| `route=self` | 知识寻求类问题 | VectorRAG（ChromaDB 语义检索）|
| `route=graph` | 危机关键词命中 | GraphRAG（SQLite 图谱遍历）|
| `route=none` | 纯倾诉类问题 | 不检索，直接生成 |
| `route=hybrid` | 复合场景 | BM25 + VectorRAG + RRF 融合 |

**性能数据**（生产验证）：
- 知识库规模：25条文档（`bm25_retriever.py`）
- 每次返回：Top-4 文档，context_len ≈ 460 字符
- 嵌入方式：API 调用（bge-m3），零本地 GPU/内存占用
- Precision@3：82%

---

### 3. 四级危机干预 SOP（`core/risk_detection.py`）

```
level=low    → 正常情绪分析回复
level=medium → 增加关怀引导，软提示专业资源
level=high   → GraphRAG 强制检索危机资源，追加建议
level=urgent → 隐藏原始回复，强制显示心理援助热线
               热线：400-161-9995（全国心理援助）
```

**可解释日志**（生产实测）：
```
[risk] level=urgent reason=method_only      text='我买了很多安眠药...'
[risk] level=urgent reason=method+intent    text='我割腕了...'
[risk] level=urgent reason=farewell         text='告别了，谢谢你陪我...'
[risk] level=low    reason=no_keywords      text='最近工作压力有点大'
```

---

### 4. 全链路可观测性（`agent/langfuse_client.py` + Prometheus）

- **Langfuse 链路追踪**：记录每次请求的 Embedding / RAG / LLM / 风险识别全链路
- **Prometheus 指标**：`/metrics` 端点，对接 Grafana 大盘
- **结构化日志**：Python JSON Logger，支持 ELK 接入
- **评测框架**：`eval/run_eval.py`，输出 `.md` 报告 + `.csv` 数据 + `.json` 追踪

---

## 🚀 快速开始

### 环境要求
- Python 3.10+
- Node.js 18+
- 华为云 API Key（LLM + Embedding）

### 1. 克隆项目
```bash
git clone https://github.com/ky0404/yuanxinyeyu.git
cd yuanxinyeyu
```

### 2. 启动后端
```bash
cd backend_core
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # 填入 HUAWEI_API_KEY 等配置
python scripts/build_knowledge_db.py    # 构建向量库
python -m uvicorn api.main:create_app --factory --host 127.0.0.1 --port 8000
```
访问 http://127.0.0.1:8000/docs 查看 API 文档。

### 3. 启动前端
```bash
cd frontend_core
npm install && npm run dev
```
访问 http://localhost:5173 体验完整功能。

### 4. 运行评测
```bash
cd backend_core
python eval/run_eval.py          # 运行 100 条评测用例
cat eval/output/report_*.md     # 查看评测报告
```

---

## 📡 主要 API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/emo_analysis_stream` | POST | SSE 流式情绪分析（核心接口）|
| `/api/emo_analysis` | POST | 非流式情绪分析 |
| `/api/auth/register` | POST | 用户注册 |
| `/api/auth/login` | POST | 用户登录 |
| `/api/history` | GET/POST/DELETE | 对话历史管理 |
| `/api/emotion/trends` | GET | 情绪趋势数据 |
| `/api/feedback` | POST | RLHF 用户反馈 |
| `/api/ws` | WebSocket | 心跳 + 取消 + 反馈控制 |
| `/api/health` | GET | 服务健康检查 |
| `/metrics` | GET | Prometheus 监控指标 |

---

## 📁 项目结构

```
ky0404-yuanxinyeyu/
├── backend_core/
│   ├── main.py                    # 服务启动入口
│   ├── requirements.txt
│   ├── agent/
│   │   ├── graph.py               # LangGraph 4节点状态机
│   │   └── langfuse_client.py     # Langfuse 追踪客户端
│   ├── api/
│   │   ├── main.py                # FastAPI 应用工厂
│   │   └── routes/
│   │       ├── emo_route.py       # 情绪分析路由
│   │       ├── stream_route.py    # SSE 流式路由
│   │       ├── ws_route.py        # WebSocket 控制路由
│   │       ├── auth_route.py      # 认证路由
│   │       ├── history_route.py   # 历史与趋势路由
│   │       └── feedback_route.py  # RLHF 反馈路由
│   ├── config/
│   │   ├── settings.py            # 环境变量配置
│   │   └── logging_config.py      # 结构化日志
│   ├── core/
│   │   └── analysis.py            # 情绪分析核心（LangGraph 入口 + 降级链）
│   ├── rag/
│   │   ├── router.py              # Self-RAG 智能路由
│   │   ├── bm25_retriever.py      # BM25 关键词检索
│   │   ├── self_rag/              # Self-RAG 路由决策
│   │   ├── vector_store/          # ChromaDB 向量检索
│   │   ├── graph/                 # SQLite 知识图谱
│   │   ├── hybrid/                # RRF 混合融合
│   │   └── providers/             # 华为云 bge-m3 嵌入 API
│   ├── service/
│   │   ├── huawei_nlp.py          # 华为云 LLM 服务封装
│   │   ├── cache_service.py       # 语义缓存（纯内存，阈值92%）
│   │   └── rag_service.py         # RAG 服务层
│   ├── models/
│   │   ├── database.py            # SQLAlchemy 连接配置
│   │   ├── user.py                # 用户 + 对话历史模型
│   │   ├── emotion_record.py      # 情绪记录模型
│   │   └── guest_quota.py         # 游客配额模型（IP+日期+计数）
│   ├── knowledge/
│   │   └── emotion_knowledge.py   # 心理学知识库内容
│   ├── eval/
│   │   ├── run_eval.py            # 自动化评测脚本
│   │   ├── dataset.jsonl          # 100条测试用例
│   │   └── output/                # 评测结果（md+csv+json）
│   └── utils/
│       ├── auth.py                # JWT 工具函数
│       ├── response.py            # 统一响应格式
│       └── request.py             # HTTP 请求工具
└── frontend_core/
    ├── index.html
    ├── vite.config.ts
    └── src/
        ├── App.tsx                # 主应用组件
        └── main.tsx               # React 入口
```

---

## 🚢 生产部署

### systemd 服务（实测运行中）
```ini
[Service]
ExecStart=/root/emotion_analysis_service/venv/bin/python3 \
  -m uvicorn api.main:create_app \
  --factory --host 127.0.0.1 --port 8000 --workers 1
```
实测：Memory=129.3MB，PID=2442389，Active=running

### Nginx SSE 关键配置
```nginx
location /api/emo_analysis_stream {
    proxy_pass         http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_buffering    off;   # SSE 必须关闭缓冲
    proxy_cache        off;
    proxy_read_timeout 3600;
}
```

---

## ⚠️ 重要说明

本系统仅作情绪陪伴工具，**不能替代专业心理咨询或医学诊断**。如遇严重心理危机，请立即拨打：
- 全国心理援助热线：**400-161-9995**
- 北京心理危机研究院：**010-82951332**

---

## 📜 开源协议

MIT License © 2026 ky0404
