# PaperScholar — 技术架构文档

> 版本: v1.0 | 日期: 2026-02-27

---

## 1. 系统架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                     前端 (Next.js 14+)                       │
│   React + TailwindCSS + shadcn/ui + Lucide Icons            │
│   ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌──────────────┐ │
│   │ 图表生成  │ │ 图表编辑   │ │ API配置   │ │ 管理后台     │ │
│   │ (SSE实时) │ │ (矢量化)   │ │ (多模型)  │ │ (审核/统计)  │ │
│   └──────────┘ └───────────┘ └──────────┘ └──────────────┘ │
└───────────────────────┬─────────────────────────────────────┘
                        │ REST API + SSE
┌───────────────────────┴─────────────────────────────────────┐
│                    后端 (Python FastAPI)                      │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                   API 路由层                             │  │
│  │  /api/auth   /api/user   /api/admin   /api/generate    │  │
│  │  /api/edit   /api/refine /api/config  /api/sse         │  │
│  └────────────────────────┬───────────────────────────────┘  │
│                           │                                   │
│  ┌────────────────────────┴───────────────────────────────┐  │
│  │               业务逻辑层 (Services)                      │  │
│  │  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────┐ │  │
│  │  │Generation │ │ Edit     │ │ Refine    │ │ User     │ │  │
│  │  │Service   │ │ Service  │ │ Service   │ │ Service  │ │  │
│  │  └────┬─────┘ └────┬─────┘ └─────┬─────┘ └──────────┘ │  │
│  │       │             │             │                      │  │
│  │  ┌────┴─────────────┴─────────────┴──────────────────┐  │  │
│  │  │          Agent Pipeline Engine                     │  │  │
│  │  │  Retriever → Planner → Stylist → Visualizer →     │  │  │
│  │  │  Critic (loop) → Polish                            │  │  │
│  │  └────────────────────┬──────────────────────────────┘  │  │
│  │                       │                                   │  │
│  │  ┌────────────────────┴──────────────────────────────┐  │  │
│  │  │       统一LLM客户端 (Unified LLM Client)           │  │  │
│  │  │  ┌──────────┐ ┌─────────┐ ┌──────────┐           │  │  │
│  │  │  │ OpenAI   │ │ Gemini  │ │Anthropic │  ...      │  │  │
│  │  │  │ Compat   │ │ Native  │ │ Native   │           │  │  │
│  │  │  └──────────┘ └─────────┘ └──────────┘           │  │  │
│  │  │       ↕ 负载均衡 / 轮询 / 故障切换                   │  │  │
│  │  └───────────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │  asyncio    │  │  Redis       │  │  文件存储             │ │
│  │  后台任务    │  │  (规划中)     │  │  (图片/SVG/数据集)    │ │
│  └─────────────┘  └──────────────┘  └──────────────────────┘ │
└───────────────────────┬─────────────────────────────────────┘
                        │
                  ┌─────┴─────┐
                  │PostgreSQL │
                  └───────────┘
```

---

## 2. 技术栈

### 前端
| 技术 | 版本 | 用途 |
|------|------|------|
| **Next.js** | 14+ (App Router) | React全栈框架 |
| **React** | 18+ | UI框架 |
| **TailwindCSS** | 3.x | 原子CSS |
| **shadcn/ui** | latest | 组件库 |
| **Lucide React** | latest | 图标 |
| **zustand** | 4.x | 轻量状态管理 |
| **@tanstack/react-query** | 5.x | 数据请求/缓存 (已安装，逐步集成中) |

### 后端
| 技术 | 版本 | 用途 |
|------|------|------|
| **Python** | 3.12+ | 运行时 |
| **FastAPI** | 0.110+ | Web框架 |
| **uvicorn** | 0.27+ | ASGI服务器 |
| **SQLAlchemy** | 2.0+ | ORM |
| **Alembic** | 1.13+ | 数据库迁移 |
| **asyncio** | (内置) | 后台任务执行 (asyncio.create_task) |
| **Pydantic** | 2.x | 数据验证 |
| **python-jose** | 3.x | JWT |
| **passlib[bcrypt]** | 1.7+ | 密码哈希 |
| **httpx** | 0.27+ | 异步HTTP客户端 |
| **openai** | 1.x | OpenAI兼容API调用 |
| **google-genai** | 1.x | Gemini原生API调用 |
| **anthropic** | 0.x | Anthropic API调用 |
| **sse-starlette** | 2.x | SSE支持 |
| **Pillow** | 10.x | 图像处理 |
| **cairosvg** | 2.x | SVG转PNG |

### 基础设施
| 技术 | 用途 |
|------|------|
| **PostgreSQL** 16+ | 主数据库 |
| **Redis** 7+ | 缓存/会话 (规划中，当前未启用) |
| **Docker** + **Docker Compose** | 容器化部署 |
| **Nginx** | 反向代理（可选） |

---

## 3. 项目目录结构

```
paperscholar/
├── frontend/                       # Next.js 前端
│   ├── src/app/                    # App Router 页面
│   │   ├── login/page.tsx          # 登录
│   │   ├── register/page.tsx       # 注册
│   │   ├── dashboard/              # 主功能页面
│   │   │   ├── generate/page.tsx   # 图表生成
│   │   │   ├── edit/page.tsx       # 图表编辑(矢量化+SVG生成)
│   │   │   ├── refine/page.tsx     # 精修增强(增强+风格迁移)
│   │   │   ├── history/page.tsx    # 历史记录
│   │   │   ├── settings/page.tsx   # API配置
│   │   │   ├── admin/users/        # 用户管理
│   │   │   ├── admin/review/       # API申请审核
│   │   │   ├── admin/config/       # 系统配置+统计+公告
│   │   │   ├── layout.tsx          # Dashboard布局(侧边栏)
│   │   │   └── page.tsx            # Dashboard首页
│   │   ├── layout.tsx              # 根布局
│   │   ├── globals.css             # 全局样式(工业技术风)
│   │   └── page.tsx                # 首页(自动跳转)
│   ├── src/components/             # 共享组件
│   │   ├── ui/                     # UI基础组件(skeleton/toaster)
│   │   └── layout/                 # 布局组件(Sidebar)
│   ├── src/lib/                    # API客户端、工具函数
│   ├── src/stores/                 # zustand stores
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.ts
│   └── tsconfig.json
│
├── backend/                        # Python FastAPI 后端
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI入口
│   │   ├── config.py               # 配置管理(pydantic-settings)
│   │   ├── api/                    # API路由
│   │   │   ├── auth.py             # 认证(注册/登录/验证码)
│   │   │   ├── api_keys.py         # API Key管理 + 系统API申请
│   │   │   ├── generate.py         # 图表生成 + SSE流 + 历史
│   │   │   ├── edit.py             # 图表编辑(矢量化+SVG生成)
│   │   │   ├── refine.py           # 精修增强(增强+风格迁移)
│   │   │   ├── admin.py            # 管理员(用户/审核/配置/公告/统计)
│   │   │   ├── files.py            # 参考图上传/管理
│   │   │   └── deps.py             # 依赖注入(认证/权限)
│   │   ├── services/               # 业务逻辑
│   │   │   ├── generation_service.py  # Pipeline执行编排
│   │   │   ├── edit_service.py     # 编辑Pipeline(SAM3+SVG)
│   │   │   ├── svg_service.py      # SVG迭代生成
│   │   │   └── cleanup_service.py  # 过期文件清理
│   │   ├── agents/                 # Agent Pipeline
│   │   │   ├── base_agent.py       # Agent抽象基类
│   │   │   ├── pipeline.py         # Pipeline编排 + Planner/Stylist/Visualizer/Critic Agent
│   │   │   ├── retriever_agent.py  # 参考图检索Agent
│   │   │   └── polish_agent.py     # 图片精修Agent
│   │   ├── llm/                    # 统一LLM客户端
│   │   │   ├── base_client.py      # 抽象基类
│   │   │   ├── openai_client.py    # OpenAI兼容
│   │   │   ├── gemini_client.py    # Gemini原生
│   │   │   ├── anthropic_client.py # Anthropic原生
│   │   │   ├── client_factory.py   # 工厂模式
│   │   │   └── load_balancer.py    # Round-Robin负载均衡+故障切换
│   │   ├── models/                 # SQLAlchemy数据库模型
│   │   │   ├── user.py             # 用户表
│   │   │   ├── api_key.py          # API Key配置 + 系统API申请
│   │   │   ├── generation.py       # 生成任务/结果/事件/参考图
│   │   │   └── system.py           # 系统配置/公告/API调用日志
│   │   ├── schemas/                # Pydantic schema
│   │   │   ├── auth.py
│   │   │   ├── generation.py
│   │   │   └── api_key.py
│   │   ├── core/                   # 核心模块
│   │   │   ├── security.py         # JWT / 密码哈希 / API Key加解密
│   │   │   ├── database.py         # DB连接(async)
│   │   │   └── middleware.py       # 全局异常处理中间件
│   │   └── prompts/                # Agent提示词
│   │       ├── diagram_prompts.py
│   │       └── plot_prompts.py
│   ├── alembic/                    # 数据库迁移
│   ├── alembic.ini
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── docker-compose.yml              # Docker编排(db/redis/backend/frontend)
├── docs/                           # 项目文档
│   ├── PRD.md
│   ├── architecture.md
│   ├── database.md
│   └── api-design.md
└── README.md
```

---

## 4. 核心模块设计

### 4.1 统一LLM客户端

```python
# 抽象基类
class BaseLLMClient(ABC):
    async def chat(self, messages, **kwargs) -> str: ...
    async def generate_image(self, prompt, **kwargs) -> bytes: ...
    async def multimodal(self, contents, **kwargs) -> str: ...

# Provider实现
class OpenAICompatClient(BaseLLMClient):    # OpenRouter / 自定义
class GeminiNativeClient(BaseLLMClient):    # Google Gemini SDK
class AnthropicClient(BaseLLMClient):       # Anthropic SDK

# 工厂
class LLMClientFactory:
    @staticmethod
    def create(provider, api_key, base_url, model) -> BaseLLMClient: ...

# 负载均衡器
class LoadBalancer:
    def __init__(self, configs: List[LLMConfig]):
        self.clients = [LLMClientFactory.create(**c) for c in configs]
        self.index = 0

    async def call(self, method, **kwargs):
        # Round-Robin + 错误自动切换
        for attempt in range(len(self.clients)):
            client = self.clients[self.index % len(self.clients)]
            self.index += 1
            try:
                return await getattr(client, method)(**kwargs)
            except Exception as e:
                log.warning(f"Client {self.index} failed: {e}, trying next")
        raise AllClientsFailedError()
```

### 4.2 Agent Pipeline Engine

```python
class PipelineEngine:
    """管理Agent执行流水线，支持SSE事件推送"""

    async def run(self, data, mode, on_event: Callable):
        """
        on_event: SSE回调函数，推送阶段状态和中间产物
        """
        if mode == "full":
            await on_event("stage", {"name": "retriever", "status": "running"})
            data = await self.retriever.process(data)
            await on_event("stage", {"name": "retriever", "status": "done"})

            await on_event("stage", {"name": "planner", "status": "running"})
            data = await self.planner.process(data)
            await on_event("intermediate", {"type": "text", "content": data["description"]})
            await on_event("stage", {"name": "planner", "status": "done"})

            # ... Stylist, Visualizer, Critic循环 ...

            await on_event("stage", {"name": "visualizer", "status": "running"})
            data = await self.visualizer.process(data)
            await on_event("intermediate", {"type": "image", "data": data["image_base64"]})
            # ...
```

### 4.3 SSE实时推送

```python
@router.get("/api/generate/{task_id}/stream")
async def stream_generation(task_id: str):
    async def event_generator():
        task = get_task(task_id)
        async for event in task.events():
            yield {
                "event": event.type,      # stage / intermediate / progress / done / error
                "data": json.dumps(event.data)
            }
    return EventSourceResponse(event_generator())
```

### 4.4 API Key管理逻辑

```
用户请求生成图表时的API Key选择优先级：
1. 用户自有API Key（已验证有效）→ 直接使用，不消耗系统配额
2. 用户已获批的系统API → 使用系统Key，记录用量
3. 都没有 → 返回错误提示
```

---

## 5. 部署架构

### Docker Compose

```yaml
services:
  frontend:
    build: ./docker/Dockerfile.frontend
    ports: ["3000:3000"]

  backend:
    build: ./docker/Dockerfile.backend
    ports: ["8000:8000"]
    depends_on: [db, redis]
    volumes:
      - ./backend/data:/app/data      # 内置数据集
      - uploads:/app/uploads           # 用户上传文件

  db:
    image: postgres:16
    volumes: [pgdata:/var/lib/postgresql/data]
    environment:
      POSTGRES_DB: paperscholar
      POSTGRES_USER: paperscholar
      POSTGRES_PASSWORD: ${DB_PASSWORD}

  redis:
    image: redis:7-alpine

volumes:
  pgdata:
  uploads:
```

---

## 6. 安全设计

| 层面 | 措施 |
|------|------|
| **认证** | JWT Token (HS256)，7天过期 |
| **密码** | bcrypt哈希，salt rounds=12 |
| **API Key存储** | AES-256加密存储到数据库，展示时脱敏 |
| **CORS** | 仅允许前端域名 |
| **速率限制** | 基于用户+IP的请求频率限制 |
| **输入校验** | Pydantic严格校验所有输入 |
| **文件上传** | 限制类型(PNG/JPG/PDF/MD)和大小(最大20MB) |
