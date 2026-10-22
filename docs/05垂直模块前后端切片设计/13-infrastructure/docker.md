# 13-基础设施切片：Docker 容器化设计

> **架构约束**：§2.3 Docker + Docker Compose、§8 目录结构、§9.2 部署编排
> **审查修复**：INF-1 [P0] Docker/Docker Compose 配置文件缺失
> **创建日期**：2026-10-12

---

## 1. 设计概述

### 1.1 问题背景

架构文档（§2.3）明确定义了 **Docker + Docker Compose** 作为容器化方案，但此前没有任何切片提供 Dockerfile 或 docker-compose 配置，属于架构审查中的 P0 级缺失项（INF-1）。本文档补齐该缺口，提供完整的容器化设计。

### 1.2 容器拓扑

| 容器 | 镜像来源 | 端口 | 角色 |
|------|----------|------|------|
| `app` | Dockerfile（python:3.12-slim） | 8000 | FastAPI 主应用 |
| `celery-worker` | Dockerfile（同 app） | - | 异步任务执行 |
| `celery-beat` | Dockerfile（同 app） | - | 定时任务调度 |
| `gpu-service` | Dockerfile.gpu（nvidia/cuda:12.1.1） | 8501 | AI 推理服务 |
| `db` | postgres:15-alpine | 5432 | 主数据库 |
| `redis` | redis:7-alpine | 6379 | 缓存 + Celery Broker |
| `nginx` | nginx:alpine | 80 / 443 | 反向代理 + TLS 终止 |

### 1.3 文件清单

| 文件 | 用途 | 对应架构章节 |
|------|------|-------------|
| `Dockerfile` | 主应用镜像（FastAPI + Celery） | §2.3、§9.2 |
| `Dockerfile.gpu` | GPU 推理服务镜像 | §2.3、§9.2 |
| `docker-compose.yml` | 开发环境编排 | §9.2 |
| `docker-compose.prod.yml` | 生产环境覆盖配置 | §9.2 |
| `.env.example` | 环境变量模板 | §9.2 |
| `nginx.conf` | Nginx 反向代理配置 | §9.2 |

---

## 2. Dockerfile（主应用）

为 FastAPI + Celery 创建的多阶段 Dockerfile，同时服务于 `app`、`celery-worker`、`celery-beat` 三个容器（通过 docker-compose 的 `command` 覆盖启动指令）。

```dockerfile
# =============================================================================
# Dockerfile — 乒乓智能分析平台主应用（FastAPI + Celery）
# 架构约束：§2.3 Docker + Docker Compose、§9.2 部署编排
# =============================================================================

# ---------- Stage 1: builder ----------
FROM python:3.12-slim AS builder

# 安装构建依赖（编译 Pillow / lxml 等需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 创建虚拟环境，隔离依赖
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 先复制依赖清单，利用 Docker 层缓存
WORKDIR /build
COPY requirements.txt .

# 安装 Python 依赖到虚拟环境
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim AS runtime

# 安装运行时系统依赖
#   libgl1        — OpenCV(cv2) 所需的 GL 库
#   libglib2.0-0  — OpenCV 所需的 glib
#   ffmpeg        — 视频处理（抽帧、转码）
#   libpq5        — psycopg2/asyncpg 运行时
#   curl          — healthcheck 探针
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 创建非 root 用户
RUN groupadd -r appuser && useradd -r -g appuser -d /home/appuser -m appuser

WORKDIR /app

# 复制应用代码
COPY --chown=appuser:appuser . /app

# 创建运行时目录（日志、临时文件）
RUN mkdir -p /app/logs /app/tmp && chown -R appuser:appuser /app/logs /app/tmp

# 切换非 root 用户
USER appuser

# 暴露 FastAPI 端口
EXPOSE 8000

# 默认启动命令（celery-worker / celery-beat 由 compose 覆盖 command）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 2.1 多阶段构建说明

| 阶段 | 作用 | 关键操作 |
|------|------|----------|
| `builder` | 编译 Python 依赖 | 安装 gcc/g++/libpq-dev，创建 venv，pip install |
| `runtime` | 运行时镜像 | 仅复制 venv，安装运行时库，创建非 root 用户 |

- **层缓存优化**：`requirements.txt` 单独先复制，代码变更不触发依赖重装
- **镜像体积**：runtime 阶段不含编译工具，约 350MB（含 OpenCV + ffmpeg）
- **安全性**：非 root 用户 `appuser` 运行，避免容器内提权

### 2.2 .dockerignore

```
# .dockerignore
__pycache__
*.pyc
*.pyo
.git
.gitignore
.env
.env.*
!.env.example
venv/
.venv/
env/
.idea/
.vscode/
*.egg-info/
dist/
build/
tests/
docs/
*.md
*.log
tmp/
```

---

## 3. Dockerfile.gpu（GPU 推理服务）

为 AI 推理服务单独构建的 GPU 镜像，使用 CUDA 基础镜像并安装深度学习推理框架。

```dockerfile
# =============================================================================
# Dockerfile.gpu — GPU 推理服务
# 架构约束：§2.3 Docker + Docker Compose、§9.2 部署编排
# 基础镜像：nvidia/cuda:12.1.1-runtime-ubuntu22.04
# =============================================================================

FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

# 设置非交互模式，避免 tzdata 等交互弹窗
ENV DEBIAN_FRONTEND=noninteractive

# 安装系统依赖 + Python 3.12
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa -y \
    && apt-get update && apt-get install -y --no-install-recommends \
        python3.12 \
        python3.12-venv \
        python3.12-dev \
        python3-pip \
        libgl1 \
        libglib2.0-0 \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/*

# 设置 python3.12 为默认
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1

# 升级 pip
RUN python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel

# 创建虚拟环境
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility

WORKDIR /gpu_service

# 先复制 GPU 服务依赖清单（独立维护）
COPY gpu_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制推理服务代码
COPY gpu_service/ /gpu_service/

# 创建非 root 用户
RUN groupadd -r gpuuser && useradd -r -g gpuuser -d /home/gpuuser -m gpuuser && \
    chown -R gpuuser:gpuuser /gpu_service
USER gpuuser

EXPOSE 8501

CMD ["uvicorn", "gpu_service.main:app", "--host", "0.0.0.0", "--port", "8501"]
```

### 3.1 GPU 镜像说明

| 项目 | 选择 | 理由 |
|------|------|------|
| 基础镜像 | `nvidia/cuda:12.1.1-runtime-ubuntu22.04` | 稳定 LTS，兼容 PyTorch 2.1 / ONNX Runtime 1.16 |
| Python | 3.12（deadsnakes PPA） | 与主应用保持版本一致 |
| 推理框架 | torch / onnxruntime-gpu / ultralytics / mediapipe | 覆盖 YOLOv8、姿态估计、ONNX 推理 |
| GPU 暴露 | `NVIDIA_VISIBLE_DEVICES=all` | 由 docker-compose `deploy.resources` 控制 |

> **替代方案**：如需内置 PyTorch 的镜像，可替换为 `pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime`，省去手动安装 torch 步骤，但镜像体积更大（约 6GB）。

### 3.2 gpu_service/requirements.txt（参考）

```text
# gpu_service/requirements.txt
fastapi==0.110.0
uvicorn[standard]==0.27.1
pydantic==2.6.1
torch==2.1.2
onnxruntime-gpu==1.16.3
ultralytics==8.1.7
mediapipe==0.10.9
opencv-python-headless==4.9.0.80
numpy==1.26.3
redis==5.0.1
psycopg2-binary==2.9.9
python-multipart==0.0.9
```

---

## 4. docker-compose.yml（开发环境）

开发环境配置，支持代码热重载、数据库持久化、GPU 服务可选启用。

```yaml
# =============================================================================
# docker-compose.yml — 开发环境
# 架构约束：§9.2 部署编排
# 使用方式：docker compose up -d
# =============================================================================
version: "3.9"

services:
  # ---------------------------------------------------------------------------
  # FastAPI 主应用
  # ---------------------------------------------------------------------------
  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: tta-app
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "3"
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      - ENV=development
      - DEBUG=true
    volumes:
      # 代码热重载：本地代码变更实时同步到容器
      - ./app:/app/app:cached
      - ./gpu_service:/app/gpu_service:cached
      - ./logs:/app/logs
      - ./tmp:/app/tmp
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - tta-net

  # ---------------------------------------------------------------------------
  # Celery Worker（异步任务执行）
  # ---------------------------------------------------------------------------
  celery-worker:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: tta-celery-worker
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "3"
    command: celery -A app.celery_app worker --loglevel=info --concurrency=4
    env_file:
      - .env
    environment:
      - ENV=development
    volumes:
      - ./app:/app/app:cached
      - ./logs:/app/logs
      - ./tmp:/app/tmp
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - tta-net

  # ---------------------------------------------------------------------------
  # Celery Beat（定时任务调度）
  # ---------------------------------------------------------------------------
  celery-beat:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: tta-celery-beat
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "3"
    command: celery -A app.celery_app beat --loglevel=info
    env_file:
      - .env
    environment:
      - ENV=development
    volumes:
      - ./app:/app/app:cached
      - ./logs:/app/logs
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - tta-net

  # ---------------------------------------------------------------------------
  # PostgreSQL 15 数据库
  # ---------------------------------------------------------------------------
  db:
    image: postgres:15-alpine
    container_name: tta-db
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-tta}
      POSTGRES_USER: ${POSTGRES_USER:-tta_user}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-tta_pass_dev}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-tta_user} -d ${POSTGRES_DB:-tta}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - tta-net

  # ---------------------------------------------------------------------------
  # Redis 7（缓存 + Celery Broker）
  # ---------------------------------------------------------------------------
  redis:
    image: redis:7-alpine
    container_name: tta-redis
    command: redis-server --requirepass ${REDIS_PASSWORD:-redis_dev_pass}
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD:-redis_dev_pass}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - tta-net

  # ---------------------------------------------------------------------------
  # GPU 推理服务（需要 NVIDIA Container Toolkit）
  # ---------------------------------------------------------------------------
  gpu-service:
    build:
      context: .
      dockerfile: Dockerfile.gpu
    container_name: tta-gpu-service
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "3"
    ports:
      - "8501:8501"
    env_file:
      - .env
    environment:
      - ENV=development
      - INFERENCE_PORT=8501
    volumes:
      - ./gpu_service:/gpu_service:cached
      - ./models:/gpu_service/models:cached
      - ./tmp:/app/tmp
    depends_on:
      db:
        condition: service_healthy
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    restart: unless-stopped
    networks:
      - tta-net

  # ---------------------------------------------------------------------------
  # Nginx 反向代理
  # ---------------------------------------------------------------------------
  nginx:
    image: nginx:alpine
    container_name: tta-nginx
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "3"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./static:/usr/share/nginx/html/static:ro
      - nginx-logs:/var/log/nginx
    depends_on:
      - app
    restart: unless-stopped
    networks:
      - tta-net

# =============================================================================
# 卷
# =============================================================================
volumes:
  pgdata:
    driver: local
  redisdata:
    driver: local
  nginx-logs:
    driver: local

# =============================================================================
# 网络
# =============================================================================
networks:
  tta-net:
    driver: bridge
```

### 4.1 开发环境特性

| 特性 | 实现方式 |
|------|----------|
| 代码热重载 | `volumes: ./app:/app/app:cached` + uvicorn `--reload`（可选追加） |
| 数据库持久化 | `pgdata` 命名卷，容器删除后数据保留 |
| Redis 持久化 | `redisdata` 命名卷 |
| GPU 支持 | `deploy.resources.reservations.devices` 声明 GPU |
| 健康检查 | db / redis 配置 `healthcheck`，app `depends_on` 条件等待 |
| 日志收集 | `./logs` 挂载到容器，方便本地查看 |

---

## 5. docker-compose.prod.yml（生产环境）

生产环境覆盖配置，使用 `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` 启动。

```yaml
# =============================================================================
# docker-compose.prod.yml — 生产环境覆盖配置
# 架构约束：§9.2 部署编排
# 使用方式：docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
# =============================================================================

services:
  # ---------------------------------------------------------------------------
  # FastAPI 主应用 — gunicorn + uvicorn workers
  # ---------------------------------------------------------------------------
  app:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        - ENV=production
    container_name: tta-app-prod
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "3"
    ports:
      - "8000:8000"
    env_file:
      - .env.prod
    environment:
      - ENV=production
      - DEBUG=false
    # 覆盖启动命令：gunicorn 多 worker + uvicorn worker class
    command: >
      gunicorn app.main:app
      --bind 0.0.0.0:8000
      --workers 4
      --worker-class uvicorn.workers.UvicornWorker
      --timeout 120
      --keep-alive 5
      --log-level info
      --access-logfile /app/logs/gunicorn-access.log
      --error-logfile /app/logs/gunicorn-error.log
    # 生产环境去除热重载 volume
    volumes:
      - ./logs:/app/logs
      - ./tmp:/app/tmp
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: always
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 2G
        reservations:
          cpus: "0.5"
          memory: 512M
    networks:
      - tta-net

  # ---------------------------------------------------------------------------
  # Celery Worker — 生产配置
  # ---------------------------------------------------------------------------
  celery-worker:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: tta-celery-worker-prod
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "3"
    command: >
      celery -A app.celery_app worker
      --loglevel=warning
      --concurrency=8
      --max-tasks-per-child=100
      --time-limit=3600
      --soft-time-limit=3000
    env_file:
      - .env.prod
    environment:
      - ENV=production
    volumes:
      - ./logs:/app/logs
      - ./tmp:/app/tmp
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "celery -A app.celery_app inspect ping -d celery@$$HOSTNAME || exit 1"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 30s
    restart: always
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 2G
    networks:
      - tta-net

  # ---------------------------------------------------------------------------
  # Celery Beat — 生产配置
  # ---------------------------------------------------------------------------
  celery-beat:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: tta-celery-beat-prod
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "3"
    command: >
      celery -A app.celery_app beat
      --loglevel=warning
      --schedule=/app/tmp/celerybeat-schedule
    env_file:
      - .env.prod
    environment:
      - ENV=production
    volumes:
      - ./logs:/app/logs
      - ./tmp:/app/tmp
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "pgrep -f 'celery.*beat' || exit 1"]
      interval: 60s
      timeout: 10s
      retries: 3
    restart: always
    networks:
      - tta-net

  # ---------------------------------------------------------------------------
  # PostgreSQL — 生产配置
  # ---------------------------------------------------------------------------
  db:
    image: postgres:15-alpine
    container_name: tta-db-prod
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    # 生产环境不暴露端口到宿主机（仅内部网络访问）
    ports: []
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 15s
      timeout: 5s
      retries: 5
    restart: always
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 2G
        reservations:
          cpus: "0.5"
          memory: 512M
    networks:
      - tta-net

  # ---------------------------------------------------------------------------
  # Redis — 生产配置
  # ---------------------------------------------------------------------------
  redis:
    image: redis:7-alpine
    container_name: tta-redis-prod
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD}
      --maxmemory 512mb
      --maxmemory-policy allkeys-lru
      --appendonly yes
    ports: []
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 15s
      timeout: 5s
      retries: 5
    restart: always
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 768M
    networks:
      - tta-net

  # ---------------------------------------------------------------------------
  # GPU 推理服务 — 生产配置
  # ---------------------------------------------------------------------------
  # 注意：生产环境 GPU 服务建议使用 Spot 实例或独立节点池部署
  # 以下 deploy 配置适用于 Docker Swarm；K8s 环境请使用 nodeSelector/tolerations
  gpu-service:
    build:
      context: .
      dockerfile: Dockerfile.gpu
    container_name: tta-gpu-service-prod
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "3"
    ports:
      - "8501:8501"
    env_file:
      - .env.prod
    environment:
      - ENV=production
      - INFERENCE_PORT=8501
    volumes:
      - ./models:/gpu_service/models:ro
      - ./tmp:/app/tmp
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8501/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    restart: always
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
          memory: 2G
        limits:
          cpus: "4.0"
          memory: 6G
    # Spot 实例配置（仅在云上 Swarm/K8s 场景生效）：
    #   在 AWS/GCP 上部署时，建议为 gpu-service 使用 Spot/G preemptible 实例
    #   配合 autoscaling group，节省推理服务空闲时的成本
    networks:
      - tta-net

  # ---------------------------------------------------------------------------
  # Nginx — 生产配置（HTTPS）
  # ---------------------------------------------------------------------------
  nginx:
    image: nginx:alpine
    container_name: tta-nginx-prod
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "3"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.prod.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./static:/usr/share/nginx/html/static:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - nginx-logs:/var/log/nginx
    depends_on:
      app:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: always
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 256M
    networks:
      - tta-net

volumes:
  pgdata:
    driver: local
  redisdata:
    driver: local
  nginx-logs:
    driver: local

networks:
  tta-net:
    driver: bridge
```

### 5.1 生产环境与开发环境差异

| 维度 | 开发环境 | 生产环境 |
|------|----------|----------|
| **启动方式** | uvicorn --reload | gunicorn 4 workers + uvicorn worker class |
| **代码挂载** | `./app:/app/app` 热重载 | 不挂载代码，仅挂载 logs/tmp |
| **数据库端口** | 暴露 5432 到宿主机 | 不暴露（仅内网） |
| **Redis 端口** | 暴露 6379 到宿主机 | 不暴露（仅内网） |
| **Redis 配置** | 基础 requirepass | + maxmemory 512mb + appendonly 持久化 |
| **Celery Worker** | concurrency=4 | concurrency=8 + max-tasks-per-child + time-limit |
| **健康检查** | db/redis | 全部服务 healthcheck |
| **重启策略** | unless-stopped | always |
| **资源限制** | 无 | 每服务 CPU/内存 limits + reservations |
| **Nginx** | HTTP only | HTTPS（挂载 SSL 证书目录） |
| **环境变量** | `.env` | `.env.prod` |

---

## 6. .env.example

环境变量模板，所有敏感配置通过环境变量注入，不硬编码到镜像或代码中。

```bash
# =============================================================================
# .env.example — 环境变量模板
# 复制为 .env（开发）或 .env.prod（生产）后填写真实值
# =============================================================================

# ---------- Application ----------
APP_NAME=TableTennisAnalysis
ENV=development
DEBUG=true
APP_HOST=0.0.0.0
APP_PORT=8000

# ---------- Database ----------
DATABASE_URL=postgresql+asyncpg://tta_user:tta_pass_dev@db:5432/tta
POSTGRES_DB=tta
POSTGRES_USER=tta_user
POSTGRES_PASSWORD=tta_pass_dev
# 数据库连接池配置
DB_POOL_SIZE=10        # 连接池大小
DB_MAX_OVERFLOW=20     # 最大溢出连接数
DB_POOL_RECYCLE=3600   # 连接回收周期（秒）

# ---------- Redis ----------
REDIS_PASSWORD=your-redis-password
REDIS_URL=redis://:your-redis-password@redis:6379/0

# ---------- JWT（强制必填，无默认值，缺失则应用拒绝启动）----------
JWT_SECRET_KEY=
JWT_REFRESH_SECRET_KEY=
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# ---------- WeChat Pay ----------
WECHAT_API_V3_KEY=
WECHAT_PRIVATE_KEY=
WECHAT_MCH_ID=
WECHAT_APP_ID=
WECHAT_NOTIFY_URL=

# ---------- OSS（阿里云对象存储）----------
OSS_ACCESS_KEY_ID=
OSS_ACCESS_KEY_SECRET=
OSS_BUCKET_NAME=
OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
OSS_CDN_DOMAIN=

# ---------- AI Inference ----------
INFERENCE_BASE_URL=http://gpu-service:8501
INFERENCE_TIMEOUT=300
INFERENCE_MODEL_VERSION=v1.0.0

# ---------- Celery ----------
CELERY_BROKER_URL=redis://:your-redis-password@redis:6379/1
CELERY_RESULT_BACKEND=redis://:your-redis-password@redis:6379/2
CELERY_TASK_TIME_LIMIT=3600
CELERY_TASK_SOFT_TIME_LIMIT=3000

# ---------- Logging ----------
LOG_LEVEL=INFO
LOG_DIR=/app/logs
# Docker 日志轮转
# docker-compose.yml / docker-compose.prod.yml 中 logging 配置：
# logging:
#   driver: json-file
#   options:
#     max-size: "50m"
#     max-file: "3"

# ---------- CORS ----------
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
```

### 6.1 环境变量安全规范

| 变量 | 必填 | 说明 |
|------|------|------|
| `JWT_SECRET_KEY` | ✅ 强制 | 无默认值，缺失时应用启动即抛异常退出 |
| `JWT_REFRESH_SECRET_KEY` | ✅ 强制 | 无默认值，同上 |
| `REDIS_PASSWORD` | ✅ 强制 | Redis 强制密码认证 |
| `DATABASE_URL` | ✅ 强制 | 生产环境必须使用独立密码 |
| `WECHAT_API_V3_KEY` | ⚠️ 生产必填 | 微信支付 V3 密钥 |
| `OSS_ACCESS_KEY_*` | ⚠️ 生产必填 | OSS 访问凭证 |
| `POSTGRES_PASSWORD` | ⚠️ 生产必填 | 生产环境必须修改默认密码 |

> **安全红线**：`.env` 和 `.env.prod` 必须加入 `.gitignore`，禁止提交到版本库。仅 `.env.example` 可提交。

### 6.2 数据库连接池配置

`.env` 中新增的 `DB_POOL_SIZE`、`DB_MAX_OVERFLOW`、`DB_POOL_RECYCLE` 环境变量在 SQLAlchemy engine 创建时使用：

```python
from sqlalchemy.ext.asyncio import create_async_engine
import os

engine = create_async_engine(
    os.getenv("DATABASE_URL"),
    pool_size=int(os.getenv("DB_POOL_SIZE", 10)),        # 连接池大小
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", 20)),  # 最大溢出连接数
    pool_recycle=int(os.getenv("DB_POOL_RECYCLE", 3600)), # 连接回收周期（秒），防止数据库端断开空闲连接
    echo=False,
)
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `pool_size` | 10 | 连接池常驻连接数，适用并发量 |
| `max_overflow` | 20 | 超出 pool_size 后允许的临时连接数 |
| `pool_recycle` | 3600 | 连接回收周期（秒），需小于数据库 `idle_timeout` |

---

## 7. nginx.conf

Nginx 反向代理配置，包含 HTTP 反向代理、WebSocket 支持、静态文件服务、安全 HTTP 头。

```nginx
# =============================================================================
# nginx/nginx.conf — Nginx 主配置
# 架构约束：§9.2 部署编排
# =============================================================================

worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
    multi_accept on;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # ---------- 日志格式（过滤 token 参数，防止泄露）----------
    log_format main '$remote_addr - $remote_user [$time_local] '
                    '"$request_method $uri" $status $body_bytes_sent '
                    '"$http_referer" "$http_user_agent" '
                    'rt=$request_time uct="$upstream_connect_time" '
                    'uht="$upstream_header_time" urt="$upstream_response_time"';
    # 注意：使用 $uri 而非 $request，避免将 query string 中的 token 记入日志

    access_log /var/log/nginx/access.log main;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    client_max_body_size 500m;  # 视频上传上限

    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css application/json application/javascript
               text/xml application/xml application/xml+rss text/javascript;

    # ---------- 上游服务 ----------
    upstream app_backend {
        server app:8000;
        keepalive 32;
    }

    upstream gpu_backend {
        server gpu-service:8501;
        keepalive 16;
    }

    # ---------- 安全 HTTP 头 ----------
    map $sent_http_content_type $security_headers {
        default "";
    }

    server {
        listen 80;
        server_name _;

        # 安全 HTTP 头
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-XSS-Protection "1; mode=block" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        add_header X-Permitted-Cross-Domain-Policies "none" always;

        # 健康检查端点（Nginx 自身）
        location /health {
            access_log off;
            return 200 '{"status":"ok"}';
            add_header Content-Type application/json;
        }

        # ---------- API 反向代理 ----------
        location /api/ {
            proxy_pass http://app_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            # 请求体大小（视频元数据等）
            client_max_body_size 100m;
            proxy_connect_timeout 10s;
            proxy_send_timeout 60s;
            proxy_read_timeout 120s;
        }

        # ---------- WebSocket 代理（实时通知、进度推送）----------
        location /ws/ {
            proxy_pass http://app_backend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            # WebSocket 长连接超时
            proxy_connect_timeout 10s;
            proxy_send_timeout 3600s;
            proxy_read_timeout 3600s;
        }

        # ---------- GPU 推理服务代理 ----------
        location /inference/ {
            proxy_pass http://gpu_backend/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

            # 推理请求可能较慢
            proxy_connect_timeout 10s;
            proxy_send_timeout 300s;
            proxy_read_timeout 300s;
        }

        # ---------- 静态文件 ----------
        location /static/ {
            alias /usr/share/nginx/html/static/;
            expires 30d;
            add_header Cache-Control "public, immutable";
            access_log off;
        }

        # ---------- 前端 SPA（可选）----------
        location / {
            root /usr/share/nginx/html;
            try_files $uri $uri/ /index.html;
            expires -1;
        }
    }
}
```

### 7.1 nginx.prod.conf（HTTPS 版本）

生产环境使用 HTTPS，以下是关键差异部分：

```nginx
# nginx/nginx.prod.conf — 生产环境（仅 server 块差异）

server {
    listen 80;
    server_name your-domain.com;
    # HTTP 强制跳转 HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL 证书
    ssl_certificate /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    # HSTS
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # 以下 location 块与开发环境相同
    # ... /api/、/ws/、/inference/、/static/、/ ...
}
```

---

## 8. 部署操作手册

### 8.1 开发环境启动

```bash
# 1. 复制环境变量模板
cp .env.example .env
# 编辑 .env，填写 JWT_SECRET_KEY、REDIS_PASSWORD 等必填项

# 2. 构建并启动所有服务
docker compose up -d --build

# 3. 查看服务状态
docker compose ps

# 4. 查看日志
docker compose logs -f app
docker compose logs -f celery-worker

# 5. 数据库迁移
docker compose exec app alembic upgrade head

# 6. 停止
docker compose down
```

### 8.2 生产环境部署

```bash
# 1. 准备生产环境变量
cp .env.example .env.prod
# 编辑 .env.prod，填写生产环境真实值（强密码）

# 2. 准备 SSL 证书
mkdir -p nginx/ssl
# 放置 fullchain.pem 和 privkey.pem

# 3. 构建并启动（使用生产覆盖配置）
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 4. 验证健康状态
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
curl https://your-domain.com/health

# 5. 滚动重启（代码更新时）
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build app celery-worker celery-beat
```

### 8.3 GPU 服务单独管理

```bash
# 仅启动 GPU 服务（推理节点独立部署时）
docker compose up -d gpu-service

# 查看 GPU 利用率
docker compose exec gpu-service nvidia-smi

# 仅重启 GPU 服务（模型更新后）
docker compose restart gpu-service
```

---

## 9. 容器资源规划

### 9.1 开发环境资源需求

| 容器 | CPU | 内存 | 备注 |
|------|-----|------|------|
| app | 0.5 | 512MB | 开发模式 |
| celery-worker | 0.5 | 512MB | concurrency=4 |
| celery-beat | 0.1 | 128MB | 调度器 |
| db | 0.5 | 512MB | PostgreSQL |
| redis | 0.2 | 128MB | 缓存 |
| gpu-service | 1.0 | 2GB | 需要 GPU |
| nginx | 0.1 | 64MB | 代理 |
| **合计** | ~3.0 | ~4GB | + GPU |

### 9.2 生产环境资源规划

| 容器 | CPU limit | 内存 limit | 备注 |
|------|-----------|-----------|------|
| app | 2.0 | 2GB | gunicorn 4 workers |
| celery-worker | 2.0 | 2GB | concurrency=8 |
| celery-beat | 0.2 | 256MB | 调度器 |
| db | 2.0 | 2GB | PostgreSQL 15 |
| redis | 1.0 | 768MB | maxmemory 512mb |
| gpu-service | 4.0 | 6GB | 推理 |
| nginx | 0.5 | 256MB | HTTPS |
| **合计** | ~11.7 | ~13GB | + GPU |

---

## 10. 与架构文档的对齐验证

| 架构约束 | 本切片实现 | 验证状态 |
|----------|-----------|----------|
| §2.3 Docker + Docker Compose | Dockerfile + docker-compose.yml | ✅ 已补齐 |
| §8 目录结构 | 镜像内 `/app` + `/gpu_service` 与架构目录一致 | ✅ |
| §9.2 部署编排 | 开发 + 生产两套 compose 编排 | ✅ |
| §9.2 容器化 | 7 个容器完整定义 | ✅ |
| 安全要求 | 非 root 用户、Redis 密码、JWT 强制、日志过滤 token | ✅ |
| GPU 推理独立 | Dockerfile.gpu 独立镜像 + 独立容器 | ✅ |

---

## 反幻觉约束

- [x] 本文档提供了完整的 Dockerfile + docker-compose.yml + docker-compose.prod.yml
- [x] 开发环境支持热重载（volume 挂载）
- [x] 生产环境使用 gunicorn 多 worker
- [x] PostgreSQL 使用 alpine 镜像减小体积
- [x] Redis 强制密码（requirepass）
- [x] GPU 服务使用 nvidia/cuda 基础镜像
- [x] Nginx 配置了安全 HTTP 头和 WebSocket 代理
- [x] 环境变量通过 .env 文件注入，不硬编码
