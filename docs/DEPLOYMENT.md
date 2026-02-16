# AI Task Manager - 部署指南

## M1 部署配置

本指南介绍如何在开发和生产环境中部署 AI Task Manager。

## 系统要求

### 软件依赖
- **Python**: 3.10+
- **Node.js**: 20+
- **Git**: 任意版本

### AI CLI 工具（至少安装一个）
- **Claude Code**: https://docs.anthropic.com/claude/docs/claude-code
- **Codex CLI**: 相关文档

### 操作系统
- Linux / macOS / Windows (WSL2 或 Git Bash)

## 快速开始（本地开发）

### 1. 克隆项目

```bash
git clone <repository-url>
cd AI-slave
```

### 2. 后端设置

```bash
# 创建虚拟环境并安装依赖
./scripts/setup_env.sh

# 启动后端服务器
./scripts/start_server.sh
```

后端将运行在 `http://127.0.0.1:8000`

### 3. 前端设置

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端将运行在 `http://localhost:3000`

### 4. 初始化工作区

访问 http://localhost:3000，然后：

1. 通过 API 或直接在数据库中注册工作区:

```bash
curl -X POST "http://127.0.0.1:8000/api/workspaces" \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/path/to/your/workspace",
    "display_name": "My Workspace",
    "runner_id": 1
  }'
```

2. 在 Web UI 中创建任务

## 环境配置

### 后端环境变量

编辑 `backend/config.py` 或设置环境变量:

```bash
# 数据库位置
export DATABASE_URL="sqlite:///./backend/tasks.db"

# API 端口
export API_PORT=8000

# 日志级别
export LOG_LEVEL="INFO"

# CORS 允许的源
export CORS_ORIGINS='["http://localhost:3000"]'
```

### 前端环境变量

创建 `frontend/.env.local`:

```env
# API 基础 URL
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api
```

## 生产部署

### 方式 1: 直接部署（单机）

#### 后端

```bash
# 1. 安装依赖
cd backend
pip install -r requirements.txt

# 2. 配置环境变量
export DATABASE_URL="sqlite:///./tasks.db"
export API_HOST="0.0.0.0"
export API_PORT=8000

# 3. 使用 gunicorn 运行（推荐）
pip install gunicorn
gunicorn main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers 4 \
  --bind 0.0.0.0:8000 \
  --timeout 300

# 或使用 uvicorn 直接运行
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

#### 前端

```bash
# 1. 构建生产版本
cd frontend
npm run build

# 2. 启动生产服务器
npm start

# 或使用 PM2 管理进程
npm install -g pm2
pm2 start npm --name "ai-task-frontend" -- start
pm2 save
pm2 startup
```

### 方式 2: Docker 部署（推荐生产环境）

#### 创建 Docker Compose 配置

创建 `docker-compose.yml`:

```yaml
version: '3.8'

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - ./backend/tasks.db:/app/tasks.db
    environment:
      - DATABASE_URL=sqlite:///./tasks.db
      - API_HOST=0.0.0.0
      - API_PORT=8000
      - CORS_ORIGINS=["http://localhost:3000"]
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
    depends_on:
      - backend
    restart: unless-stopped
```

#### 后端 Dockerfile

创建 `backend/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# 复制代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["gunicorn", "main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "300"]
```

#### 前端 Dockerfile

创建 `frontend/Dockerfile`:

```dockerfile
FROM node:20-alpine AS builder

WORKDIR /app

# 安装依赖
COPY package*.json ./
RUN npm ci

# 构建
COPY . .
RUN npm run build

# 生产镜像
FROM node:20-alpine

WORKDIR /app

COPY --from=builder /app/package*.json ./
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/node_modules ./node_modules

EXPOSE 3000

CMD ["npm", "start"]
```

#### 启动 Docker 容器

```bash
docker-compose up -d
```

### 方式 3: Nginx 反向代理

创建 `/etc/nginx/sites-available/ai-task-manager`:

```nginx
upstream backend {
    server 127.0.0.1:8000;
}

upstream frontend {
    server 127.0.0.1:3000;
}

server {
    listen 80;
    server_name your-domain.com;

    # 前端
    location / {
        proxy_pass http://frontend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # 后端 API
    location /api {
        proxy_pass http://backend/api;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # SSE 日志流（特殊配置）
    location /api/logs {
        proxy_pass http://backend/api/logs;
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

启用配置:

```bash
sudo ln -s /etc/nginx/sites-available/ai-task-manager /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 数据库管理

### SQLite（M1 默认）

**备份**:
```bash
cp backend/tasks.db backend/tasks.db.backup
```

**迁移到 PostgreSQL（M2+）**:
```bash
# 1. 安装 PostgreSQL 适配器
pip install psycopg2-binary

# 2. 更新 DATABASE_URL
export DATABASE_URL="postgresql://user:password@localhost/ai_tasks"

# 3. 运行迁移（需要实现迁移脚本）
python -m alembic upgrade head
```

## 监控与日志

### 后端日志

日志输出到标准输出（stdout），可以重定向:

```bash
# 开发环境
./scripts/start_server.sh > backend.log 2>&1

# 生产环境（使用 systemd）
sudo journalctl -u ai-task-backend -f
```

### 前端日志

```bash
# 查看 Next.js 日志
pm2 logs ai-task-frontend
```

### 健康检查

```bash
# 后端健康检查
curl http://localhost:8000/health

# 预期输出: {"status":"healthy"}
```

## 安全配置

### 1. CORS 配置

仅允许可信源:

```python
# backend/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend-domain.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
```

### 2. API 认证（M2+）

计划实现 JWT 或 API Key 认证。

### 3. HTTPS

使用 Let's Encrypt 免费证书:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

## 性能优化

### 后端优化

1. **使用 Gunicorn + Uvicorn Worker**:
   - 多进程处理并发请求
   - Worker 数量 = (2 × CPU 核心数) + 1

2. **数据库连接池**:
   - SQLAlchemy 默认已启用连接池

3. **异步任务调度**:
   - 已使用 asyncio.create_task

### 前端优化

1. **静态资源 CDN**:
   - 将 `_next/static/` 上传到 CDN

2. **图像优化**:
   - 使用 Next.js Image 组件

3. **缓存策略**:
   - SWR 自动缓存和重验证

## 故障排查

### 后端启动失败

```bash
# 检查端口占用
netstat -tuln | grep 8000

# 查看详细错误
cd backend
../venv/Scripts/python.exe main.py
```

### 前端构建失败

```bash
# 清除缓存
rm -rf frontend/.next frontend/node_modules
npm install
npm run build
```

### SSE 日志流断开

- 检查 Nginx 配置的 `proxy_buffering off`
- 验证 `proxy_read_timeout` 足够长
- 确认防火墙未阻止长连接

## 扩展部署（M2+）

### 多 Runner 分布式部署

1. 在不同机器上部署 Runner
2. 通过 API 注册远程 Runner
3. 配置 Runner 的 `max_parallel` 和 `capabilities`

### 负载均衡

使用 Nginx 或 HAProxy 实现后端负载均衡:

```nginx
upstream backend_cluster {
    least_conn;
    server backend1:8000;
    server backend2:8000;
    server backend3:8000;
}
```

## 自动化部署

### CI/CD 配置示例（GitHub Actions）

创建 `.github/workflows/deploy.yml`:

```yaml
name: Deploy

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Deploy to production
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.HOST }}
          username: ${{ secrets.USERNAME }}
          key: ${{ secrets.SSH_KEY }}
          script: |
            cd /opt/ai-task-manager
            git pull
            docker-compose down
            docker-compose up -d --build
```

## 备份策略

### 自动备份脚本

创建 `scripts/backup.sh`:

```bash
#!/bin/bash

BACKUP_DIR="/opt/backups/ai-task-manager"
DATE=$(date +%Y%m%d_%H%M%S)

# 备份数据库
cp backend/tasks.db "$BACKUP_DIR/tasks_$DATE.db"

# 保留最近 30 天的备份
find "$BACKUP_DIR" -name "tasks_*.db" -mtime +30 -delete
```

配置 cron 定时任务:

```bash
# 每天凌晨 2 点备份
0 2 * * * /opt/ai-task-manager/scripts/backup.sh
```

## 总结

- ✅ 本地开发：快速启动，适合开发和测试
- ✅ Docker 部署：推荐生产环境，易于维护
- ✅ Nginx 反向代理：提供 HTTPS 和负载均衡
- ✅ 监控日志：使用 systemd 或 PM2 管理进程
- ✅ 定期备份：防止数据丢失

有问题请查看项目文档或提交 Issue。
