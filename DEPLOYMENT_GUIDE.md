# PaperScholar 优化部署指南

## 优化内容总结

本次优化包含以下四个方面：

### 1. 降低 LoadBalancer 429 冷却时间
- **改动**：将 429 错误的冷却时间从 `60 * round_index` 降低到 `30 * round_index`
- **效果**：减少 API 限流后的等待时间，从 60-180 秒降低到 30-90 秒
- **文件**：`backend/app/llm/load_balancer.py`

### 2. 优化 InputOptimizer 并发策略
- **改动**：将 InputOptimizer 的并行调用改成顺序调用
- **效果**：避免同时发起多个请求触发 VectorEngine 的并发限流
- **文件**：`backend/app/agents/pipeline.py`

### 3. 接入 Celery + Redis 异步任务队列
- **新增文件**：
  - `backend/app/celery_app.py` - Celery 应用配置
  - `backend/app/tasks/generation_tasks.py` - 图片生成任务
  - `backend/app/tasks/__init__.py` - 任务包初始化
  - `docker-compose.celery.yml` - Celery 服务配置
- **效果**：
  - 实现全局 rate limiting
  - 避免多个任务同时抢占同一个 API key
  - 支持任务队列和优先级管理
  - 支持任务重试和失败处理

### 4. 实现 key pool 管理服务
- **新增文件**：`backend/app/services/key_pool_service.py`
- **效果**：
  - 动态监控每个 API key 的健康状态
  - 自动切换到健康的 key
  - 记录每个 key 的调用统计、失败率、延迟
  - 自动从冷却中恢复

## 部署步骤

### 步骤 1：备份当前代码

```bash
ssh Hudi
cd /opt/paperscholar
cp -r /opt/paperscholar /opt/paperscholar.backup.$(date +%Y%m%d_%H%M%S)
```

### 步骤 2：同步新代码到服务器

在本地执行：

```bash
cd C:\Users\11750\Desktop\Hudi_code_compare_20260501_180431\hudi-opt-paperscholar
tar -czf paperscholar-optimized.tar.gz backend/app docker-compose.celery.yml
scp paperscholar-optimized.tar.gz Hudi:/tmp/
```

在服务器上执行：

```bash
ssh Hudi
cd /opt/paperscholar
tar -xzf /tmp/paperscholar-optimized.tar.gz
```

### 步骤 3：更新 requirements.txt

在服务器上执行：

```bash
ssh Hudi
cd /opt/paperscholar/backend
cat >> requirements.txt <<'EOF'
celery[redis]==5.3.4
flower==2.0.1
kombu==5.3.4
EOF
```

### 步骤 4：更新 .env 配置

在服务器上执行：

```bash
ssh Hudi
cd /opt/paperscholar
# 确保 REDIS_URL 已配置
grep -q "REDIS_URL" .env || echo "REDIS_URL=redis://redis:6379/0" >> .env
```

### 步骤 5：重新构建并启动服务

```bash
ssh Hudi
cd /opt/paperscholar

# 停止现有服务
docker compose -f docker-compose.deploy.yml down

# 重新构建后端镜像
docker compose -f docker-compose.deploy.yml build backend

# 启动核心服务
docker compose -f docker-compose.deploy.yml up -d

# 启动 Celery 服务（可选）
docker compose -f docker-compose.celery.yml up -d
```

### 步骤 6：验证部署

```bash
# 检查所有容器状态
docker ps

# 检查后端日志
docker logs paperscholar-backend --tail=50

# 检查 Celery worker 日志（如果启动了）
docker logs paperscholar-celery-worker-1 --tail=50

# 测试健康检查
curl http://localhost:8000/api/health
```

## 配置说明

### Celery 配置（可选）

如果要启用 Celery 异步任务队列，需要：

1. **启动 Celery 服务**：
   ```bash
   docker compose -f docker-compose.celery.yml up -d
   ```

2. **访问 Flower 监控界面**：
   - URL: http://localhost:5555
   - 可以查看任务队列、worker 状态、任务历史

3. **配置任务路由**（可选）：
   在 `backend/app/celery_app.py` 中调整 `task_annotations` 来设置不同任务的速率限制

### Key Pool 管理配置

Key Pool Manager 会自动启动，无需额外配置。可以通过以下方式查看健康状态：

```python
# 在后端代码中
from app.services.key_pool_service import get_key_pool_manager

key_pool = await get_key_pool_manager()
summary = await key_pool.get_health_summary()
print(summary)
```

## 回滚方案

如果部署后出现问题，可以快速回滚：

```bash
ssh Hudi
cd /opt/paperscholar

# 停止所有服务
docker compose -f docker-compose.deploy.yml down
docker compose -f docker-compose.celery.yml down

# 恢复备份
BACKUP_DIR=$(ls -td /opt/paperscholar.backup.* | head -1)
rm -rf /opt/paperscholar
mv $BACKUP_DIR /opt/paperscholar

# 重新启动
cd /opt/paperscholar
docker compose -f docker-compose.deploy.yml up -d
```

## 监控和调优

### 1. 监控 API key 健康状态

可以添加一个管理后台接口来查看 key pool 状态：

```python
# backend/app/api/admin.py
from app.services.key_pool_service import get_key_pool_manager

@router.get("/key-pool-status")
async def get_key_pool_status():
    key_pool = await get_key_pool_manager()
    return await key_pool.get_health_summary()
```

### 2. 调整冷却时间

如果发现冷却时间仍然太长或太短，可以在 `backend/app/llm/load_balancer.py` 中调整：

```python
if status == 429:
    return (retry_after or min(30.0 * round_index, 90.0)) + jitter, True
    # 可以调整为：min(20.0 * round_index, 60.0) 更激进
    # 或者：min(45.0 * round_index, 120.0) 更保守
```

### 3. 调整 Celery worker 并发数

在 `docker-compose.celery.yml` 中调整 `--concurrency` 参数：

```yaml
command: celery -A app.celery_app worker --loglevel=info --concurrency=4
# 可以根据服务器资源调整为 2, 4, 8 等
```

## 常见问题

### Q1: 为什么还是会触发 429 限流？

A: VectorEngine 的限流策略非常严格，可能是每分钟 1-2 个请求。建议：
- 添加更多不同的 API key
- 使用不同的 provider（如果有）
- 联系 VectorEngine 升级套餐

### Q2: Celery 任务队列是否必须启用？

A: 不是必须的。前两个优化（降低冷却时间 + 顺序调用）已经可以显著改善限流问题。Celery 是长期优化方案，适合高并发场景。

### Q3: 如何查看 key pool 的健康状态？

A: 可以通过以下方式：
1. 查看后端日志：`docker logs paperscholar-backend | grep KeyPoolManager`
2. 添加管理后台接口（见上文"监控和调优"部分）
3. 直接在数据库中查询 `api_usage_logs` 表

## 性能对比

### 优化前
- 429 冷却时间：60-180 秒
- InputOptimizer：并行调用，容易触发限流
- 无全局 rate limiting
- 无 key 健康监控

### 优化后
- 429 冷却时间：30-90 秒（减少 50%）
- InputOptimizer：顺序调用，避免并发限流
- 支持 Celery 全局 rate limiting（可选）
- 自动监控 key 健康状态并切换

## 联系支持

如有问题，请查看：
- 后端日志：`docker logs paperscholar-backend`
- Celery 日志：`docker logs paperscholar-celery-worker-1`
- Redis 日志：`docker logs paperscholar-redis`
