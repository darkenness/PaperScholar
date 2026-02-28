# PaperScholar

> AI 驱动的学术图表生成与编辑平台，专为科研人员打造。

[![Python](https://img.shields.io/badge/Python-3.12+-blue?style=flat-square&logo=python)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-14.2-black?style=flat-square&logo=next.js)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=flat-square&logo=postgresql)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=flat-square&logo=redis)](https://redis.io)

---

## 功能特性

### 图表生成

- **多 Agent 协作流水线**: Retriever → Planner → Stylist → Visualizer → Critic → Polish 六 Agent 协同，支持 7 种 Pipeline 模式（vanilla / dev_planner / dev_planner_stylist / dev_planner_critic / dev_full / demo_full / demo_planner_critic）
- **双类型支持**: 示意图（Diagram）通过图像生成模型直出，统计图（Plot）通过生成 matplotlib 代码执行
- **多候选并行生成**: 单次任务最多生成 20 个候选图，Critic 可配置 1-5 轮迭代优化
- **NeurIPS 2025 风格指南**: 内置 Diagram / Plot 两套学术风格指南，规范颜色、排版、图标语义
- **参考示例检索**: 基于 PaperBananaBench 数据集的 in-context learning，支持 auto / random / manual / none 四种检索模式
- **SSE 实时反馈**: 生成过程实时推送阶段状态、中间图片预览、Critic 反馈

### 图表编辑

- **SAM3 矢量化分割**: 调用 fal.ai / Roboflow 的 SAM3 API 进行图像语义分割
- **SVG 模板生成**: 自动从分割结果生成带占位符的 SVG 模板
- **SVG 迭代优化**: AutoFigure 风格的 Review-Refine 循环，生成 → 评分 → 改进直至达标

### 精修增强

- **AI 图像增强**: 支持 2K / 4K 分辨率输出
- **风格迁移**: 从参考图提取风格并迁移至目标图

### 多 Provider LLM 支持

- **三大 Provider**: OpenAI 兼容（OpenRouter、中转站等）/ Google Gemini / Anthropic Claude
- **Chat / Image 模型分离配置**: 独立配置 Provider、URL、API Key 和模型
- **负载均衡与故障转移**: 优先级轮询、指数退避重试、连续失败自动禁用
- **系统共享 API**: 管理员配置系统密钥，已审批用户可共享使用

### 用户与管理

- **用户认证**: 注册 / 登录、邮箱验证码、JWT 令牌（7 天过期）
- **角色权限**: 管理员 / 普通用户，首个注册用户自动成为管理员
- **API Key 管理**: 加密存储（Fernet AES-256）、在线验证、优先级排序
- **系统 API 申请审核**: 用户申请 → 管理员审核 → 共享系统密钥
- **管理后台**: 用户管理、申请审核、系统配置、API 密钥管理、公告管理、系统统计
- **API 用量追踪**: 记录 Token 消耗、调用延迟、成功 / 失败状态

---

## 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | Next.js 14.2 (App Router) + React 18.3 + TailwindCSS 3.4 + Zustand 4.5 + Lucide Icons |
| **后端** | Python 3.12 + FastAPI 0.115 + SQLAlchemy 2.0 (async) + Pydantic 2.10 + Alembic |
| **LLM** | openai 1.58 + google-genai 1.5 + anthropic 0.42 |
| **数据库** | PostgreSQL 16 + Redis 7 |
| **部署** | Docker Compose + Nginx 反向代理 |

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
# 编辑 .env 文件，填写必要配置（SECRET_KEY、JWT_SECRET_KEY、API_KEY_ENCRYPTION_KEY）

# 启动所有服务（PostgreSQL + Redis + Backend + Frontend）
docker-compose up -d
```

服务地址：
- **前端**: http://localhost:3000
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs

### 3. 本地开发

**后端**:
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env（配置 DATABASE_URL、REDIS_URL 等）
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
2. 在「API 配置」页面添加你的 LLM API Key（分别配置 Chat 和 Image 模型）
3. 进入「图表生成」页面，选择 Pipeline 模式开始使用

---

## 项目结构

```
paperscholar/
├── frontend/                      # Next.js 前端
│   ├── src/
│   │   ├── app/                   # 页面 (App Router)
│   │   │   ├── login/             # 登录
│   │   │   ├── register/          # 注册
│   │   │   └── dashboard/         # 主功能区
│   │   │       ├── generate/      # 图表生成（SSE 实时流）
│   │   │       ├── edit/          # 图表编辑（矢量化 + SVG 生成）
│   │   │       ├── refine/        # 精修增强（增强 + 风格迁移）
│   │   │       ├── history/       # 历史记录（分页 + 过滤）
│   │   │       ├── settings/      # API 配置（Chat/Image 分离）
│   │   │       └── admin/         # 管理后台
│   │   │           ├── users/     # 用户管理
│   │   │           ├── review/    # 申请审核
│   │   │           └── config/    # 系统配置 + 公告 + 统计
│   │   ├── components/            # 共享组件
│   │   │   ├── layout/Sidebar.tsx # 响应式侧边栏
│   │   │   ├── ModelSelector.tsx  # 模型选择器
│   │   │   └── ui/               # ThemeToggle / Toaster / Skeleton
│   │   ├── lib/                   # API 客户端、工具函数
│   │   └── stores/                # Zustand 状态（auth / theme / sidebar）
│   └── Dockerfile                 # 多阶段构建（node:20-alpine）
├── backend/                       # FastAPI 后端
│   ├── app/
│   │   ├── api/                   # REST API 路由（8 个模块）
│   │   │   ├── auth.py            # 认证（注册/登录/验证码）
│   │   │   ├── api_keys.py        # API Key 管理
│   │   │   ├── applications.py    # 系统 API 申请
│   │   │   ├── generate.py        # 图表生成 + SSE 流
│   │   │   ├── edit.py            # 矢量化编辑
│   │   │   ├── refine.py          # 精修增强
│   │   │   ├── references.py      # 参考图管理
│   │   │   └── admin.py           # 管理后台
│   │   ├── agents/                # Agent Pipeline
│   │   │   ├── pipeline.py        # PipelineEngine + 5 个 Agent
│   │   │   ├── retriever_agent.py # 参考示例检索
│   │   │   ├── polish_agent.py    # 最终精修
│   │   │   └── style_guides/      # NeurIPS 2025 风格指南（md）
│   │   ├── llm/                   # 统一 LLM 客户端
│   │   │   ├── base_client.py     # 抽象接口
│   │   │   ├── openai_client.py   # OpenAI 兼容
│   │   │   ├── gemini_client.py   # Gemini Native
│   │   │   ├── anthropic_client.py# Anthropic Claude
│   │   │   ├── load_balancer.py   # 负载均衡 + 故障转移
│   │   │   └── client_factory.py  # 工厂模式
│   │   ├── models/                # SQLAlchemy 模型（10 张表）
│   │   ├── schemas/               # Pydantic 验证
│   │   ├── services/              # 业务逻辑
│   │   │   ├── generation_service.py  # 生成任务调度
│   │   │   ├── edit_service.py        # SAM3 + SVG 模板
│   │   │   ├── svg_service.py         # SVG 迭代优化
│   │   │   ├── usage_service.py       # API 用量统计
│   │   │   └── cleanup_service.py     # 过期文件清理
│   │   ├── prompts/               # Agent 提示词模板
│   │   └── core/                  # 安全、数据库、中间件、限流
│   ├── alembic/                   # 数据库迁移
│   └── Dockerfile                 # python:3.12-slim
├── docs/                          # 项目文档
│   ├── PRD.md                     # 产品需求文档
│   ├── architecture.md            # 技术架构文档
│   ├── api-design.md              # API 设计文档
│   ├── database.md                # 数据库设计文档
│   └── dev-plan-paperbanana.md    # PaperBanana 复刻开发计划
├── docker-compose.yml             # 四服务编排（DB + Redis + Backend + Frontend）
├── nginx.conf                     # Nginx 反向代理
├── deploy_setup.sh                # 部署环境配置
├── server_setup.sh                # 服务器初始化
└── README.md
```

---

## API 端点概览

| 模块 | 路径前缀 | 主要端点 |
|------|----------|----------|
| 认证 | `/api/v1/auth` | 注册、登录、验证码、用户信息 |
| API Key | `/api/v1/api-keys` | CRUD、验证 |
| 申请 | `/api/v1/api-applications` | 创建申请、查看我的申请 |
| 生成 | `/api/v1/generate` | 创建任务、SSE 流、历史列表、下载 ZIP、收藏 |
| 编辑 | `/api/v1/edit` | 矢量化管道、SVG 生成 |
| 精修 | `/api/v1/refine` | 图像增强、风格迁移 |
| 参考图 | `/api/v1/references` | 上传（24h TTL）、列表、删除 |
| 管理 | `/api/v1/admin` | 用户管理、申请审核、系统密钥、配置、公告、统计 |
| 公开 | `/api/v1/announcements` | 活跃公告 |
| 健康 | `/api/health` | 健康检查 |

完整 API 文档：启动后访问 http://localhost:8000/docs (Swagger UI)

---

## Agent Pipeline 架构

```
用户输入（方法文本 + 图表标题）
        │
        ▼
┌─────────────┐   auto/random/manual/none
│  Retriever  │ ← PaperBananaBench 数据集检索 Top-10 参考示例
└──────┬──────┘
       │ 参考示例
       ▼
┌─────────────┐
│   Planner   │ ← 基于参考示例 in-context learning，生成详细图表描述
└──────┬──────┘
       │ 图表描述
       ▼
┌─────────────┐
│   Stylist   │ ← 注入 NeurIPS 2025 风格指南，精炼视觉细节
└──────┬──────┘
       │ 精炼描述
       ▼
┌─────────────┐
│ Visualizer  │ ← Diagram: 图像模型直出 / Plot: matplotlib 代码生成执行
└──────┬──────┘
       │ 生成图像
       ▼
┌─────────────┐
│   Critic    │ ← 多轮迭代评估，输出改进建议 + 修订描述
└──────┬──────┘   （最多 N 轮，"No changes needed" 提前终止）
       │
       ▼
┌─────────────┐
│   Polish    │ ← 最终精修，基于风格指南生成改进版本
└─────────────┘
```

---

## 数据库模型

共 10 张表：

| 表名 | 说明 |
|------|------|
| `users` | 用户（角色、系统 API 审批状态） |
| `api_key_configs` | API 密钥配置（加密存储、Chat/Image 分类、优先级） |
| `api_applications` | 系统 API 使用申请 |
| `generation_tasks` | 生成任务（类型、状态、进度、使用的模型信息） |
| `generation_results` | 生成结果（图片路径、质量评分、Agent 描述、Critic 反馈） |
| `pipeline_events` | Pipeline SSE 事件记录 |
| `uploaded_references` | 用户上传参考图（24h TTL） |
| `system_configs` | 系统配置（键值对） |
| `announcements` | 系统公告 |
| `api_usage_logs` | API 调用日志（Token / 延迟 / 成功率） |

---

## 开发路线图

| 阶段 | 状态 | 内容 |
|------|------|------|
| **Phase 1.1** | ✅ 完成 | 项目脚手架 + 数据库模型（10 张表）+ 用户认证 + 角色权限 |
| **Phase 1.2** | ✅ 完成 | 统一 LLM 客户端（3 Provider）+ 负载均衡 + API Key 管理 |
| **Phase 1.3** | ✅ 完成 | 6 Agent Pipeline 引擎 + 7 种管道模式 + SSE 实时反馈 |
| **Phase 1.4** | ✅ 完成 | 前端全部页面 + 响应式 UI + 暗色/亮色主题 + 管理后台 |
| **Phase 2** | ✅ 完成 | 矢量化编辑（SAM3 分割 + SVG 模板）+ SVG 迭代优化 + 精修增强 + 风格迁移 |
| **Phase 3** | 🔄 进行中 | PaperBanana 提示词深度复刻 + 风格指南完善 + Critic 迭代回滚 |
| **Phase 4** | 🔲 计划中 | 评估框架 + Pipeline Evolution 可视化 + 风格指南自动生成工具 |

---

## 部署

### Docker Compose（开发 / 测试）

```bash
docker-compose up -d
# 服务：PostgreSQL:5432 + Redis:6379 + Backend:8000 + Frontend:3000
```

### 生产环境

项目提供了 Nginx 反向代理配置和服务器初始化脚本：

```bash
# 服务器初始化（配置镜像源、防火墙、环境变量）
bash server_setup.sh

# 或使用部署脚本（生成密钥、启动服务）
bash deploy_setup.sh
```

生产部署架构：`Nginx:80` → `Frontend:3000` / `Backend:8000` → `PostgreSQL:5432` + `Redis:6379`

---

## 参考项目

本项目融合了以下开源项目的设计理念：

- [PaperBanana](https://github.com/dwzhu-pku/PaperBanana) — 多 Agent 学术图表生成框架
- [AutoFigure](https://github.com/ResearAI/AutoFigure) — SVG 迭代优化生成
- [AutoFigure-Edit](https://github.com/ResearAI/AutoFigure-Edit) — 矢量化编辑 Pipeline
- [VoAPI](https://github.com/VoAPI/VoAPI) — API 聚合分发系统（用户 / API 管理参考）
- [Nano-Banana](https://github.com/pili1121/Nano-Banana) — UI 风格参考

---

## 许可证

本项目为非商业学术工具，仅供学习和研究使用。
