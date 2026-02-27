# 🎨 PaperScholar

> AI 驱动的学术图表生成与编辑平台，专为科研人员打造。

[![Python](https://img.shields.io/badge/Python-3.12+-blue?style=flat-square&logo=python)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-14-black?style=flat-square&logo=next.js)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=flat-square&logo=postgresql)](https://postgresql.org)

---

## 功能特性

- **多Agent图表生成**: Retriever → Planner → Stylist → Visualizer → Critic 五Agent协作流水线
- **多Provider LLM支持**: OpenAI兼容 / Google Gemini / Anthropic Claude，支持负载均衡和自动故障切换
- **SSE实时反馈**: 生成过程中实时推送阶段状态和中间图片预览
- **用户管理**: 注册/登录、角色权限、API Key管理、系统API申请审核
- **Chat/Image模型分离配置**: 分别配置不同的Provider、URL、API Key和模型
- **暗色工业技术风UI**: 硬朗的深色工业面板风格，方角设计、等宽字体点缀、网格纹理背景

---

## 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | Next.js 14 + React 18 + TailwindCSS + zustand |
| **后端** | Python 3.12 + FastAPI + SQLAlchemy 2.0 + asyncio |
| **数据库** | PostgreSQL 16 + Redis 7 (规划中) |
| **部署** | Docker Compose |

---

## 快速开始

### 1. 克隆项目

```bash
git clone <repo-url>
cd paperscholar
```

### 2. Docker Compose 一键启动

```bash
# 复制环境变量
cp backend/.env.example backend/.env
# 编辑 .env 文件，填写必要配置（JWT密钥等）

# 启动所有服务
docker-compose up -d
```

服务地址：
- **前端**: http://localhost:3000
- **后端API**: http://localhost:8000
- **API文档**: http://localhost:8000/docs

### 3. 本地开发

**后端**:
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env
uvicorn app.main:app --reload --port 8000
```

**前端**:
```bash
cd frontend
npm install
npm run dev
```

### 4. 首次使用

1. 访问 http://localhost:3000/register 注册账号（**第一个注册的用户自动成为管理员**）
2. 在「API 配置」页面添加你的 LLM API Key
3. 进入「图表生成」页面开始使用

---

## 项目结构

```
paperscholar/
├── frontend/                  # Next.js 前端
│   ├── src/app/              # 页面 (App Router)
│   │   ├── login/            # 登录
│   │   ├── register/         # 注册
│   │   └── dashboard/        # 主功能区
│   │       ├── generate/     # 图表生成
│   │       ├── edit/         # 图表编辑(矢量化+SVG生成)
│   │       ├── refine/       # 精修增强(增强+风格迁移)
│   │       ├── settings/     # API配置
│   │       ├── history/      # 历史记录
│   │       └── admin/        # 管理后台(users/review/config)
│   ├── src/lib/              # API客户端、工具函数
│   ├── src/stores/           # zustand状态管理
│   └── src/components/       # 共享组件(layout/ui)
├── backend/                   # FastAPI 后端
│   └── app/
│       ├── api/              # REST API路由
│       ├── agents/           # Agent Pipeline引擎
│       ├── llm/              # 统一LLM客户端(多Provider+负载均衡)
│       ├── models/           # SQLAlchemy数据库模型
│       ├── schemas/          # Pydantic验证
│       ├── services/         # 业务逻辑(generation/edit/svg/cleanup)
│       ├── prompts/          # Agent提示词模板
│       └── core/             # 安全、数据库连接、中间件
├── docs/                      # 项目文档
│   ├── PRD.md                # 产品需求文档
│   ├── architecture.md       # 技术架构文档
│   ├── database.md           # 数据库设计文档
│   └── api-design.md         # API设计文档
├── docker-compose.yml         # Docker编排
└── README.md
```

---

## 开发路线图

| 阶段 | 状态 | 内容 |
|------|------|------|
| **Phase 1.1** | ✅ 完成 | 项目脚手架 + 数据库模型 + 用户认证 |
| **Phase 1.2** | ✅ 完成 | 统一LLM客户端 + API Key管理 |
| **Phase 1.3** | ✅ 完成 | Agent Pipeline引擎 + SSE实时反馈 |
| **Phase 1.4** | ✅ 完成 | 前端页面 + 管理后台 |
| **Phase 2** | 🔲 计划中 | 结构化数据图表 + 交互优化 |
| **Phase 3** | � 部分实现 | 矢量化编辑(基础API) + 精修增强(基础API) + SVG直接生成 |

---

## 参考项目

本项目融合了以下开源项目的设计理念：

- [PaperBanana](https://github.com/dwzhu-pku/PaperBanana) — 多Agent学术图表生成框架
- [AutoFigure](https://github.com/ResearAI/AutoFigure) — SVG迭代优化生成
- [AutoFigure-Edit](https://github.com/ResearAI/AutoFigure-Edit) — 矢量化编辑Pipeline
- [VoAPI](https://github.com/VoAPI/VoAPI) — API聚合分发系统(用户/API管理参考)
- [Nano-Banana](https://github.com/pili1121/Nano-Banana) — UI风格参考

---

## 许可证

本项目为非商业学术工具，仅供学习和研究使用。
