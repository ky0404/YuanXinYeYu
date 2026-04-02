# 媛心烨语 · AI 情绪陪伴与心理疏导系统

> 🌸 温婉如媛，明亮如烨 —— 一个懂你情绪、陪你聊天的心灵 AI 伴侣。

[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-Frontend-blue)](https://reactjs.org/)
[![Huawei ModelArts LLM](https://img.shields.io/badge/Huawei%20Cloud-LLM-brightgreen)](https://www.huaweicloud.com)

---

## 🌟 项目简介

**媛心烨语（YuanXinYeYu）** 是一款整合了大语言模型 + 心理知识库 的情绪陪伴系统。  
通过自然语言理解与共情式引导，让用户能在安全、温暖的空间中表达自我、获得安慰。

功能亮点：
- 💬 智能情绪识别与共情回复  
- 🧠 RAG 检索增强：把心理学知识融入 AI 直觉  
- 🚦 危机识别与安全分流（含热线提示）  
- ☁️ 用户注册 / 登录 / 云端历史同步  
- 📊 情绪趋势追踪与可视化  
- 🔒 完整隐私保护与日志脱敏

---

## 🏗 技术栈

| 层级 | 主要技术 |
|------|-----------|
| 前端 | React 19 + Vite 8 + TypeScript + Ant Design 6 + Axios |
| 后端 | FastAPI + SQLAlchemy + Uvicorn + Pydantic |
| 数据库 | SQLite（可替换 MySQL） |
| AI 分析 | 华为云 LLM（DeepSeek v3.2） + SentenceTransformer MiniLM + ChromaDB |
| 安全 | JWT 认证 + CORS 隔离 + 异常脱敏日志 + 游客日限控制 |

---

## ⚙️ 本地快速启动

### 1️⃣ 初始化后端服务
```bash
# 进入后端目录
cd backend_core

# 建立虚拟环境并安装依赖
python -m venv venv
source venv/bin/activate  # Windows 用 venv\Scripts\activate
pip install -r requirements.txt

# 新建配置文件 .env （内容示例）
HOST=127.0.0.1
PORT=8000
ENV=dev
DATABASE_URL=sqlite:///./emotion.db
HUAWEI_API_KEY=你的华为云Key
HUAWEI_MODEL=deepseek-v3.2

# 初始化数据库
python -m api.main
或首次执行：
python -c "from models.database import init_db; init_db()"

# 启动服务
uvicorn main:app --reload
```

接口文档（仅 dev 可见）：  
👉 http://127.0.0.1:8000/docs

---

### 2️⃣ 启动前端

```bash
cd frontend_core
npm install
npm run dev
```

浏览器访问：  
👉 http://localhost:5173

前端通过 Vite 代理自动转发 API 至 http://127.0.0.1:8000。

---

## 📡 主要 API 说明

### 🔐 用户认证
| API | 方法 | 说明 |
|------|------|------|
| `/api/auth/register` | POST | 注册新用户 |
| `/api/auth/login` | POST | 登录（返回 JWT Cookie） |
| `/api/auth/logout` | POST | 退出登录 |
| `/api/auth/me` | GET | 当前用户信息 |

### 💬 情绪分析核心接口
| API | 方法 | 描述 |
|------|------|------|
| `/api/emo_analysis` | POST | 分析情绪并返回模型回复 |
| `/api/mood/process` | POST | 同上别名接口（兼容旧版） |

请求示例：
```json
{
  "text": "最近总觉得很焦虑，晚上睡不着。",
  "mode": "smart",
  "history": [{"role": "user", "content": "上周也差不多"}]
}
```
返回示例：
```json
{
  "code": 200,
  "data": {
    "category": 2,
    "label": "负面",
    "score": 6.8,
    "keywords": ["焦虑", "失眠"],
    "reply": "听起来这段时间真的挺难受的…慢慢来，好吗？"
  }
}
```

### 🕘 对话与历史记录
| API | 方法 | 功能 |
|------|------|------|
| `/api/history` | GET | 获取当前用户对话历史 |
| `/api/history` | POST | 保存对话历史 |
| `/api/history` | DELETE | 清空历史 |
| `/api/emotion/trends` | GET | 获取情绪趋势数据 |
| `/api/emotion/records` | DELETE | 清空全部情绪记录 |

---

## 🧠 模块划分

| 模块 | 文件 | 功能 |
|------|------|------|
| **情绪分析引擎** | `core/analysis.py` | 实际调用 Huawei LLM 服务 |
| **RAG 检索模块** | `service/rag_service.py` | 向量 + 关键词混合召回 |
| **日志系统** | `config/logging_config.py` | JSON 结构化日志 + 彩色控制台 |
| **数据库结构** | `models/*.py` | User / ChatHistory / EmotionRecord |
| **Web API** | `api/routes/*.py` | auth / emo / history 路由 |
| **前端主界面** | `frontend_core/src/App.tsx` | 聊天界面 + 情绪趋势图 |
| **样式主题** | `frontend_core/src/App.css` | 毛玻璃风 + 治愈系配色 |

---

## ✨ 技术亮点

- **RAG 语义检索融合**
  - `ChromaDB + SentenceTransformer` 实现上下文检索增强。
- **风险分级 detect_risk_level()**
  - 快速识别 urgent / high / medium / low 四级风险并动态调整 Prompt。
- **自然共情式 Prompt 模板**
  - 系统提示改写为“人性化心理陪伴”话术，不暴露 AI 身份。
- **游客配额机制**
  - 每 IP 每日 5 次免费额度，防止滥用。
- **全局异常脱敏**
  - 任何异常仅简短输出「系统繁忙」而不泄露服务器堆栈。
- **离线安全模式**
  - 向量模型与知识库均可离线加载，无需外网。

---

---

## 🧩 知识库与向量检索模块

### 📚 情感知识库（`backend_core/knowledge/emotion_knowledge.py`）
- 内置 **学生群体专属心理与情感知识库 v2.0**；
- 覆盖主题：  
  `学业压力`、`宿舍与人际`、`恋爱与情感`、`就业与未来`、`心理健康`、`家庭关系`、`自我成长`、`生活压力`、`积极心理`；
- 每条知识条目包含字段：
  - `id`、`category`、`topic`、`keywords`
  - `content`（心理学分析）
  - `advice`（可行动建议）
  - `dialogue_example`（人性化回复示例）
  - 新增 `audience` (目标人群)、`emotion_type` (情绪类型)、`risk_level` (风险等级) 等元数据；
- 支持 `_normalize_entry()` 归一化函数和 `KEYWORD_INDEX` 快速关键词索引；
- 为 RAG 模块提供心理学知识上下文输入，帮助 LLM 生成更具人情味的共情回复。

### 🧠 知识库初始化脚本（`backend_core/scripts/build_knowledge_db.py`）
- 作用：一次性构建 **ChromaDB 向量数据库**；
- 自动：
  1. 检查依赖 `chromadb` 和 `sentence-transformers`；
  2. 读取 `emotion_knowledge.py` 中 `KNOWLEDGE_BASE`；
  3. 生成文本嵌入并写入本地向量库 `data/chroma_db/`；
  4. 默认使用模型：
     - `text2vec-base-chinese`  
     - 或回退到 `paraphrase-multilingual-MiniLM-L12-v2`；
  5. 构建完成后自动输出检索测试结果；
- ▶️ 使用方法：
```bash
cd backend_core
python scripts/build_knowledge_db.py

---

### 1. 核心功能与技术栈

#### 🏗 总体架构
`YuanXinYeYu`（媛心烨语）是一个**AI 情绪陪伴与心理疏导 Web 应用**，采用**前后端分离架构**：
- 前端：`frontend_core`
- 后端：`backend_core`

#### 💡 核心功能
| 模块 | 描述 |
|------|------|
| 🌸 情绪分析 | 通过 Huawei 云 NLP API + RAG 知识库结合，智能识别文本中的情绪类别、强度、风险等级，并生成自然共情式回复。 |
| 🪞 情感陪伴聊天 | 模拟贴心陪伴者 “小暖” 的聊天体验，支持 3 种模式（智能分析/暖心夸夸/温柔安慰）。 |
| 📊 情绪趋势追踪 | 前端以折线图形式展示用户近期对话的情绪强度变化。 |
| ☁️ 用户体系 | 注册登录、JWT 身份验证、Cookie 安全、历史记录云端同步。 |
| 💾 历史记录管理 | 支持查看、保存及清空用户的对话记录与情绪记录。 |
| 🧩 知识库 RAG | 内置心理情绪知识库，通过 ChromaDB + SentenceTransformer 实现检索增强生成。 |
| 🚦 情绪危机识别 | 检测“自杀”“崩溃”等高风险关键词，触发安全提示与热线信息。 |

#### 🛠 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | React 19 + Vite 8 + TypeScript + Ant Design 6 + Axios |
| **后端** | FastAPI + SQLAlchemy + Pydantic + Uvicorn |
| **数据库** | SQLite (默认，可切换 MySQL/PostgreSQL) |
| **AI 核心** | 华为云 ModelArts LLM（DeepSeek v3.2） + Chromadb 向量检索 + SentenceTransformers MiniLM |
| **认证与安全** | JWT 鉴权 + Cookie SameSite 设置 + 异常脱敏日志 |
| **日志系统** | JSON 结构化 Rotating Log + 彩色控制台输出 |
| **部署兼容** | 支持 systemd 启动，CORS 安全策略分 dev/prod。 |

#### 📁 目录结构简略图
```
Directory structure:
└── ky0404-yuanxinyeyu/
    ├── README.md
    ├── LICENSE
    ├── backend_core/
    │   ├── main.py
    │   ├── api/
    │   │   ├── __init__.py
    │   │   ├── main.py
    │   │   └── routes/
    │   │       ├── __init__.py
    │   │       ├── auth_route.py
    │   │       ├── emo_route.py
    │   │       └── history_route.py
    │   ├── config/
    │   │   ├── __init__.py
    │   │   ├── logging_config.py
    │   │   └── settings.py
    │   ├── core/
    │   │   ├── __init__.py
    │   │   └── analysis.py
    │   ├── data/
    │   │   └── models/
    │   │       └── models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2/
    │   │           └── blobs/
    │   │               ├── 2ea7ad0e45a9d1d1591782ba7e29a703d0758831
    │   │               ├── 3c1b565ae10a15a1d0c31096f834af2fd9359e91
    │   │               ├── 5fd10429389515d3e5cccdeda08cae5fea1ae82e
    │   │               ├── 6bedb7f3622d56b7020f33ab93f6996d33242043
    │   │               ├── b974b349cb2d419ada11181750a733ff82f291ad
    │   │               ├── c06d5b49495f044e6380e68a60538be17a6bd5d1
    │   │               └── d1514c3162bbe87b343f565fadc62e6c06f04f03
    │   ├── knowledge/
    │   │   ├── emotion_knowledge.py  
    │   │   └── knowledge__init__.py
    │   ├── models/
    │   │   ├── __init__.py
    │   │   ├── database.py
    │   │   ├── emotion_record.py
    │   │   ├── guest_quota.py
    │   │   └── user.py
    │   ├── scripts/
    │   │   └── build_knowledge_db.py
    │   ├── service/
    │   │   ├── __init__.py
    │   │   ├── huawei_nlp.py
    │   │   └── rag_service.py
    │   └── utils/
    │       ├── __init__.py
    │       ├── auth.py
    │       ├── request.py
    │       └── response.py
    └── frontend_core/
        ├── README.md
        ├── cookies.txt
        ├── eslint.config.js
        ├── index.html
        ├── package.json
        ├── tsconfig.app.json
        ├── tsconfig.json
        ├── tsconfig.node.json
        ├── vite.config.ts
        └── src/
            ├── App.css
            ├── App.tsx
            ├── index.css
            └── main.tsx

```

---

### 2. 项目解决的痛点（通俗解释）

传统心理陪伴 APP 普遍两类问题：
- 🤖 AI 回复机械、居高临下；
- 🧍‍♀️ 真人咨询耗费高、无法 24 小时响应。

**“媛心烨语”**想解决的核心痛点是：
> 让 AI 像一个理解情绪、会安慰人的朋友，一开口就有温度。

它做到：
- **能听懂情绪，不只是关键词匹配**：结合 语义分析 + 知识库 + 上下文 推理。
- **能自然陪伴，不暴露 AI 身份**：回复模仿心理咨询师的真实语气。
- **能守护安全**：自动识别危机词，私下记日志、前台温柔劝导。
- **能积累治愈力**：历史趋势图提醒用户自身情绪变化。

---
## 🧪 开发建议

- 生产部署可用 `Nginx + Gunicorn/UvicornWorker`；
- 数据可切换 PostgreSQL 以支持高并发；
- 前端支持 PWA 改造，实现离线“心舍”体验；
- 可集成 WebSocket 实现实时打字回复动画。

---

## 📜 开源声明

本项目主要用于技术研究与心理健康公益交流。  
严禁将模型输出作为医学诊断或危机咨询的替代。

---

© 2026 YuanXinYeYu Team — 愿每一份情绪都被温柔接住 💗
