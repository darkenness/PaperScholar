# PaperScholar — API 设计文档

> 版本: v1.0 | 日期: 2026-02-27 | 基础路径: `/api/v1`

---

## 1. 通用约定

| 项目 | 说明 |
|------|------|
| **协议** | HTTPS (生产) / HTTP (开发) |
| **格式** | JSON (Content-Type: application/json) |
| **认证** | Bearer Token (`Authorization: Bearer <JWT>`) |
| **分页** | `?page=1&page_size=20`，响应包含 `total` / `page` / `page_size` |
| **错误格式** | `{"detail": "错误信息", "code": "ERROR_CODE"}` |

### HTTP 状态码

| 码 | 含义 |
|----|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 400 | 请求参数错误 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 409 | 冲突（如用户名已存在） |
| 422 | 数据验证失败 |
| 429 | 请求频率超限 |
| 500 | 服务器内部错误 |

---

## 2. 认证模块 `/api/v1/auth`

### POST `/auth/register` — 注册

```json
// Request
{
  "username": "string",
  "email": "string",
  "password": "string",
  "verification_code": "string"
}

// Response 201
{
  "user": { "id": 1, "username": "...", "email": "...", "role": "user" },
  "access_token": "jwt...",
  "token_type": "bearer"
}
```

### POST `/auth/send-code` — 发送验证码

```json
// Request
{ "email": "user@example.com" }

// Response 200
{ "message": "验证码已发送" }
```

### POST `/auth/login` — 登录

```json
// Request
{ "email": "string", "password": "string" }

// Response 200
{
  "user": { "id": 1, "username": "...", "email": "...", "role": "user" },
  "access_token": "jwt...",
  "token_type": "bearer"
}
```

### GET `/auth/me` — 获取当前用户 🔒

```json
// Response 200
{
  "id": 1,
  "username": "...",
  "email": "...",
  "role": "user",
  "system_api_approved": false,
  "created_at": "2026-02-27T00:00:00Z"
}
```

---

## 3. API Key 管理 `/api/v1/api-keys` 🔒

### GET `/api-keys` — 获取用户所有API Key配置

```json
// Response 200
{
  "chat_keys": [
    {
      "id": 1,
      "provider": "openai_compat",
      "base_url": "https://openrouter.ai/api/v1",
      "api_key_preview": "sk-or-v1...x4fG",
      "model_name": "gemini-2.5-pro",
      "is_verified": true,
      "priority": 0
    }
  ],
  "image_keys": [
    {
      "id": 2,
      "provider": "gemini",
      "base_url": null,
      "api_key_preview": "AIzaSy...7kLm",
      "model_name": "gemini-2.5-pro-image",
      "is_verified": true,
      "priority": 0
    }
  ]
}
```

### POST `/api-keys` — 添加API Key

```json
// Request
{
  "model_type": "chat",            // "chat" | "image"
  "provider": "openai_compat",     // "openai_compat" | "gemini" | "anthropic"
  "base_url": "https://openrouter.ai/api/v1",
  "api_key": "sk-or-v1-xxxxx",
  "model_name": "gemini-2.5-pro"
}

// Response 201
{
  "id": 1,
  "is_verified": false,
  "message": "API Key已保存，正在验证有效性..."
}
```

### POST `/api-keys/{id}/verify` — 验证API Key有效性

```json
// Response 200
{ "is_verified": true, "message": "API Key验证通过" }

// Response 200 (失败)
{ "is_verified": false, "message": "验证失败: Invalid API key" }
```

### PUT `/api-keys/{id}` — 更新API Key配置

```json
// Request (部分更新)
{
  "base_url": "https://new-endpoint.ai/v1",
  "model_name": "new-model",
  "priority": 1
}
```

### DELETE `/api-keys/{id}` — 删除API Key

```json
// Response 200
{ "message": "已删除" }
```

---

## 4. 系统API申请 `/api/v1/api-applications` 🔒

### POST `/api-applications` — 提交申请

```json
// Request
{ "reason": "科研论文写作需要，预计每月生成约50张图表" }

// Response 201
{ "id": 1, "status": "pending", "message": "申请已提交，等待管理员审核" }
```

### GET `/api-applications/my` — 查看我的申请状态

```json
// Response 200
{
  "applications": [
    {
      "id": 1,
      "status": "approved",
      "reason": "...",
      "review_comment": "已批准",
      "created_at": "...",
      "reviewed_at": "..."
    }
  ]
}
```

---

## 5. 图表生成 `/api/v1/generate` 🔒

### POST `/generate` — 创建生成任务

```json
// Request
{
  "task_type": "diagram",           // "diagram" | "plot"
  "content": "## Method\nOur approach uses...",
  "visual_intent": "A flowchart showing the training pipeline",
  "pipeline_mode": "dev_full",      // "vanilla" | "dev_planner" | "dev_planner_stylist" | "dev_planner_critic" | "dev_full"
  "retrieval_setting": "auto",      // "auto" | "manual" | "random" | "none"
  "num_candidates": 4,
  "aspect_ratio": "16:9",
  "max_critic_rounds": 3,
  "reference_image_ids": [1, 2]     // 用户上传的参考图ID（可选）
}

// Response 201
{
  "task_id": "a1b2c3d4-...",
  "status": "pending",
  "stream_url": "/api/v1/generate/a1b2c3d4-.../stream"
}
```

### GET `/generate/{task_id}/stream` — SSE实时事件流

```
// SSE Events
event: stage
data: {"name": "retriever", "status": "running", "progress": 0.1}

event: stage
data: {"name": "retriever", "status": "done", "progress": 0.2}

event: stage
data: {"name": "planner", "status": "running", "progress": 0.2}

event: intermediate
data: {"type": "text", "stage": "planner", "content": "A detailed flowchart showing..."}

event: stage
data: {"name": "planner", "status": "done", "progress": 0.4}

event: stage
data: {"name": "visualizer", "status": "running", "progress": 0.5}

event: intermediate
data: {"type": "image", "stage": "visualizer", "candidate_index": 0, "image_url": "/api/v1/files/tmp/xxx.jpg"}

event: stage
data: {"name": "critic", "status": "running", "round": 1, "progress": 0.7}

event: intermediate
data: {"type": "text", "stage": "critic", "content": "Suggestions: improve arrow alignment..."}

event: intermediate
data: {"type": "image", "stage": "critic", "round": 1, "candidate_index": 0, "image_url": "/api/v1/files/tmp/yyy.jpg"}

event: done
data: {"task_id": "a1b2c3d4-...", "status": "completed", "num_results": 4}
```

### GET `/generate/{task_id}` — 查询任务状态

```json
// Response 200
{
  "task_id": "a1b2c3d4-...",
  "status": "completed",
  "progress": 1.0,
  "current_stage": null,
  "results": [
    {
      "candidate_index": 0,
      "image_url": "/api/v1/files/results/xxx.jpg",
      "thumbnail_url": "/api/v1/files/results/xxx_thumb.jpg",
      "quality_score": 8.5,
      "is_favorited": false
    }
  ],
  "created_at": "...",
  "completed_at": "..."
}
```

### GET `/generate/history/list` — 生成历史（分页）

```json
// Query: ?page=1&page_size=20&task_type=diagram
// Response 200
{
  "total": 42,
  "page": 1,
  "page_size": 20,
  "items": [ /* generation_task + first result */ ]
}
```

### POST `/generate/{task_id}/cancel` — 取消任务

### POST `/generate/results/{result_id}/favorite` — 收藏/取消收藏

---

## 6. 参考图管理 `/api/v1/references` 🔒

### POST `/references/upload` — 上传参考图

```
// Request: multipart/form-data
// Field: file (PNG/JPG, max 20MB)

// Response 201
{
  "id": 1,
  "file_name": "ref_image.png",
  "file_size": 245000,
  "expires_at": "2026-02-28T00:00:00Z"
}
```

### GET `/references/my` — 我的上传参考图

### DELETE `/references/{id}` — 删除参考图

---

## 7. 图表编辑 `/api/v1/edit` 🔒 (Phase 3)

### POST `/edit` — 创建编辑任务

```json
// Request: multipart/form-data
// Fields:
//   image: (PNG/JPG file)
//   reference_image: (可选，风格迁移参考图)
//   sam_backend: "api"           // "local" | "api"
//   sam_api_key: "fal-xxx"       // API模式时用户提供
//   optimize_iterations: 2

// Response 201
{
  "task_id": "e1f2g3h4-...",
  "stream_url": "/api/v1/edit/e1f2g3h4-.../stream"
}
```

### GET `/edit/{task_id}/stream` — SSE事件流

### GET `/edit/{task_id}` — 查询编辑结果

```json
// Response 200
{
  "task_id": "...",
  "status": "completed",
  "figure_url": "/api/v1/files/...",
  "samed_url": "/api/v1/files/...",
  "template_svg_url": "/api/v1/files/...",
  "final_svg_url": "/api/v1/files/...",
  "icon_count": 5
}
```

---

## 8. 精修增强 `/api/v1/refine` 🔒

### POST `/refine/enhance` — 图片增强

```
// Request: multipart/form-data
// Fields:
//   image: (要精修的图片)
//   instruction: "提高整体视觉质量，使其达到出版级别"
//   resolution: "2k"             // "2k" | "4k"

// Response 200
{
  "task_id": "...",
  "original_url": "/uploads/refine/.../original.png",
  "enhanced_url": "/uploads/refine/.../enhanced.png"
}
```

### POST `/refine/style-transfer` — 风格迁移

```
// Request: multipart/form-data
// Fields:
//   source_image: (源图片)
//   reference_image: (参考风格图片)

// Response 200
{
  "task_id": "...",
  "source_url": "/uploads/refine/.../source.png",
  "reference_url": "/uploads/refine/.../reference.png",
  "result_url": "/uploads/refine/.../result.png"
}
```

---

## 9. 管理员接口 `/api/v1/admin` 🔒🛡️

> 需要 role=admin

### GET `/admin/users` — 用户列表（分页）
### PUT `/admin/users/{id}/role` — 修改用户角色
### GET `/admin/applications` — 待审核申请列表
### PUT `/admin/applications/{id}` — 审核申请

```json
// Request
{ "status": "approved", "comment": "已批准" }
```

### GET `/admin/stats` — 系统统计

```json
// Response 200
{
  "total_users": 120,
  "today_tasks": 45,
  "total_tasks": 3200,
  "api_usage_7d": {
    "by_provider": { "openai_compat": 1500, "gemini": 800 },
    "total_tokens": 2500000
  }
}
```

### GET `/admin/configs` — 获取系统配置
### PUT `/admin/configs/{key}` — 更新系统配置

### POST `/admin/announcements` — 发布公告
### GET `/admin/announcements` — 公告列表
### DELETE `/admin/announcements/{id}` — 删除公告

---

## 10. 文件服务

> 文件通过 `/uploads/` 静态挂载提供访问，无独立的文件API路由。
>
> 例如: `GET /uploads/results/{task_id}/candidate_0.png`
>
> **待实现**: 批量ZIP下载接口 `GET /files/download/{task_id}`

---

## 11. 速率限制（待实现）

> 当前未实现速率限制中间件。计划目标:

| 接口类别 | 限制 |
|---------|------|
| 认证接口 | 10次/分钟/IP |
| 生成任务 | 5次/分钟/用户 |
| 普通API | 60次/分钟/用户 |
| 文件上传 | 10次/分钟/用户 |
| 管理员接口 | 120次/分钟/用户 |
