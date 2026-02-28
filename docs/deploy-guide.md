# PaperScholar Linux 服务器部署指南

> 创建时间：2026-02-28
> 适用环境：CentOS / Ubuntu / Debian 等主流 Linux 发行版

---

## 一、当前部署架构分析

### 现有组件

| 组件 | 技术栈 | 容器化 | 端口 |
|---|---|---|---|
| 前端 | Next.js 14 + React 18 + TailwindCSS | Dockerfile ✅ | 3000 |
| 后端 | FastAPI + Uvicorn + SQLAlchemy | Dockerfile ✅ | 8000 |
| 数据库 | PostgreSQL 16 | docker-compose ✅ | 5432 |
| 缓存 | Redis 7 | docker-compose ✅ | 6379 |
| 反代 | Nginx（配置文件已有，但未纳入 compose） | ❌ | 80 |

### 现有部署脚本

- `server_setup.sh` — 一体化部署脚本（镜像源 + .env + 防火墙 + docker compose）
- `deploy_setup.sh` — 简化版（.env + docker compose）
- `setup_mirror.sh` — 仅配置容器镜像源
- `nginx.conf` — Nginx 反代配置（未集成到 compose）
- `registries.conf` — Podman 镜像源配置

---

## 二、现有问题与改进建议

### D1: Nginx 未纳入 docker-compose

- **现状**：`nginx.conf` 存在但 `docker-compose.yml` 中没有 nginx 服务，前端和后端端口直接暴露
- **问题**：生产环境需要通过 Nginx 统一入口，处理 SSL、SSE 长连接、静态文件缓存
- **建议**：在 docker-compose.yml 中添加 nginx 服务，仅暴露 80/443 端口

### D2: 前端 API_URL 在构建时写死

- **现状**：`frontend/Dockerfile` 中 `NEXT_PUBLIC_API_URL` 作为 build ARG 写入，构建后不可变
- **问题**：换服务器 IP 或域名需要重新 build 前端镜像
- **建议**：利用 `next.config.js` 已有的 rewrites 规则，前端请求走 `/api/*` 由 Nginx 反代到后端，`NEXT_PUBLIC_API_URL` 设为空或相对路径

### D3: docker-compose 是开发模式配置

- **现状**：
  - backend 使用 `--reload` 热重载
  - backend 挂载了源码目录 `./backend/app:/app/app`
  - 数据库密码硬编码为 `paperscholar`
  - 所有端口（5432、6379）对外暴露
- **建议**：创建 `docker-compose.prod.yml` 生产覆盖文件

### D4: 缺少 SSE 长连接的 Nginx 配置

- **现状**：`nginx.conf` 的 `/api/` 路由没有 SSE 相关配置
- **问题**：生成任务通过 SSE 推送进度，Nginx 默认会缓冲响应导致 SSE 失效
- **建议**：添加 `proxy_buffering off`、`X-Accel-Buffering: no` 等 SSE 必要头

### D5: 缺少数据库迁移自动执行

- **现状**：`init_db()` 使用 `Base.metadata.create_all` 直接建表，alembic 迁移需要手动执行
- **问题**：更新部署时数据库 schema 变更不会自动应用
- **建议**：容器启动时自动执行 `alembic upgrade head`

### D6: 缺少日志持久化

- **现状**：容器日志仅存在于 Docker 内部，重启后丢失
- **建议**：挂载日志目录或配置 Docker logging driver

### D7: 缺少健康检查和自动重启

- **现状**：db 和 redis 有 healthcheck，但 backend 和 frontend 没有
- **建议**：为 backend 和 frontend 添加 healthcheck

### D8: 部署脚本 IP 硬编码

- **现状**：`server_setup.sh` 和 `deploy_setup.sh` 中 IP `39.106.47.92` 硬编码
- **建议**：改为参数化或自动检测

### D9: 缺少 HTTPS 支持

- **现状**：全部走 HTTP
- **建议**：集成 Let's Encrypt 自动证书（通过 certbot 或 acme.sh）

### D10: 前端 Docker 构建未利用多阶段优化

- **现状**：单阶段构建，最终镜像包含所有 devDependencies 和构建工具
- **建议**：多阶段构建，最终镜像仅包含 production 依赖和 `.next/standalone`

### D11: 后端缺少 matplotlib 等 Plot 生成依赖

- **现状**：`requirements.txt` 没有 `matplotlib`、`numpy`、`seaborn`，但 `_execute_plot_code` 在子进程中调用它们
- **问题**：Plot 模式在容器内会直接失败
- **建议**：在 requirements.txt 中添加 `matplotlib`、`numpy`

### D12: uploads 卷在生产环境需要备份策略

- **现状**：uploads 使用 Docker named volume，没有备份机制
- **建议**：改为 bind mount 到宿主机目录，方便备份

---

## 三、改进后的目标部署架构

```
                    ┌─────────────┐
                    │   Nginx     │ :80 / :443
                    │  (SSL终端)   │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Frontend │ │ Backend  │ │ /uploads │
        │ :3000    │ │ :8000    │ │ (静态)    │
        └──────────┘ └────┬─────┘ └──────────┘
                          │
                ┌─────────┼─────────┐
                │                   │
                ▼                   ▼
          ┌──────────┐       ┌──────────┐
          │ Postgres │       │  Redis   │
          │ :5432    │       │  :6379   │
          └──────────┘       └──────────┘
          (仅内部访问)         (仅内部访问)
```

---

## 四、具体改进文件

### 4.1 生产环境 docker-compose.prod.yml

创建 `docker-compose.prod.yml` 作为生产覆盖：

```yaml
# docker-compose.prod.yml
# 用法: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

services:
  db:
    ports: !override []  # 不对外暴露
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD:-paperscholar}
    volumes:
      - ./data/postgres:/var/lib/postgresql/data  # bind mount 方便备份

  redis:
    ports: !override []  # 不对外暴露

  backend:
    command: >
      sh -c "alembic upgrade head &&
             uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4"
    ports: !override []  # 仅通过 nginx 访问
    expose:
      - "8000"
    volumes:
      - ./data/uploads:/app/uploads
      - ./data/logs/backend:/app/logs
    environment:
      DATABASE_URL: postgresql+asyncpg://paperscholar:${DB_PASSWORD:-paperscholar}@db:5432/paperscholar
      REDIS_URL: redis://redis:6379/0
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/api/health')"]
      interval: 30s
      timeout: 5s
      retries: 3

  frontend:
    ports: !override []
    expose:
      - "3000"
    environment:
      NEXT_PUBLIC_API_URL: ""  # 走 nginx 反代，不需要绝对 URL
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:3000"]
      interval: 30s
      timeout: 5s
      retries: 3

  nginx:
    image: nginx:alpine
    container_name: paperscholar-nginx
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./data/certbot/conf:/etc/letsencrypt:ro
      - ./data/certbot/www:/var/www/certbot:ro
    depends_on:
      - frontend
      - backend
```

### 4.2 改进后的 nginx.conf

```nginx
# 上游服务
upstream frontend {
    server frontend:3000;
}

upstream backend {
    server backend:8000;
}

server {
    listen 80;
    server_name _;

    # Let's Encrypt 验证
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # API 路由（含 SSE 支持）
    location /api/ {
        proxy_pass http://backend/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 关键配置
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
        proxy_set_header X-Accel-Buffering no;

        # 长连接超时（生成任务可能需要几分钟）
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;

        # 上传大小
        client_max_body_size 50M;
    }

    # 上传文件静态服务
    location /uploads/ {
        proxy_pass http://backend/uploads/;
        proxy_set_header Host $host;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    # Swagger 文档
    location /docs {
        proxy_pass http://backend/docs;
        proxy_set_header Host $host;
    }

    location /openapi.json {
        proxy_pass http://backend/openapi.json;
        proxy_set_header Host $host;
    }

    # 前端（兜底）
    location / {
        proxy_pass http://frontend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### 4.3 改进后的一键部署脚本

```bash
#!/bin/bash
# deploy.sh — PaperScholar 一键部署脚本
set -e

# ── 参数 ──
PROJECT_DIR="${PROJECT_DIR:-/opt/paperscholar}"
SERVER_IP="${SERVER_IP:-$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')}"
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -hex 16)}"

echo "=== PaperScholar 部署 ==="
echo "项目目录: $PROJECT_DIR"
echo "服务器 IP: $SERVER_IP"

# ── 1. 系统依赖 ──
echo ""
echo "--- 1/6 检查 Docker ---"
if ! command -v docker &>/dev/null; then
    echo "安装 Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
fi
docker --version

# ── 2. 创建数据目录 ──
echo ""
echo "--- 2/6 创建数据目录 ---"
mkdir -p "$PROJECT_DIR"/{data/postgres,data/uploads,data/logs/backend,data/certbot/conf,data/certbot/www}

# ── 3. 生成 .env ──
echo ""
echo "--- 3/6 生成配置文件 ---"
SECRET=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 32)
API_ENC=$(openssl rand -hex 16)

cat > "$PROJECT_DIR/backend/.env" << EOF
APP_NAME=PaperScholar
APP_ENV=production
DEBUG=false
SECRET_KEY=$SECRET
API_V1_PREFIX=/api/v1
DATABASE_URL=postgresql+asyncpg://paperscholar:${DB_PASSWORD}@db:5432/paperscholar
REDIS_URL=redis://redis:6379/0
JWT_SECRET_KEY=$JWT_SECRET
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=10080
API_KEY_ENCRYPTION_KEY=$API_ENC
CORS_ORIGINS=["http://${SERVER_IP}","https://${SERVER_IP}"]
UPLOAD_DIR=./uploads
MAX_UPLOAD_SIZE_MB=20
EOF

cat > "$PROJECT_DIR/frontend/.env.local" << EOF
NEXT_PUBLIC_API_URL=
EOF

echo "Backend .env 已生成"
echo "Frontend .env.local 已生成（API 走 Nginx 反代）"

# ── 4. 防火墙 ──
echo ""
echo "--- 4/6 配置防火墙 ---"
if command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-service=http 2>/dev/null || true
    firewall-cmd --permanent --add-service=https 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
    echo "firewalld 已配置"
elif command -v ufw &>/dev/null; then
    ufw allow 80/tcp 2>/dev/null || true
    ufw allow 443/tcp 2>/dev/null || true
    echo "ufw 已配置"
else
    echo "未检测到防火墙工具，请手动开放 80/443 端口"
fi

# ── 5. Docker 镜像加速（中国大陆服务器可选） ──
echo ""
echo "--- 5/6 配置 Docker 镜像加速 ---"
if [ "${USE_MIRROR:-false}" = "true" ]; then
    mkdir -p /etc/docker
    cat > /etc/docker/daemon.json << 'MIRROREOF'
{
    "registry-mirrors": [
        "https://docker.1ms.run",
        "https://docker.xuanyuan.me",
        "https://hub.rat.dev"
    ]
}
MIRROREOF
    systemctl restart docker
    echo "Docker 镜像加速已配置"
else
    echo "跳过（设置 USE_MIRROR=true 启用）"
fi

# ── 6. 启动服务 ──
echo ""
echo "--- 6/6 构建并启动服务 ---"
cd "$PROJECT_DIR"
DB_PASSWORD=$DB_PASSWORD docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

echo ""
echo "=== 部署完成 ==="
echo "访问地址: http://${SERVER_IP}"
echo "API 文档: http://${SERVER_IP}/docs"
echo ""
echo "数据库密码已保存，请记录: $DB_PASSWORD"
echo "如需查看日志: docker compose logs -f"
```

### 4.4 前端 Dockerfile 多阶段优化

```dockerfile
# frontend/Dockerfile.prod
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --legacy-peer-deps

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_API_URL=""
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT=3000
CMD ["node", "server.js"]
```

> 注意：需要在 `next.config.js` 中添加 `output: 'standalone'` 才能使用 standalone 模式。

### 4.5 后端 requirements.txt 补充

需要添加的依赖（Plot 模式必需）：

```
# Plot generation (used by _execute_plot_code in subprocess)
matplotlib>=3.8.0
numpy>=1.26.0
```

---

## 五、部署操作步骤

### 首次部署

```bash
# 1. 克隆代码到服务器
git clone <repo-url> /opt/paperscholar
cd /opt/paperscholar

# 2. 一键部署（中国大陆服务器加 USE_MIRROR=true）
USE_MIRROR=true bash deploy.sh

# 3. 检查服务状态
docker compose ps
docker compose logs -f backend
```

### 更新部署

```bash
cd /opt/paperscholar

# 拉取最新代码
git pull

# 重新构建并启动（仅重建有变更的服务）
DB_PASSWORD=<之前的密码> docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 如果有数据库迁移
docker compose exec backend alembic upgrade head
```

### 查看日志

```bash
# 所有服务
docker compose logs -f

# 仅后端
docker compose logs -f backend

# 仅查看最近 100 行
docker compose logs --tail=100 backend
```

### 数据备份

```bash
# 数据库备份
docker compose exec db pg_dump -U paperscholar paperscholar > backup_$(date +%Y%m%d).sql

# 上传文件备份
tar czf uploads_$(date +%Y%m%d).tar.gz data/uploads/
```

### 数据恢复

```bash
# 数据库恢复
cat backup_20260228.sql | docker compose exec -T db psql -U paperscholar paperscholar

# 上传文件恢复
tar xzf uploads_20260228.tar.gz
```

---

## 六、可选：HTTPS 配置

```bash
# 安装 certbot
apt install -y certbot  # Ubuntu/Debian
# 或
yum install -y certbot  # CentOS

# 获取证书（需要先确保 80 端口可访问且域名已解析）
certbot certonly --webroot -w /opt/paperscholar/data/certbot/www -d your-domain.com

# 在 nginx.conf 中添加 SSL server block：
# server {
#     listen 443 ssl;
#     server_name your-domain.com;
#     ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
#     ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
#     ... (其余配置同 80 端口)
# }

# 重启 nginx
docker compose restart nginx

# 设置自动续期
echo "0 3 * * * certbot renew --quiet && docker compose -f /opt/paperscholar/docker-compose.yml restart nginx" | crontab -
```

---

## 七、改进任务清单

| 编号 | 任务 | 优先级 | 涉及文件 | 说明 |
|---|---|---|---|---|
| D1 | Nginx 纳入 docker-compose | P0 | `docker-compose.prod.yml`, `nginx.conf` | 统一入口，SSE 支持 |
| D2 | 前端 API_URL 改为相对路径 | P0 | `frontend/.env.local`, `next.config.js` | 避免换 IP 重新 build |
| D3 | 创建生产 compose 覆盖文件 | P0 | 新建 `docker-compose.prod.yml` | 去掉 --reload、源码挂载 |
| D4 | Nginx SSE 配置 | P0 | `nginx.conf` | `proxy_buffering off` 等 |
| D5 | 容器启动自动迁移 | P1 | `docker-compose.prod.yml` backend command | `alembic upgrade head` |
| D6 | 日志持久化 | P1 | `docker-compose.prod.yml` volumes | 挂载日志目录 |
| D7 | backend/frontend healthcheck | P1 | `docker-compose.prod.yml` | 自动重启不健康容器 |
| D8 | 部署脚本参数化 | P0 | 新建 `deploy.sh` 替代旧脚本 | 自动检测 IP，参数化密码 |
| D9 | HTTPS 支持 | P2 | `nginx.conf`, `deploy.sh` | Let's Encrypt 集成 |
| D10 | 前端多阶段构建 | P1 | `frontend/Dockerfile` | 镜像体积优化 |
| D11 | 补充 matplotlib/numpy 依赖 | P0 | `backend/requirements.txt` | Plot 模式必需 |
| D12 | uploads 改为 bind mount | P1 | `docker-compose.prod.yml` | 方便备份 |
