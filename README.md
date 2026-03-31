# 媛心烨语 - 温柔情绪陪伴站

> 💗 你说一句，我就认真接住一句。
> 
> 一个基于AI的情绪陪伴Web应用，帮助用户理解自己的情绪，获得心理支持。

![Language](https://img.shields.io/badge/Language-TypeScript%2FPython-blue)
![Frontend](https://img.shields.io/badge/Frontend-React%2019%2BVite-61DAFB)
![Backend](https://img.shields.io/badge/Backend-FastAPI-009688)
![License](https://img.shields.io/badge/License-MIT-green)

## ✨ 核心特性

### 🧠 三大陪伴模式
- **✨ 智能分析**：深度解析情绪根源，提供心理学建议
- **🌈 暖心夸夸**：发现你的闪光点，增强价值感
- **☁️ 温柔安慰**：先陪着你，给予情感支持

### 📊 实时情绪追踪
- 情绪强度量化（1-10分）
- 交互式趋势图表（SVG渲染）
- 关键词提取与情感标签

### 🔐 安全隐私设计
- 用户认证（邮箱/密码）
- 云端智能同步
- 滑块验证反爬虫
- CORS严格限制

### 🎨 现代化UI
- 玻璃态设计(Glassmorphism)
- 响应式自适应布局
- 流畅动画交互
- 深色主题优化

---

## 🏗️ 技术架构

### 前端架构
React 19 + TypeScript ↓ Ant Design 6.x (UI组件) ↓ Vite (构建工具，<500ms热更新) ↓ 自定义CSS (玻璃态特效 + 渐变)

**关键技术点**：
- 状态管理：React Hooks（useState, useRef, useEffect）
- 异步通信：Axios + CancelToken（支持请求取消）
- 本地缓存：localStorage（30分钟CAPTCHA缓存）
- 数据可视化：SVG原生绘制（低依赖，高性能）

### 后端架构
FastAPI (异步框架) ↓ ├─ auth_route.py (JWT认证) ├─ emo_route.py (NLP情感分析) └─ history_route.py (数据持久化) ↓ Core/analysis.py (sentence-transformers) ↓ 数据库 (用户/对话存储)

**关键技术点**：
- 异步处理：async/await全链路
- 模型推理：预训练句子向量化
- 隐私护盾：全局异常处理，错误信息脱敏
- CORS中间件：限制跨域请求

### NLP流水线
用户输入文本 ↓ 分词 + 清洗 ↓ sentence-transformers (多语言编码) ↓ 情感分类模型 (负向/正向/中性/复杂) ↓ 关键词提取 + 建议生成 ↓ 返回JSON (emotion, score, reply, guide)

---

## 🚀 快速启动

### 前置需求
- Node.js 18+
- Python 3.8+
- pip, npm/pnpm

### 后端启动

```bash
cd backend_core

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 安装依赖
pip install fastapi uvicorn python-dotenv sentencepiece transformers

# 启动服务器 (localhost:8000)
python api/main.py

环境变量 (.env)：
ENV=dev
APP_NAME=YuanXinYeYu
APP_VERSION=1.0.0
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]
DATABASE_URL=sqlite:///app.db
前端启动
bash
cd frontend_core

# 安装依赖
npm install
# 或
pnpm install

# 启动开发服务器 (localhost:5173)
npm run dev

# 构建生产版本
npm run build

# 预览生产构建
npm run preview
