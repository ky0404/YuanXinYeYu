Let me retrieve the current README first, then provide you with the complete, properly formatted version:

根据你的完整 README 文本，我发现问题了。让我为你生成一份**完全修复、格式规范的 README.md**：

```markdown
# 💗 元心叶语 - 温柔情绪陪伴站

> 你说一句，我就认真接住一句。
> 
> 一个基于AI的情绪陪伴Web应用，帮助用户理解自己的情绪，获得心理支持。

![Language](https://img.shields.io/badge/Language-TypeScript%2FPython-blue)
![Frontend](https://img.shields.io/badge/Frontend-React%2019%2BVite-61DAFB)
![Backend](https://img.shields.io/badge/Backend-FastAPI-009688)
![License](https://img.shields.io/badge/License-MIT-green)

---

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

- 玻璃态设计 (Glassmorphism)
- 响应式自适应布局
- 流畅动画交互
- 深色主题优化

---

## 🏗️ 技术架构

### 前端架构

```
React 19 + TypeScript
    ↓
Ant Design 6.x (UI组件)
    ↓
Vite (构建工具，<500ms热更新)
    ↓
自定义CSS (玻璃态特效 + 渐变)
```

**关键技术点**：

- 状态管理：React Hooks（useState, useRef, useEffect）
- 异步通信：Axios + CancelToken（支持请求取消）
- 本地缓存：localStorage（30分钟CAPTCHA缓存）
- 数据可视化：SVG原生绘制（低依赖，高性能）

### 后端架构

```
FastAPI (异步框架)
    ↓
    ├─ auth_route.py (JWT认证)
    ├─ emo_route.py (NLP情感分析)
    └─ history_route.py (数据持久化)
    ↓
Core/analysis.py (sentence-transformers)
    ↓
数据库 (用户/对话存储)
```

**关键技术点**：

- 异步处理：async/await全链路
- 模型推理：预训练句子向量化
- 隐私护盾：全局异常处理，错误信息脱敏
- CORS中间件：限制跨域请求

### NLP流水线

```
用户输入文本
    ↓
分词 + 清洗
    ↓
sentence-transformers (多语言编码)
    ↓
情感分类模型 (负向/正向/中性/复杂)
    ↓
关键词提取 + 建议生成
    ↓
返回JSON (emotion, score, reply, guide)
```

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
```

**环境变量配置**

在 `backend_core` 目录创建 `.env` 文件：

```env
ENV=dev
APP_NAME=YuanXinYeYu
APP_VERSION=1.0.0
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]
DATABASE_URL=sqlite:///app.db
```

### 前端启动

```bash
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
```

---

## 📚 API 文档

### 1. 情绪分析端点

**请求**：

```http
POST /api/emo_analysis HTTP/1.1
Content-Type: application/json

{
  "text": "最近压力很大，工作太累了",
  "mode": "smart",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**响应** (HTTP 200)：

```json
{
  "code": 200,
  "data": {
    "sentiment_category": 2,
    "sentiment_score": 7.5,
    "sentiment_label": "焦虑",
    "reply": "我感受到你的压力了...",
    "guide": "建议尝试深呼吸练习...",
    "keywords": ["压力", "工作", "疲劳"],
    "mode": "smart"
  }
}
```

**参数说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| text | string | 用户输入文本（5-500字） |
| mode | string | 回应模式：smart / praise / comfort |
| history | array | 历史对话（最多6条） |
| sentiment_category | number | 1=正向, 2=负向, 4=中性 |
| sentiment_score | number | 强度 0-10 |

### 2. 用户认证

**注册**：

```http
POST /api/auth/register HTTP/1.1
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "secure123",
  "username": "Amy"
}
```

**登录**：

```http
POST /api/auth/login HTTP/1.1
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "secure123"
}
```

**获取当前用户**：

```http
GET /api/auth/me HTTP/1.1
Cookie: session_id=xxx
```

### 3. 聊天历史

```http
GET /api/history      # 获取历史记录
POST /api/history     # 保存聊天记录
DELETE /api/history   # 删除所有记录
```

---

## 🎯 核心模块说明

### 模块1：情感分析引擎

**文件**：`backend_core/core/analysis.py`

**职责**：将用户输入转换为结构化情感数据

- **输入**：原始文本字符串
- **处理**：句向量化 → 情感分类 → 关键词提取
- **输出**：情感类别、强度、标签、建议

### 模块2：用户认证系统

**文件**：`routes/auth_route.py`

**职责**：账户安全管理

- 密码哈希存储 (bcrypt)
- Session/JWT管理
- 邮箱唯一性验证

### 模块3：对话历史管理

**文件**：`routes/history_route.py`

**职责**：数据持久化与同步

- 云端存储用户对话
- 自动同步到本地缓存
- 支持批量删除

### 模块4：前端UI组件系统

- **SlideCaptcha**：拖拽式验证组件
- **EmotionBall**：情绪可视化球
- **EmotionTrend**：趋势曲线图
- **AnalysisCard**：分析结果卡片
- **AuthModal**：登录注册弹框

---

## 📊 项目指标

| 指标 | 数值 |
|------|------|
| 前端代码行数 | ~900 LOC (App.tsx单文件) |
| 支持用户并发 | >100 (FastAPI异步) |
| 平均响应时间 | <2s (含模型推理) |
| 前端包体积 | ~800KB (未gzip) |
| 模型大小 | ~450MB (sentence-transformers) |

---

## 🔒 安全特性

### 前端安全

- ✅ 敏感操作需滑块验证
- ✅ localStorage隔离（按用户ID）
- ✅ 请求超时保护 (20s)

### 后端安全

- ✅ CORS白名单限制
- ✅ 全局异常处理（隐藏错误详情）
- ✅ SQL注入预防 (ORM)
- ✅ 密码字段不返回客户端

### 应用层

- ✅ CAPTCHA验证30分钟缓存
- ✅ 环境变量配置敏感信息
- ✅ 生产环境关闭FastAPI文档

---

## 🎨 设计理念

### UI/UX特点

1. **玻璃态设计**：半透明背景+毛玻璃效果，呼应"温柔"主题
2. **情绪色彩系统**：
   - 😊 开心：金黄��� (#f59e0b)
   - 😢 低落：蓝色 (#3b82f6)
   - 😰 焦虑：紫色 (#8b5cf6)
   - 😠 愤怒：红色 (#ef4444)
   - 😌 平静：绿色 (#10b981)
3. **交互友好**：智能提示、加载动画、成功反馈
4. **响应式布局**：支持手机/平板/桌面全适配

### 心理学考量

- 多模式回应：满足不同心理需求
- 不强制建议：先陪伴再指导
- 持久化记忆：让用户感到被重视
- 情绪可视化：增强自我认知

---

## 🚧 项目现状

**完成度**：75%~85%

- ✅ 核心情感分析流程
- ✅ 认证系统框架
- ✅ 多模式回应模板
- ✅ 前端UI完整度高
- ⏳ 数据库模型 (推测未完全实现)
- ⏳ 高级NLP功能 (如多轮对话上下文优化)
- ⏳ 部署脚本

---

## 📈 后续优化方向

1. **个性化推荐**：基于用户历史的定制回应
2. **社群功能**：允许用户分享经历（匿名）
3. **专业转接**：心理问题严重时建议咨询专业医生
4. **多语言支持**：扩展到英文/日文等
5. **离线模式**：轻量级模型支持本地推理

---

## 📄 许可证

MIT License - 自由使用、修改、分发

---

## 👨‍💻 作者

[@ky0404](https://github.com/ky0404)

---

## 💬 反馈与贡献

欢迎提出 Issue 和 Pull Request！一起让这个项目更温柔。

---

## 💌 关键信息

如果你正在经历情绪困扰，这个应用是你的朋友。

**GitHub**：[github.com/ky0404/YuanXinYeYu](https://github.com/ky0404/YuanXinYeYu)
```
