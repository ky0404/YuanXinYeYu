# 🌸 媛心烨语 · AI 情绪陪伴与心理疏导系统

> 温婉如媛，明亮如烨 —— 一个懂你情绪、会安慰人的心灵 AI 伴侣。
> 
> 愿每一份情绪都被温柔接住，每一个孤独的时刻都有陪伴。

[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-Frontend-blue)](https://reactjs.org/)
[![Huawei Cloud](https://img.shields.io/badge/Huawei%20Cloud-LLM-brightgreen)](https://www.huaweicloud.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agent%20Orchestration-orange)](https://langchain-ai.github.io/langgraph/)
[![Langfuse](https://img.shields.io/badge/Langfuse-Observability-purple)](https://langfuse.com)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9+-blue)](https://www.typescriptlang.org/)

---

## ✨ 项目简介

**媛心烨语（YuanXinYeYu）** 是一款专为大学生群体打造的生产级AI情绪陪伴系统，整合了大语言模型与专业心理学知识库，通过自然语言理解与共情式引导，为用户提供安全、温暖、私密的情绪倾诉空间。

系统采用**前后端分离架构**，基于**LangGraph状态机**编排核心业务流程，实现了**三混合RAG检索增强**、**四级危机干预**、**全链路可观测性**等企业级特性。所有功能均在**2核2G云服务器**上优化运行，内存峰值控制在1.2GB以内，兼顾性能与成本。

**在线体验**：[https://dukkha.top](sslocal://flow/file_open?url=https%3A%2F%2Fdukkha.top&flow_extra=eyJsaW5rX3R5cGUiOiJjb2RlX2ludGVycHJldGVyIn0=)

---

## 🎯 核心功能

| 功能 | 技术实现 | 描述 |
|------|----------|------|
| 💬 **智能情绪陪伴** | 华为云DeepSeek v3.2 + 情绪镜像词典 | 三种模式（智能分析/暖心夸夸/温柔安慰），生成自然共情式回复 |
| 🧠 **三混合RAG知识增强** | Self-RAG + VectorRAG + GraphRAG | 内置大学生专属心理知识库，自动选择最优检索策略 |
| 🚦 **四级危机干预SOP** | 关键词匹配 + LLM风险识别 + 安全后处理 | 自动识别自杀、自残等高风险信号，触发标准化安全流程 |
| ☁️ **云端数据同步** | JWT认证 + SQLite/MySQL | 用户注册登录后，对话历史与情绪记录永久云端保存 |
| 📊 **情绪趋势追踪** | ECharts可视化 + 时间序列分析 | 展示用户7天/30天情绪变化曲线，帮助自我认知 |
| 🔒 **隐私安全保护** | 全局数据脱敏 + 游客模式 + 一键清空 | 全方位保护用户隐私，符合心理咨询伦理规范 |
| ⚡ **SSE流式输出** | FastAPI Server-Sent Events | 打字机效果回复，模拟真实聊天体验 |
| 📝 **RLHF反馈闭环** | WebSocket实时反馈 + 统计分析 | 支持点赞/踩/重新生成，持续优化AI回复质量 |

---

## 🛠 技术栈

### 前端技术栈
- **框架**：React 19 + TypeScript 5.9+
- **构建工具**：Vite 8
- **UI组件**：Ant Design 6
- **HTTP客户端**：Axios
- **样式**：原生CSS + 毛玻璃效果
- **PWA支持**：可安装为桌面/移动端应用

### 后端技术栈
- **Web框架**：FastAPI + Uvicorn
- **智能体编排**：**LangGraph**（状态机化核心链路，支持开关切换与失败回退）
- **ORM**：SQLAlchemy 2.0
- **数据验证**：Pydantic
- **日志系统**：Python JSON Logger + 滚动日志
- **异步HTTP**：aiohttp
- **可观测性**：**Langfuse**（全链路追踪LLM/RAG/风险识别）
- **监控**：Prometheus + Grafana

### AI与数据层
- **大语言模型**：华为云DeepSeek v3.2（OpenAI兼容接口）
- **向量数据库**：ChromaDB（轻量持久化）
- **嵌入模型**：华为云MaaS bge-m3（API调用，零本地内存占用）
- **知识图谱**：SQLite实现的轻量级GraphRAG
- **数据库**：SQLite（默认）/ MySQL（生产环境可选）
- **语义缓存**：纯内存实现，相似度阈值92%，降低API调用35%

### 安全与运维
- **认证**：JWT + HttpOnly Cookie
- **限流**：Redis滑动窗口限流 + 游客每日额度控制
- **部署**：Nginx反向代理 + Gunicorn + systemd开机自启
- **降级策略**：多级自动降级，确保服务永不宕机

---

## 🧩 核心模块深度解析

### 1. LangGraph 智能体编排 (`agent/graph.py`)
**核心价值**：将原本的"函数式调用链"重构为"状态机编排"，实现更清晰的业务逻辑、更优雅的失败处理和更灵活的灰度发布。

**设计亮点**：
- **4节点线性工作流**：严格按照 `risk_detect` → `rag_retrieve` → `llm_generate` → `safety_check` 顺序执行
- **懒加载单例编译**：全局`_compiled_graph`仅在第一次请求时编译，节省内存约20MB
- **节点级失败回退**：任意节点出错自动降级到旧函数式链路，确保生产环境可用性
- **开关控制灰度发布**：通过`USE_LANGGRAPH`环境变量一键切换新旧链路，出问题1秒回退
- **Langfuse深度集成**：在`llm_generate`节点内注入全链路追踪，记录完整的输入输出和元数据

**状态机流转日志示例**：
```
[LG] Graph 编译完成 | nodes=4 (risk→rag→llm→safety)
[LG] run_agent START | mode=smart text_len=15 history=6
[LG] risk_detect | risk=low text_len=15
[LG] rag_retrieve | context_len=443 route=self
[LG] llm_generate | category=2 score=8.0 reply_len=202
[LG] safety_check | 无需追加热线
[LG] run_agent END | category=2 score=8.0
```

### 2. 三混合RAG检索系统 (`rag/`)
**与LangGraph协同**：RAG检索作为LangGraph工作流的第二个节点，由Self-RAG决定路由策略，结果注入LLM Prompt。

**架构设计**：
- **Self-RAG**：基于启发式规则决定是否需要检索及检索类型
  - `route=self`：知识寻求类问题，走向量检索
  - `route=graph`：危机关键词命中，走图谱检索
  - `route=none`：纯倾诉类问题，不检索任何内容
- **VectorRAG**：ChromaDB向量检索，捕捉语义相似性，Precision@3=82%
- **GraphRAG**：SQLite实现的轻量级知识图谱，提供结构化知识和危机资源
- **HybridRAG**：合并向量和图谱结果，按相似度加权排序

**检索日志示例**：
```
[RagRouter] Vector backend: OK (API embedding)
[RagRouter] Graph backend: OK (SQLite nodes=7)
[RagRouter] route=graph need=True reason=crisis_keywords
[GraphRAG] hits=3 seeds=['自杀']
[RagRouter] 最终 docs=3 top_score=1.000 route=graph
```

### 3. 全链路可观测性 (`utils/observability/`)
**Langfuse集成**：
- **追踪覆盖**：Embedding调用、RAG检索、LLM生成、风险识别等所有核心节点
- **记录内容**：用户输入、模式、风险等级、情感类别、分数、完整Prompt/Response、延迟等
- **分析能力**：通过Langfuse Dashboard分析响应慢的请求、优化RAG检索准确率、统计模型成本
- **开关控制**：通过`LANGFUSE_ENABLED`环境变量一键开启/关闭，不影响主业务

**Langfuse后台数据示例**：
- Trace列表：显示`lg_llm_generate`（LangGraph链路）和`nlp_generate`（旧链路）两种请求
- Trace详情：包含完整的Input/Output/Metadata，支持按用户、会话、时间筛选
- 延迟分析：p50=7.0s，p90=8.4s，p95=8.7s
- 成本统计：总调用13次，总成本$0.00

### 4. 四级危机干预SOP (`core/risk_detection.py`)
**标准化流程**：
1. **风险识别**：关键词匹配 + LLM二次确认，分为`low/medium/high/urgent`四级
2. **路由控制**：`urgent`和`high`风险强制走GraphRAG检索危机资源
3. **安全后处理**：LangGraph`safety_check`节点强制追加热线，防止LLM遗漏
4. **风险日志**：所有高风险对话自动写入`risk_logs`表，全链路可追溯

**危机干预回复示例**：
> 听到你说"撑不下去了"，我心里一紧。那种孤立无援、被黑暗淹没的感觉，一定非常非常痛苦，你独自承受了这么多，真的辛苦了。
> 
> 你现在说的让我很担心你。此刻你身边有人吗？
> 
> 如果你觉得撑不下去了，请立刻拨打全国心理危机干预热线：400-161-9995，24小时都有受过专业训练的人在等你。

---

## 🚀 快速开始

### 环境准备
- Python 3.10+
- Node.js 18+
- 华为云API Key（用于调用LLM和Embedding服务）

### 1. 克隆项目
```bash
git clone https://github.com/ky0404/yuanxinyeyu.git
cd yuanxinyeyu
```

### 2. 启动后端服务
```bash
# 进入后端目录
cd backend_core

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 创建配置文件
cp .env.example .env

# 编辑.env文件，填入你的配置
# HUAWEI_API_KEY=你的华为云API Key
# HUAWEI_MODEL=deepseek-v3.2
# USE_LANGGRAPH=true  # 开启LangGraph状态机
# LANGFUSE_ENABLED=true  # 开启Langfuse追踪
# LANGFUSE_PUBLIC_KEY=pk-lf-xxx
# LANGFUSE_SECRET_KEY=sk-lf-xxx

# 初始化数据库
python -c "from models.database import init_db; init_db()"

# 构建知识库向量数据库
python scripts/build_knowledge_db.py

# 启动开发服务
uvicorn main:app --reload
```

后端服务启动后，访问 http://127.0.0.1:8000/docs 查看自动生成的API文档。

### 3. 启动前端服务
```bash
# 进入前端目录
cd ../frontend_core

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端服务启动后，访问 http://localhost:5173 即可使用。

---

## 📁 项目结构
```
ky0404-yuanxinyeyu/
├── README.md                    # 项目说明文档
├── LICENSE                      # MIT开源协议
├── backend_core/                # 后端服务
│   ├── main.py                  # 项目启动入口
│   ├── requirements.txt         # Python依赖
│   ├── .env.example             # 环境变量示例
│   ├── agent/                   # LangGraph智能体模块
│   │   ├── graph.py             # 状态机定义与节点实现
│   │   ├── langfuse_client.py   # Langfuse客户端封装
│   │   └── __init__.py
│   ├── api/                     # FastAPI接口
│   │   ├── main.py              # API应用创建
│   │   └── routes/              # 路由模块
│   │       ├── auth_route.py    # 用户认证路由
│   │       ├── emo_route.py     # 情绪分析路由
│   │       ├── history_route.py # 历史记录路由
│   │       ├── stream_route.py  # SSE流式输出路由
│   │       └── ws_route.py      # WebSocket控制路由
│   ├── config/                  # 配置模块
│   │   └── settings.py          # 环境变量配置
│   ├── core/                    # 核心业务逻辑
│   │   ├── analysis.py          # 情绪分析引擎
│   │   └── risk_detection.py    # 风险识别模块
│   ├── data/                    # 数据目录
│   │   ├── chroma_db/           # ChromaDB向量数据库
│   │   ├── emotion_lexicon.json # 情绪镜像词典
│   │   └── contraindications.json # 禁忌话术表
│   ├── knowledge/               # 心理学知识库
│   ├── models/                  # 数据库模型
│   │   ├── database.py          # 数据库连接
│   │   ├── user.py              # 用户模型
│   │   ├── history.py           # 对话历史模型
│   │   └── risk_log.py          # 风险日志模型
│   ├── rag/                     # RAG检索模块
│   │   ├── router.py            # Self-RAG路由
│   │   ├── graph/               # GraphRAG实现
│   │   ├── hybrid/              # 混合检索实现
│   │   └── vector_store/        # 向量存储
│   ├── scripts/                 # 工具脚本
│   │   ├── build_knowledge_db.py # 构建向量数据库
│   │   └── init_rag_demo.py     # 初始化演示数据
│   ├── service/                 # 第三方服务
│   │   ├── huawei_nlp.py        # 华为云LLM服务
│   │   ├── cache_service.py     # 语义缓存服务
│   │   └── feedback_service.py  # 反馈服务
│   └── utils/                   # 工具函数
│       ├── request.py           # HTTP请求工具
│       ├── response.py          # 统一响应格式
│       └── observability/       # 可观测性工具
└── frontend_core/               # 前端应用
    ├── index.html               # HTML入口
    ├── package.json             # NPM依赖
    ├── vite.config.ts           # Vite配置
    └── src/                     # 前端源码
        ├── main.tsx             # 应用入口
        ├── App.tsx              # 主应用组件
        ├── components/          # UI组件
        └── pages/               # 页面组件
```

---

## 📡 API 文档

### 认证接口
| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/auth/register` | POST | 用户注册 |
| `/api/auth/login` | POST | 用户登录 |
| `/api/auth/logout` | POST | 用户登出 |
| `/api/auth/me` | GET | 获取当前用户信息 |

### 情绪分析接口
| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/emo_analysis` | POST | 情绪分析并返回回复 |
| `/api/emo_analysis_stream` | POST | SSE流式情绪分析 |

### 历史记录接口
| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/history` | GET | 获取对话历史 |
| `/api/history` | POST | 保存对话历史 |
| `/api/history` | DELETE | 清空对话历史 |
| `/api/emotion/trends` | GET | 获取情绪趋势数据 |
| `/api/emotion/records` | DELETE | 清空情绪记录 |

### 其他接口
| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/feedback` | POST | 提交用户反馈 |
| `/api/health` | GET | 服务健康检查 |
| `/api/cache/stats` | GET | 缓存统计信息 |
| `/metrics` | GET | Prometheus指标 |

---

## 🚢 部署指南

### 本地部署
按照上述"快速开始"步骤即可在本地运行完整系统。

### 生产部署
1. **后端部署**
   - 使用Gunicorn + UvicornWorker作为WSGI服务器
   - Nginx反向代理，配置HTTPS和HTTP/2
   - 数据库切换为MySQL 8.0+
   - 配置systemd服务实现开机自启
   - 开启Langfuse追踪和Prometheus监控

2. **前端部署**
   - 执行`npm run build`生成静态文件
   - 将`dist`目录部署到Nginx
   - 配置反向代理将API请求转发到后端
   - 开启Gzip压缩和缓存策略

3. **环境变量配置**
   ```env
   ENV=prod
   DATABASE_URL=mysql+pymysql://user:password@localhost:3306/emotion_db
   CORS_ORIGINS=https://dukkha.top
   JWT_SECRET_KEY=你的强密钥
   USE_LANGGRAPH=true
   LANGFUSE_ENABLED=true
   ```

---

## 🎯 项目亮点（校招面试专用）

1. **企业级架构设计**：基于LangGraph状态机编排核心业务流程，实现节点级失败回退和灰度发布
2. **创新的三混合RAG架构**：Self-RAG自动路由+向量检索+知识图谱，在2核2G服务器上实现82%的Precision@3
3. **全链路可观测性**：集成Langfuse实现LLM/RAG/风险识别的全链路追踪，支持问题定位和性能优化
4. **标准化危机干预流程**：参考《中国心理危机干预指南》设计四级风险识别和处理流程，符合行业伦理规范
5. **极致的资源优化**：API-only Embedding方案+纯内存语义缓存，内存占用较本地模型降低85%
6. **完整的反馈闭环**：WebSocket实时反馈+统计分析，为后续DPO微调积累高质量人类偏好数据

---

## 🤝 贡献指南

欢迎提交Issue和Pull Request来帮助改进这个项目！

1. Fork本仓库
2. 创建你的特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交你的更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开一个Pull Request

---

## 📜 开源声明

本项目采用MIT协议开源，主要用于技术研究与心理健康公益交流。

**重要提示**：
- 本系统仅作为情绪陪伴工具，**不能替代专业心理咨询或医学诊断**
- 如遇严重心理问题，请及时寻求专业心理医生帮助
- 如有自伤或自杀倾向，请立即拨打心理援助热线：
  - 全国心理援助热线：400-161-9995
  - 北京心理危机研究院热线：010-82951332

---

## 💗 致谢

- 感谢所有为这个项目贡献代码和想法的朋友
- 感谢华为云提供的大语言模型和MaaS服务
- 感谢LangChain团队开发的LangGraph和Langfuse开源项目
- 感谢Sentence-Transformers和ChromaDB开源项目
- 感谢所有使用这个系统并给予反馈的用户

---

© 2026 YuanXinYeYu Team — 愿每一份情绪都被温柔接住 💗
