# PaperScholar 本地启动脚本 (Windows PowerShell)
# 用法: 右键 "使用 PowerShell 运行" 或在终端执行 ./start-local.ps1

Write-Host "=== PaperScholar 本地运行启动器 ===" -ForegroundColor Cyan
Write-Host ""

# 1. 检查 Docker Desktop
Write-Host "[1/5] 检查 Docker Desktop 状态..." -ForegroundColor Yellow
try {
    $dockerInfo = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Docker daemon not reachable"
    }
    Write-Host "  ✓ Docker 守护进程正常" -ForegroundColor Green
} catch {
    Write-Host "  ✗ 无法连接到 Docker Desktop 引擎！" -ForegroundColor Red
    Write-Host ""
    Write-Host "请先启动 Docker Desktop：" -ForegroundColor Yellow
    Write-Host "  1. 从 Windows 开始菜单搜索并打开 'Docker Desktop'"
    Write-Host "  2. 等待它完全启动（托盘图标变成绿色鲸鱼）"
    Write-Host "  3. 再次运行此脚本"
    Write-Host ""
    Read-Host "按 Enter 键退出"
    exit 1
}

# 2. 停止旧容器（如果有）
Write-Host "[2/5] 清理旧容器..." -ForegroundColor Yellow
docker compose down --remove-orphans 2>$null | Out-Null
Write-Host "  ✓ 清理完成" -ForegroundColor Green

# 3. 启动所有服务
Write-Host "[3/5] 启动 Docker Compose 服务（首次构建可能需要 5-15 分钟）..." -ForegroundColor Yellow
Write-Host "  - PostgreSQL + Redis + Backend (带自动迁移) + Frontend" -ForegroundColor Gray
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ 启动失败，请查看上面的错误日志" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ 服务已启动（后台运行）" -ForegroundColor Green

# 4. 等待服务就绪
Write-Host "[4/5] 等待服务就绪（最多 90 秒）..." -ForegroundColor Yellow
$maxWait = 90
$waited = 0
$healthy = $false
while ($waited -lt $maxWait) {
    Start-Sleep -Seconds 3
    $waited += 3

    $backendLog = docker logs paperscholar-backend --tail 20 2>&1 | Out-String
    if ($backendLog -match "Uvicorn running on|Application startup complete") {
        $healthy = $true
        break
    }
    Write-Host "  ... 等待中 ($waited s)" -ForegroundColor Gray
}

if (-not $healthy) {
    Write-Host "  ⚠ 后端启动较慢，请稍后手动检查日志" -ForegroundColor Yellow
} else {
    Write-Host "  ✓ 后端已就绪" -ForegroundColor Green
}

# 5. 显示访问信息
Write-Host "[5/5] 完成！" -ForegroundColor Green
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "服务地址：" -ForegroundColor White
Write-Host "  前端 UI:     http://localhost:3000" -ForegroundColor Green
Write-Host "  后端 API:    http://localhost:8000" -ForegroundColor Green
Write-Host "  API 文档:    http://localhost:8000/docs" -ForegroundColor Green
Write-Host ""
Write-Host "邀请码（注册用）: devinvite2026" -ForegroundColor Yellow
Write-Host ""
Write-Host "下一步操作：" -ForegroundColor White
Write-Host "  1. 浏览器打开 http://localhost:3000/register"
Write-Host "  2. 使用邀请码注册（第一个用户自动成为管理员）"
Write-Host "  3. 登录后进入「API 配置」添加你的 LLM API Key（Chat + Image 模型）"
Write-Host "  4. 开始使用图表生成功能"
Write-Host ""
Write-Host "常用命令：" -ForegroundColor Gray
Write-Host "  查看日志: docker compose logs -f backend"
Write-Host "  停止服务: docker compose down"
Write-Host "  重启后端: docker compose restart backend"
Write-Host "========================================" -ForegroundColor Cyan

# 可选：打开浏览器
$open = Read-Host "是否现在打开浏览器访问前端？(y/N)"
if ($open -match '^[yY]') {
    Start-Process "http://localhost:3000"
}
