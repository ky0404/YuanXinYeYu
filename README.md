# 🌸 媛心烨语 · AI 情绪陪伴与心理疏导系统

> 温婉如媛，明亮如烨 —— 一个懂你情绪、会安慰人的心灵 AI 伴侣。
> 
> 愿每一份情绪都被温柔接住，每一个孤独的时刻都有陪伴。

[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-Frontend-blue)](https://reactjs.org/)
[![Huawei Cloud](https://img.shields.io/badge/Huawei%20Cloud-LLM-brightgreen)](https://www.huaweicloud.com)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9+-blue)](https://www.typescriptlang.org/)

---

## ✨ 项目简介

**媛心烨语（YuanXinYeYu）** 是一款专为大学生群体打造的AI情绪陪伴系统，整合了大语言模型与专业心理学知识库，通过自然语言理解与共情式引导，为用户提供安全、温暖、私密的情绪倾诉空间。

系统采用前后端分离架构，集成了智能情绪识别、RAG检索增强、危机干预、情绪趋势追踪等核心功能，旨在成为用户身边24小时在线的"心灵树洞"。

**在线体验**：[https://dukkha.top](sslocal://flow/file_open?url=https%3A%2F%2Fdukkha.top&flow_extra=eyJsaW5rX3R5cGUiOiJjb2RlX2ludGVycHJldGVyIn0=)

---

## 🎯 核心功能

| 功能 | 描述 |
|------|------|
| 💬 **智能情绪陪伴** | 三种模式（智能分析/暖心夸夸/温柔安慰），生成自然共情式回复 |
| 🧠 **RAG 知识增强** | 内置大学生专属心理知识库，让AI回复更专业、更有温度 |
| 🚦 **四级危机干预** | 自动识别自杀、自残等高风险信号，触发安全提示与热线推荐 |
| ☁️ **云端数据同步** | 用户注册登录后，对话历史与情绪记录永久云端保存 |
| 📊 **情绪趋势追踪** | 可视化展示用户近期情绪变化，帮助用户了解自己的心理状态 |
| 🔒 **隐私安全保护** | 全局异常脱敏、游客模式、一键清空记录，全方位保护用户隐私 |
| ⚡ **SSE 流式输出** | 打字机效果回复，模拟真实聊天体验 |
| 📝 **用户反馈系统** | 支持点赞/踩/重新生成，持续优化AI回复质量 |

---

## 🛠 技术栈

### 前端技术栈
- **框架**：React 19 + TypeScript 5.9+
- **构建工具**：Vite 8
- **UI 组件**：Ant Design 6
- **HTTP 客户端**：Axios
- **样式**：原生 CSS + 毛玻璃效果
- **PWA 支持**：可安装为桌面应用

### 后端技术栈
- **Web 框架**：FastAPI + Uvicorn
- **ORM**：SQLAlchemy 2.0
- **数据验证**：Pydantic
- **日志系统**：Python JSON Logger + 滚动日志
- **异步 HTTP**：aiohttp

### AI 与数据层
- **大语言模型**：华为云 DeepSeek v3.2
- **向量数据库**：ChromaDB
- **嵌入模型**：Sentence-Transformers MiniLM
- **知识图谱**：SQLite 实现的轻量级 GraphRAG
- **数据库**：SQLite（默认）/ MySQL（可选）

### 安全与运维
- **认证**：JWT + HttpOnly Cookie
- **限流**：游客每日 5 次免费额度
- **可观测性**：Langfuse 追踪（可选）
- **部署**：支持 Nginx + Gunicorn 生产部署

---

## 🚀 快速开始

### 环境准备
- Python 3.10+
- Node.js 18+
- 华为云 API Key（用于调用 LLM 服务）

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
# 编辑 .env 文件，填入你的华为云 API Key
# HUAWEI_API_KEY=你的华为云API Key
# HUAWEI_MODEL=deepseek-v3.2

# 初始化数据库
python -c "from models.database import init_db; init_db()"

# 构建知识库向量数据库
python scripts/build_knowledge_db.py

# 启动服务
uvicorn main:app --reload
```

后端服务启动后，访问 http://127.0.0.1:8000/docs 查看 API 文档。

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
├── LICENSE                      # MIT 开源协议
├── backend_core/                # 后端服务
│   ├── main.py                  # 项目启动入口
│   ├── requirements.txt         # Python 依赖
│   ├── .env.example             # 环境变量示例
│   ├── agent/                   # LangGraph 智能体模块
│   ├── api/                     # FastAPI 接口
│   │   ├── main.py              # API 应用创建
│   │   └── routes/              # 路由模块
│   │       ├── auth_route.py    # 用户认证路由
│   │       ├── emo_route.py     # 情绪分析路由
│   │       ├── history_route.py # 历史记录路由
│   │       ├── stream_route.py  # SSE 流式输出路由
│   │       └── ws_route.py      # WebSocket 控制路由
│   ├── config/                  # 配置模块
│   ├── core/                    # 核心业务逻辑
│   ├── data/                    # 数据目录
│   │   ├── chroma_db/           # ChromaDB 向量数据库
│   │   └── models/              # 本地嵌入模型缓存
│   ├── knowledge/               # 心理学知识库
│   ├── models/                  # 数据库模型
│   ├── rag/                     # RAG 检索模块
│   │   ├── graph/               # GraphRAG 实现
│   │   ├── hybrid/              # 混合检索实现
│   │   ├── self_rag/            # Self-RAG 路由
│   │   └── vector_store/        # 向量存储
│   ├── scripts/                 # 工具脚本
│   ├── service/                 # 第三方服务
│   └── utils/                   # 工具函数
└── frontend_core/               # 前端应用
    ├── index.html               # HTML 入口
    ├── package.json             # NPM 依赖
    ├── vite.config.ts           # Vite 配置
    ├── eslint.config.js         # ESLint 配置
    └── src/                     # 前端源码
        ├── main.tsx             # 应用入口
        ├── App.tsx              # 主应用组件
        └── App.css              # 全局样式
```

---

## 🧩 核心模块介绍

### 情绪分析引擎 (`core/analysis.py`)
- 调用华为云 LLM 服务进行情绪识别和回复生成
- 支持四级风险分级（urgent/high/medium/low）
- 自动降级机制：网络异常时使用本地模型兜底

### 三混合 RAG 系统 (`rag/`)
- **Self-RAG**：基于启发式规则决定是否需要检索及检索类型
- **VectorRAG**：ChromaDB 向量检索，捕捉语义相似性
- **GraphRAG**：SQLite 实现的轻量级知识图谱，提供结构化知识和危机资源
- **HybridRAG**：合并向量和图谱结果，加权排序

### 语义缓存服务 (`service/cache_service.py`)
- 基于语义相似度的请求缓存，相似度阈值 92%
- 降低重复 API 调用约 35%，节省接口成本
- 纯内存实现，无需外部依赖，2G 内存友好

### 前端交互系统
- 温暖治愈系毛玻璃风格 UI
- SSE 流式输出，打字机效果
- 情绪能量球可视化
- 响应式设计，完美适配移动端
- PWA 支持，可安装为桌面应用

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
| `/api/emo_analysis_stream` | POST | SSE 流式情绪分析 |

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

---

## 🚢 部署指南

### 本地部署
按照上述"快速开始"步骤即可在本地运行完整系统。

### 生产部署
1. **后端部署**
   - 使用 Gunicorn + UvicornWorker 作为 WSGI 服务器
   - Nginx 反向代理，配置 HTTPS
   - 数据库切换为 MySQL/PostgreSQL
   - 配置 systemd 服务实现开机自启

2. **前端部署**
   - 执行 `npm run build` 生成静态文件
   - 将 `dist` 目录部署到 Nginx
   - 配置反向代理将 API 请求转发到后端

3. **环境变量配置**
   - 设置 `ENV=prod`
   - 配置生产环境数据库连接
   - 配置 CORS 允许的域名
   - 配置 JWT 密钥

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request 来帮助改进这个项目！

1. Fork 本仓库
2. 创建你的特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交你的更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开一个 Pull Request

---

## 📜 开源声明

本项目采用 MIT 协议开源，主要用于技术研究与心理健康公益交流。

**重要提示**：
- 本系统仅作为情绪陪伴工具，**不能替代专业心理咨询或医学诊断**
- 如遇严重心理问题，请及时寻求专业心理医生帮助
- 如有自伤或自杀倾向，请立即拨打心理援助热线：
  - 全国心理援助热线：400-161-9995
  - 北京心理危机研究院热线：010-82951332

---

## 💗 致谢

- 感谢所有为这个项目贡献代码和想法的朋友
- 感谢华为云提供的大语言模型服务
- 感谢 Sentence-Transformers 和 ChromaDB 开源项目
- 感谢所有使用这个系统并给予反馈的用户

---

© 2026 YuanXinYeYu Team — 愿每一份情绪都被温柔接住 💗
