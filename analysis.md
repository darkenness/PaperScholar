# PaperScholar 项目分析报告

## 一、参考项目深度分析

---

### 1. PaperBanana — 多Agent学术图表生成框架

**核心架构**: 五Agent协作流水线（异步Python）

| Agent | 职责 | 模型类型 |
|-------|------|----------|
| **Retriever** | 从参考集中检索最相关的参考图表（Top10）| Chat (Gemini) |
| **Planner** | 根据method内容+参考示例生成详细图表描述 | Chat (Gemini) |
| **Stylist** | 根据Style Guide润色描述，确保学术审美 | Chat (Gemini) |
| **Visualizer** | 将描述转为图像（diagram用Image模型；plot用代码生成） | Image (Gemini) / Chat+Code |
| **Critic** | 多轮迭代审查，与Visualizer形成闭环 | Chat (Gemini) |
| **Polish** | 精修/上采样到2K/4K | Image (Gemini) |

**Pipeline模式**:
- `vanilla`: 直接生成（无规划无精修）
- `dev_planner`: Planner → Visualizer
- `dev_planner_stylist`: Planner → Stylist → Visualizer
- `dev_planner_critic`: Planner → Visualizer → Critic循环
- `dev_full`: 全pipeline（Retriever → Planner → Stylist → Visualizer → Critic循环）

**并发机制**: 使用 `asyncio.Semaphore` 控制并发（默认max=50），批量处理多个候选图

**API调用**: 
- 仅支持 Google Gemini API（`google.genai` SDK）
- 支持 OpenAI gpt-image 模型（新增）
- 配置通过 YAML 文件（`configs/model_config.yaml`）
- chat模型和image模型分开配置（`model_name` / `image_model_name`）

**前端**: Streamlit（`demo.py`，约39k行），两个Tab：Generate Candidates + Refine Image

**关键痛点（你提到的）**:
- ⚠️ 等待时间长，过程中无反馈交互
- ⚠️ 仅支持 Gemini API，无多Provider支持
- ⚠️ 无用户管理，无API Key管理
- ⚠️ 无负载均衡

---

### 2. AutoFigure — SVG/mxGraph迭代优化生成

**核心架构**: Generate → Evaluate → Improve 迭代循环（同步Python）

| 阶段 | 职责 | 说明 |
|------|------|------|
| **生成初始代码** | LLM生成SVG或mxGraph XML | 支持paper/survey/blog/textbook四种主题 |
| **评估** | Critic评分(0-10)，三维度：aesthetic_design / content_fidelity / placeholder_usage | 多模态输入：PNG+代码+参考图 |
| **改进** | 基于评估反馈重新生成改进版代码 | 迭代直到达到质量阈值(默认9.0) |
| **增强** | AI美化（可选），支持code/code2prompt/none三种输入模式 | 多Provider支持 |

**LLM调用**: 
- 统一接口 `call_unified_llm()`，基于 OpenAI SDK
- 支持 OpenRouter / Bianxie / Gemini 三种Provider
- 每个Provider独立配置 base_url / api_key / model

**SDK设计**: 
- `Config` dataclass 统一管理配置
- generation / methodology / enhancement 三套独立的 api_key/base_url/model/provider
- `AutoFigureAgent` 作为主入口，`GenerationResult` 作为返回值

**前端**: Next.js Web UI + Flask API Server

**关键优势**:
- ✅ 输出可编辑SVG/mxGraph XML（draw.io兼容）
- ✅ 多Provider支持
- ✅ 迭代优化直到质量达标
- ✅ PDF/Markdown方法提取

---

### 3. AutoFigure-Edit — 矢量化编辑Pipeline

**核心架构**: 五步骤线性Pipeline（同步Python）

| 步骤 | 功能 | 输出 |
|------|------|------|
| **步骤1** | LLM生成学术风格图片（支持风格迁移） | `figure.png` |
| **步骤2** | SAM3分割（多prompt检测+Box合并） | `samed.png` + `boxlib.json` |
| **步骤3** | 裁切图标 + RMBG2去背景 | `icons/*.png` + `*_nobg.png` |
| **步骤4** | LLM多模态生成SVG模板 + 语法验证修复 + LLM优化 | `template.svg` → `optimized_template.svg` |
| **步骤5** | 图标替换到SVG占位符（序号匹配/坐标匹配） | `final.svg` |

**SAM3后端**: 
- 本地GPU推理（`sam3` Python包）
- fal.ai API
- Roboflow API

**LLM调用**: 基于 OpenAI SDK，支持 OpenRouter / Bianxie

**前端**: FastAPI + 静态HTML + 嵌入式 SVG-Edit 编辑器

**关键优势**:
- ✅ 生成完全可编辑的矢量SVG
- ✅ 风格迁移（参考图像）
- ✅ 嵌入式SVG编辑器（所见即所得）
- ✅ 每步骤可单独停止（`stop_after`参数）

---

### 4. VoAPI — AI模型API聚合分发系统

**说明**: VoAPI 是闭源Go项目（仅提供Docker镜像），但其功能设计可作为PaperScholar用户/API管理的参考蓝图。

**核心功能**:

| 模块 | 功能 |
|------|------|
| **用户管理** | 注册/登录（用户名/邮箱）、多用户管理、5层用户等级、第三方登录(GitHub/Gitee) |
| **API令牌** | 多令牌管理、令牌权限控制 |
| **渠道管理** | 渠道分组、多上游配置、渠道重试、密钥错误禁用与自动恢复 |
| **负载均衡** | 多分组负载均衡、渠道密钥轮询、RPM/TPM限速 |
| **数据转发** | API核心转发、规则引擎(JS语法)、熔断超时机制 |
| **安全** | API密钥验证、IP/UA规则限制、安全过滤 |

**技术栈**: Go + MySQL + Redis + Docker Compose

**对PaperScholar的启发**:
- 渠道管理 → API Key管理（chat模型/image模型分离）
- 负载均衡 → 多Key轮询调用
- 用户管理 → 注册/登录/权限
- 密钥验证 → 用户自有API Key验证

---

## 二、PaperScholar 功能融合方案

基于以上分析，结合你的需求，以下是 PaperScholar 的功能梳理方案：

### 核心功能模块

#### 模块1: 学术图表生成（参照PaperBanana核心）
> 优先级: ⭐⭐⭐⭐⭐

**流程**: 输入Method Section + Figure Caption → 配置参数 → 多Agent Pipeline → 输出候选图表

**Agent Pipeline**（复用PaperBanana五Agent架构，但改造API层）:
1. **Retriever Agent** — 参考图检索（支持自动/手动/随机/无检索四种模式）
2. **Planner Agent** — 生成详细图表描述（支持diagram + plot两种任务）
3. **Stylist Agent** — 基于Style Guide美学润色
4. **Visualizer Agent** — 生成图像（diagram用Image模型 / plot用代码生成）
5. **Critic Agent** — 多轮迭代审查反馈

**改造重点**:
- 将 `generation_utils.py` 中仅支持Gemini的调用层替换为**统一多Provider LLM客户端**
- 添加**实时进度反馈机制**：每个Agent步骤完成时推送状态 + 中间图像给前端（SSE/WebSocket）
- 支持配置不同的pipeline模式

#### 模块2: 结构化数据图表（参照AutoFigure + PaperBanana plot模式）
> 优先级: ⭐⭐⭐⭐

**流程**: 输入结构化数据（表格/JSON） → LLM生成Python matplotlib代码 → 执行代码 → 迭代优化

**方案**（两种路径，可结合）:
- **路径A（PaperBanana方式）**: Planner生成描述 → Visualizer用LLM生成matplotlib代码 → 执行代码生成图表 → Critic评审迭代
- **路径B（AutoFigure方式）**: LLM直接生成SVG/mxGraph XML → Evaluate评分 → Improve迭代 → 输出可编辑矢量图

**建议**: 先实现路径A作为基础，后续扩展路径B提供矢量图输出选项

#### 模块3: 图表编辑与矢量化（参照AutoFigure-Edit）
> 优先级: ⭐⭐⭐⭐

**流程**: 上传已有图表 → SAM3分割 → 去背景 → SVG模板生成 → 图标替换 → 在线编辑

**实现要点**:
- 复用 autofigure-edit 的五步骤Pipeline（LLM生图 → SAM3分割 → RMBG去背 → SVG生成 → 图标替换）
- 集成嵌入式SVG编辑器（svg-edit）
- SAM3后端支持：本地GPU / fal.ai API / Roboflow API
- 支持风格迁移（上传参考图像）

#### 模块4: 精修与增强（参照PaperBanana Polish + AutoFigure Enhancement）
> 优先级: ⭐⭐⭐

**功能**:
- 上传候选图 → 描述修改需求 → Image模型精修
- 分辨率上采样（2K/4K）
- AI美化增强（code2prompt模式推荐）
- 矢量图精修 / 部分组件精修

---

### 平台功能模块

#### 模块5: 统一多Provider LLM客户端
> 优先级: ⭐⭐⭐⭐⭐（基础设施，其他模块依赖）

**设计**（参照AutoFigure的`call_unified_llm` + VoAPI的渠道管理思路）:

```
支持的调用格式:
├── OpenAI 兼容格式（OpenRouter / Bianxie / 自定义endpoint）
├── Google Gemini 原生格式（google.genai SDK）
├── Anthropic 格式
└── 可扩展Provider接口

配置结构（每种模型类型独立配置）:
├── Chat模型
│   ├── provider / base_url / api_key / model_name
│   └── 支持多组配置（用于负载均衡）
├── Image模型
│   ├── provider / base_url / api_key / model_name
│   └── 支持多组配置（用于负载均衡）
└── 默认配置（一键使用，也可自定义）
```

**负载均衡/轮询**:
- 用户配置多个API Key时（chat/image模型各自），请求自动轮询分配
- 支持策略：Round-Robin / Random / Weighted
- 错误自动切换下一个Key（参照VoAPI的密钥错误禁用与恢复机制）

#### 模块6: 用户管理系统
> 优先级: ⭐⭐⭐⭐

**功能**（参照VoAPI）:

| 功能 | 说明 |
|------|------|
| 注册/登录 | 用户名 + 邮箱 + 密码 |
| 角色权限 | 管理员 / 普通用户 |
| API Key管理 | 用户可使用系统API或填写自己的API Key |
| 系统API申请 | 用户申请 → 管理员审核 → 通过后授权使用 |
| 自有API验证 | 用户填写API Key后自动验证有效性（发送测试请求） |
| 用量统计 | 记录用户的API调用次数/Token消耗 |

#### 模块7: 实时交互体验
> 优先级: ⭐⭐⭐⭐（你特别强调的痛点）

**方案**:
- **SSE (Server-Sent Events)** 或 **WebSocket** 推送Agent运行状态
- 每个Agent步骤完成时推送：
  - 当前阶段名称（如 "Planner Agent 正在生成描述..."）
  - 中间产物（如 Planner输出的文本描述、Visualizer生成的阶段图片、Critic的反馈意见）
  - 进度百分比
- 前端实时展示Pipeline Evolution（参照PaperBanana的 `show_pipeline_evolution.py` 可视化思路）

---

## 三、技术架构建议

### 整体架构: 前后端分离

```
┌─────────────────────────────────────────────────┐
│                   前端 (React/Next.js)           │
│  ┌─────────┐ ┌──────────┐ ┌───────────────────┐ │
│  │ 图表生成 │ │ 图表编辑  │ │ 用户/API Key管理  │ │
│  │ (SSE实时)│ │ (SVG编辑) │ │ (Dashboard)      │ │
│  └─────────┘ └──────────┘ └───────────────────┘ │
└──────────────────────┬──────────────────────────┘
                       │ HTTP / SSE / WebSocket
┌──────────────────────┴──────────────────────────┐
│                后端 (Python FastAPI)              │
│  ┌──────────────────────────────────────────┐    │
│  │         API路由层 (REST + SSE)            │    │
│  ├──────────────────────────────────────────┤    │
│  │         业务逻辑层                        │    │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────┐  │    │
│  │  │图表生成  │ │图表编辑   │ │精修增强   │  │    │
│  │  │Pipeline │ │Pipeline  │ │Pipeline  │  │    │
│  │  └─────────┘ └──────────┘ └──────────┘  │    │
│  ├──────────────────────────────────────────┤    │
│  │     统一LLM客户端 (多Provider+负载均衡)     │    │
│  ├──────────────────────────────────────────┤    │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────┐  │    │
│  │  │用户管理  │ │API Key   │ │任务队列   │  │    │
│  │  │(Auth)   │ │管理/验证  │ │(Celery?) │  │    │
│  │  └─────────┘ └──────────┘ └──────────┘  │    │
│  └──────────────────────────────────────────┘    │
└──────────────────────┬──────────────────────────┘
                       │
       ┌───────────────┼───────────────┐
       │               │               │
  ┌────┴────┐    ┌─────┴─────┐   ┌────┴────┐
  │PostgreSQL│    │   Redis   │   │文件存储  │
  │(用户/配置)│    │(会话/缓存) │   │(图片/SVG)│
  └─────────┘    └───────────┘   └─────────┘
```

### 技术选型建议

| 层级 | 技术选择 | 理由 |
|------|---------|------|
| **前端框架** | React + Next.js | AutoFigure已有Next.js前端，可复用；生态成熟 |
| **UI组件** | shadcn/ui + TailwindCSS | 现代化、高质量UI |
| **后端框架** | Python FastAPI | 异步支持好（Agent Pipeline需要async）、SSE原生支持、与现有Python代码兼容 |
| **数据库** | PostgreSQL | 可靠、Linux部署友好（也可用MySQL） |
| **缓存** | Redis | 会话管理、API Key缓存、任务状态 |
| **任务队列** | Celery + Redis | 长时间运行的图表生成任务异步执行 |
| **认证** | JWT + bcrypt | 标准、轻量 |
| **部署** | Docker Compose | 你要求的Linux服务器便捷部署 |
| **实时通信** | SSE (Server-Sent Events) | 比WebSocket更简单，适合单向推送Pipeline状态 |

---

## 四、待确认问题

在进入正式项目文档创建之前，有几个关键问题需要你确认：

1. **关于PaperBanana的参考数据集**：PaperBanana依赖 `PaperBananaBench` 数据集进行检索。PaperScholar是否也需要内置参考数据集？还是仅支持用户自己上传参考图？

2. **关于SAM3依赖**：autofigure-edit的矢量化功能依赖SAM3模型（需要GPU或API调用）。PaperScholar是否需要本地SAM3支持，还是仅使用API模式（fal.ai/Roboflow）？

3. **优先级排序**：你希望先实现哪些功能模块？建议的MVP路径：
   - Phase 1: 统一LLM客户端 + 用户管理 + 图表生成Pipeline（核心）
   - Phase 2: 实时交互 + 结构化数据图表
   - Phase 3: 图表编辑/矢量化 + 精修增强

4. **前端偏好**：是否希望从头构建前端，还是基于AutoFigure的Next.js前端改造？

5. **数据库偏好**：PostgreSQL 还是 MySQL？（VoAPI用MySQL，但PostgreSQL在新项目中更常见）

6. **许可证问题**：PaperBanana声明核心方法已被Google申请专利，不影响开源研究但限制商业应用。PaperScholar是否有商业化计划？这会影响与PaperBanana代码的复用策略。
