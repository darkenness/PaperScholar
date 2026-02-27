# PaperScholar — 数据库设计文档

> 版本: v1.0 | 日期: 2026-02-27 | 数据库: PostgreSQL 16+

---

## 1. ER 关系图（文字版）

```
users (1) ──── (N) api_key_configs
users (1) ──── (N) api_applications
users (1) ──── (N) generation_tasks
users (1) ──── (N) generation_results
users (1) ──── (N) uploaded_references
generation_tasks (1) ──── (N) generation_results
generation_tasks (1) ──── (N) pipeline_events
```

---

## 2. 表结构详细设计

### 2.1 users — 用户表

```sql
CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(50) UNIQUE NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(20) NOT NULL DEFAULT 'user',  -- 'user' | 'admin'
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- 系统API使用状态
    system_api_approved  BOOLEAN NOT NULL DEFAULT FALSE,  -- 是否已批准使用系统API
    
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
```

### 2.2 api_key_configs — 用户API Key配置表

```sql
CREATE TABLE api_key_configs (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- 模型类型: 'chat' 或 'image'
    model_type      VARCHAR(20) NOT NULL,  -- 'chat' | 'image'
    
    -- Provider配置
    provider        VARCHAR(50) NOT NULL,  -- 'openai_compat' | 'gemini' | 'anthropic'
    base_url        VARCHAR(500),
    api_key_encrypted VARCHAR(1000) NOT NULL,  -- AES-256加密存储
    model_name      VARCHAR(200),
    
    -- 状态
    is_verified     BOOLEAN NOT NULL DEFAULT FALSE,  -- 是否已验证有效
    is_enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    last_verified_at TIMESTAMP WITH TIME ZONE,
    last_error      TEXT,                             -- 最近一次错误信息
    
    -- 负载均衡权重（同一model_type下多个Key时）
    priority        INTEGER NOT NULL DEFAULT 0,       -- 越大优先级越高
    
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_api_key_configs_user ON api_key_configs(user_id);
CREATE INDEX idx_api_key_configs_user_type ON api_key_configs(user_id, model_type);
```

### 2.3 api_applications — 系统API申请表

```sql
CREATE TABLE api_applications (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    reason          TEXT,                           -- 申请理由
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',  -- 'pending' | 'approved' | 'rejected'
    
    reviewed_by     INTEGER REFERENCES users(id),   -- 审核人
    reviewed_at     TIMESTAMP WITH TIME ZONE,
    review_comment  TEXT,                            -- 审核备注
    
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_api_applications_user ON api_applications(user_id);
CREATE INDEX idx_api_applications_status ON api_applications(status);
```

### 2.4 generation_tasks — 生成任务表

```sql
CREATE TABLE generation_tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- 任务类型
    task_type       VARCHAR(30) NOT NULL,  -- 'diagram' | 'plot' | 'edit' | 'refine'
    
    -- 输入参数
    content         TEXT,                   -- Method Section / 数据内容
    visual_intent   TEXT,                   -- Figure Caption / 描述
    pipeline_mode   VARCHAR(30),            -- 'vanilla' | 'dev_planner' | 'dev_full' 等
    retrieval_setting VARCHAR(20),          -- 'auto' | 'manual' | 'random' | 'none'
    num_candidates  INTEGER DEFAULT 1,
    aspect_ratio    VARCHAR(10),            -- '1:1' | '16:9' 等
    max_critic_rounds INTEGER DEFAULT 3,
    
    -- 使用的模型配置快照
    chat_provider   VARCHAR(50),
    chat_model      VARCHAR(200),
    image_provider  VARCHAR(50),
    image_model     VARCHAR(200),
    
    -- 任务状态
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',  -- 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
    progress        REAL DEFAULT 0,         -- 0.0 ~ 1.0
    current_stage   VARCHAR(50),            -- 当前执行阶段
    error_message   TEXT,
    
    -- 时间
    started_at      TIMESTAMP WITH TIME ZONE,
    completed_at    TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_gen_tasks_user ON generation_tasks(user_id);
CREATE INDEX idx_gen_tasks_status ON generation_tasks(status);
CREATE INDEX idx_gen_tasks_created ON generation_tasks(created_at DESC);
```

### 2.5 generation_results — 生成结果表

```sql
CREATE TABLE generation_results (
    id              SERIAL PRIMARY KEY,
    task_id         UUID NOT NULL REFERENCES generation_tasks(id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- 候选序号
    candidate_index INTEGER NOT NULL DEFAULT 0,
    
    -- 结果文件
    image_path      VARCHAR(500),           -- 生成的图片路径
    svg_path        VARCHAR(500),           -- SVG文件路径（如有）
    thumbnail_path  VARCHAR(500),           -- 缩略图路径
    
    -- 质量评分
    quality_score   REAL,                   -- 0-10 评分
    eval_details    JSONB,                  -- 评估细节（各维度评分）
    
    -- Pipeline中间产物摘要
    planner_desc    TEXT,                   -- Planner输出的描述
    stylist_desc    TEXT,                   -- Stylist润色后的描述
    critic_feedback JSONB,                  -- Critic反馈历史
    
    -- 元数据
    metadata        JSONB,                  -- 其他元数据
    
    is_favorited    BOOLEAN DEFAULT FALSE,  -- 是否被用户收藏
    
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_gen_results_task ON generation_results(task_id);
CREATE INDEX idx_gen_results_user ON generation_results(user_id);
CREATE INDEX idx_gen_results_favorited ON generation_results(user_id, is_favorited) WHERE is_favorited = TRUE;
```

### 2.6 pipeline_events — Pipeline事件流表（SSE回放）

```sql
CREATE TABLE pipeline_events (
    id              SERIAL PRIMARY KEY,
    task_id         UUID NOT NULL REFERENCES generation_tasks(id) ON DELETE CASCADE,
    
    event_type      VARCHAR(30) NOT NULL,   -- 'stage' | 'intermediate' | 'progress' | 'error' | 'done'
    event_data      JSONB NOT NULL,
    
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_pipeline_events_task ON pipeline_events(task_id);
```

### 2.7 uploaded_references — 用户上传参考图表

```sql
CREATE TABLE uploaded_references (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    file_path       VARCHAR(500) NOT NULL,
    file_name       VARCHAR(255),
    file_size       INTEGER,                -- 字节数
    mime_type       VARCHAR(100),
    
    -- 关联的任务（用于清理）
    task_id         UUID REFERENCES generation_tasks(id) ON DELETE SET NULL,
    
    -- 自动清理标记
    expires_at      TIMESTAMP WITH TIME ZONE,  -- 过期时间，到期自动删除
    is_deleted      BOOLEAN DEFAULT FALSE,
    
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_uploaded_refs_user ON uploaded_references(user_id);
CREATE INDEX idx_uploaded_refs_expires ON uploaded_references(expires_at) WHERE is_deleted = FALSE;
```

### 2.8 system_configs — 系统配置表

```sql
CREATE TABLE system_configs (
    id              SERIAL PRIMARY KEY,
    config_key      VARCHAR(100) UNIQUE NOT NULL,
    config_value    JSONB NOT NULL,
    description     TEXT,
    
    updated_by      INTEGER REFERENCES users(id),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 预置配置
INSERT INTO system_configs (config_key, config_value, description) VALUES
('default_chat_model', '{"provider":"openai_compat","model":"gemini-2.5-pro"}', '默认Chat模型'),
('default_image_model', '{"provider":"openai_compat","model":"gemini-2.5-pro-image"}', '默认Image模型'),
('sam3_mode', '"api"', 'SAM3模式: local 或 api'),
('max_candidates', '20', '最大候选数'),
('max_critic_rounds', '5', '最大Critic轮数'),
('upload_ref_ttl_hours', '24', '用户上传参考图保留时长（小时）');
```

### 2.9 api_usage_logs — API调用日志表

```sql
CREATE TABLE api_usage_logs (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    task_id         UUID REFERENCES generation_tasks(id) ON DELETE SET NULL,
    
    -- 调用信息
    provider        VARCHAR(50),
    model           VARCHAR(200),
    api_key_id      INTEGER REFERENCES api_key_configs(id) ON DELETE SET NULL,
    is_system_key   BOOLEAN DEFAULT FALSE,   -- 是否使用系统Key
    
    -- 用量
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    total_tokens    INTEGER,
    
    -- 状态
    success         BOOLEAN NOT NULL,
    error_message   TEXT,
    latency_ms      INTEGER,                 -- 响应时间（毫秒）
    
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_usage_logs_user ON api_usage_logs(user_id);
CREATE INDEX idx_usage_logs_created ON api_usage_logs(created_at DESC);

-- 按月分区（可选，数据量大时启用）
-- CREATE TABLE api_usage_logs (...) PARTITION BY RANGE (created_at);
```

### 2.10 announcements — 系统公告表

```sql
CREATE TABLE announcements (
    id              SERIAL PRIMARY KEY,
    content         TEXT NOT NULL,
    is_important    BOOLEAN DEFAULT FALSE,
    is_active       BOOLEAN DEFAULT TRUE,
    
    created_by      INTEGER REFERENCES users(id),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

---

## 3. 关键查询场景

### 获取用户可用的LLM配置（用于负载均衡）
```sql
SELECT id, provider, base_url, api_key_encrypted, model_name, priority
FROM api_key_configs
WHERE user_id = :user_id
  AND model_type = :model_type  -- 'chat' 或 'image'
  AND is_verified = TRUE
  AND is_enabled = TRUE
ORDER BY priority DESC;
```

### 清理过期的用户上传文件
```sql
UPDATE uploaded_references
SET is_deleted = TRUE
WHERE expires_at < NOW()
  AND is_deleted = FALSE
RETURNING file_path;
-- 后端服务定时执行，返回的file_path用于物理删除文件
```

### 用户生成历史（分页）
```sql
SELECT t.id, t.task_type, t.pipeline_mode, t.status, t.created_at,
       r.image_path, r.thumbnail_path, r.quality_score, r.is_favorited
FROM generation_tasks t
LEFT JOIN generation_results r ON r.task_id = t.id AND r.candidate_index = 0
WHERE t.user_id = :user_id
ORDER BY t.created_at DESC
LIMIT :limit OFFSET :offset;
```

### 管理员统计面板
```sql
-- 用户总数
SELECT COUNT(*) FROM users;

-- 今日生成任务数
SELECT COUNT(*) FROM generation_tasks
WHERE created_at >= CURRENT_DATE;

-- API调用量统计（按Provider）
SELECT provider, COUNT(*), SUM(total_tokens)
FROM api_usage_logs
WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY provider;
```

---

## 4. 数据迁移策略

使用 **Alembic** 管理数据库迁移：

```bash
# 初始化
alembic init alembic

# 生成迁移
alembic revision --autogenerate -m "initial tables"

# 执行迁移
alembic upgrade head

# 回滚
alembic downgrade -1
```

---

## 5. 数据清理策略

| 数据类型 | 清理策略 |
|---------|---------|
| 用户上传参考图 | 定时任务检查 `expires_at`，到期自动删除文件和记录 |
| Pipeline事件流 | 任务完成30天后可清理 |
| API调用日志 | 保留90天，超过后归档或删除 |
| 生成结果图片 | 用户主动删除或账号注销时清理 |
