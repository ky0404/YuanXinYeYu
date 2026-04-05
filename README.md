当然可以！我已阅读你提供的原始 README 与项目结构。  
以下是优化、整理后的新版 **README.md**，  
保留了原有风格与技术细节，但结构更清晰、表达更专业，便于开源展示与团队协作。  

---

# 🌸 媛心烨语 · AI 情绪陪伴与心理疏导系统

> 温婉如媛，明亮如烨 —— 一个懂你情绪、陪你聊天的心灵 AI 伴侣。

[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-Frontend-blue)](https://reactjs.org/)
[![Huawei ModelArts LLM](https://img.shields.io/badge/Huawei%20Cloud-LLM-brightgreen)](https://www.huaweicloud.com)

---

## 🌟 项目简介

**媛心烨语（YuanXinYeYu）** 是一款结合大语言模型与情绪心理知识库的 AI 情感陪伴系统。  
它通过自然语言理解与共情式引导，让用户在安全、温暖的空间中自由表达与自我疗愈。

主要特点：

- 💬 智能情绪识别与自然共情回复  
- 🧠 RAG 检索增强，将心理学知识融入生成逻辑  
- 🚦 危机识别与安全分流，提供心理援助热线  
- ☁️ 用户注册 / 登录 / 云端历史同步  
- 📊 情绪趋势追踪与可视化  
- 🔒 日志脱敏 + 隐私保护 + 游客每日配额控制  

---

## 🏗 技术架构

### 前后端分离 · 现代全栈方案

| 层级 | 技术栈 |
|------|--------|
| 前端 | React 19 + Vite 8 + TypeScript + Ant Design 6 + Axios |
| 后端 | FastAPI + SQLAlchemy + Pydantic + Uvicorn |
| 数据库 | SQLite（默认，可替换为 MySQL/PostgreSQL） |
| AI 核心 | 华为云 ModelArts LLM（DeepSeek v3.2） + ChromaDB 向量检索 + SentenceTransformer MiniLM |
| 安全认证 | JWT 鉴权 + Cookie SameSite 策略 + 异常脱敏日志 |
| 可观测 | Langfuse 追踪（可选）+ JSON 结构化日志 |
| 部署兼容 | 支持 systemd 守护与 Nginx 反向代理 |

---

## ⚙️ 快速启动

### 后端部署

```bash
cd backend_core

# 1. 创建虚拟环境并安装依赖
python -m venv venv
source venv/bin/activate   # Windows 使用 venv\Scripts\activate
pip install -r requirements.txt

# 2. 创建 .env 配置
HOST=127.0.0.1
PORT=8000
ENV=dev
DATABASE_URL=sqlite:///./emotion.db
HUAWEI_API_KEY=你的华为云Key
HUAWEI_API_BASE=https://api.huaweicloud.com
HUAWEI_MODEL=deepseek-v3.2

# 3. 初始化数据库
python -c "from models.database import init_db; init_db()"

# 4. 启动服务
uvicorn main:app --reload
```

接口文档（仅开发环境）：  
👉 http://127.0.0.1:8000/docs  

---

### 前端运行

```bash
cd frontend_core
npm install
npm run dev
```

浏览器访问：  
👉 http://localhost:5173 （Vite 自动代理到后端）

---

## 📡 API 总览

### 🔐 用户认证

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/auth/register` | POST | 注册用户 |
| `/api/auth/login` | POST | 登录（返回 JWT） |
| `/api/auth/logout` | POST | 登出 |
| `/api/auth/me` | GET | 获取当前用户信息 |

---

### 💬 情绪分析与对话

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/emo_analysis` | POST | 分析情绪并生成 AI 回复 |
| `/api/emo_analysis_stream` | POST | **SSE 流式输出**版（支持打字机效果） |
| `/api/mood/process` | POST | 向后兼容接口 |

示例：

```json
{
  "text": "最近总觉得很焦虑，晚上睡不着",
  "mode": "smart",
  "history": [{"role": "user", "content": "上周也是这样"}]
}
```

返回：

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

---

### 🕘 历史记录与趋势分析

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/history` | GET | 获取历史对话 |
| `/api/history` | POST | 保存历史记录 |
| `/api/history` | DELETE | 清空对话 |
| `/api/emotion/trends` | GET | 获取情绪趋势 |
| `/api/emotion/records` | DELETE | 清空所有情绪记录 |

---

## 🧠 系统模块说明

| 模块 | 文件 | 功能 |
|------|------|------|
| 情绪分析引擎 | `core/analysis.py` | 统一调用 Huawei LLM 服务 |
| RAG 检索模块 | `service/rag_service.py` | 向量 + 关键词混合检索 |
| 语义缓存层 | `service/cache_service.py` | 92% 相似度命中跳过重复调用 |
| 消息流接口 | `api/routes/stream_route.py` | SSE 增强版流式回复 |
| 心理知识库 | `knowledge/emotion_knowledge.py` | 学生情绪知识条目 v2.0 |
| 前端 UI | `frontend_core/src/App.tsx` | 主界面 + 趋势图 + 验证 + 登录 |
| 样式主题 | `frontend_core/src/App.css` | 毛玻璃视觉 + 暖色治愈风格 |

---

## ✨ 技术亮点

- 🧩 **RAG 语义检索融合** —— ChromaDB + SentenceTransformer 结合，实现上下文增强  
- 🧭 **风险分级 detect_risk_level()** —— 自动识别 `urgent / high / medium / low`  
- 🧑‍🤝‍🧑 **共情式 Prompt 模板** —— 模拟心理咨询师语气，不暴露 AI 身份  
- 🔐 **游客配额机制** —— 每日 IP 限 5 次，防滥用  
- 💾 **语义缓存层** —— 近似匹配 92% 自动复用结果，节省 API 成本  
- ☁️ **PWA & 云端同步** —— 前端支持离线模式与 Cookie 登录  
- 💬 **SSE 流式输出** —— 实现自然的“打字回复”动态展示  

---

## 📚 知识库与向量检索

### 情感知识库
文件：`backend_core/knowledge/emotion_knowledge.py`

- 覆盖九类心理主题：学业、人际、恋爱、就业、自我、家庭、健康、压力、成长  
- 每条记录包含：
  - `content` 心理学分析  
  - `advice` 行动建议  
  - `dialogue_example` 共情回复示例  
  - `audience` 目标人群  
  - `emotion_type` 情绪类型  
  - `risk_level` 风险等级  

### 向量构建脚本
```bash
cd backend_core
python scripts/build_knowledge_db.py
```
自动生成 ChromaDB 向量数据库并输出检索测试结果。

---

## 🧪 开发建议

- 正式部署可采用 `Nginx + Gunicorn (UvicornWorker)`  
- SQLite 可切换为 PostgreSQL 以提升并发  
- 前端支持 PWA 改造，提供离线聊天体验  
- 可集成 WebSocket 以实现实时流式互动与反馈  

---

## 🤝 项目定位与价值

传统心理陪伴 App 面临两大痛点：  
1. 🤖 AI 回复生硬、难以共情  
2. 🧍‍♀️ 真人咨询人力有限、难以 7×24 响应  

**媛心烨语** 的目标是让 AI 化身一位温柔的倾听者：
> 它能理解情绪，也能回应情绪；能在深夜里，成为你安全的心灵港湾。

用户获得的，是持续的陪伴与自我觉察能力的提升。

---

## 📜 开源声明

本项目用于心理健康公益与技术研究，  
严禁将模型输出作为**医疗诊断或心理危机干预**的替代。  

---

© 2026 YuanXinYeYu Team  
愿每一份情绪都被温柔接住 💗

---

是否希望我继续为你生成一份  
👉 **英文版 README.md（国际展示/竞赛投稿版）**？
