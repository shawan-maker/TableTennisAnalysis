# 02 — PG 15 + Redis 7 部署

> 适用场景：在虚拟机上部署 PostgreSQL 15 和 Redis 7 容器

## 方式一：脚本自动部署（推荐）

在本机执行以下脚本，通过 SSH 远程部署到虚拟机：

```bash
# 本机 PowerShell
cd D:\PyProject\TableTennisAnalysis
.venv\Scripts\python.exe docs\08部署手册\scripts\vm_deploy.py
```

脚本会自动完成：
1. SSH 连接虚拟机
2. 停止并清理所有现有容器
3. 在虚拟机创建 `/root/tta-dev/docker-compose.yml`
4. 拉取 Docker 镜像
5. 启动 PG + Redis 容器
6. 等待健康检查通过
7. 验证 PG 连接和 Redis PING

脚本参数在文件顶部定义，修改后可适配不同虚拟机：

```python
VM_HOST = "192.168.40.147"
VM_USER = "root"
VM_PASS = "123456"
```

## 方式二：手动部署

### 1. 在虚拟机创建目录

```bash
mkdir -p /root/tta-dev
cd /root/tta-dev
```

### 2. 创建 docker-compose.yml

将 `docs/08部署手册/scripts/docker-compose.vm.yml` 的内容复制到虚拟机的 `/root/tta-dev/docker-compose.yml`。

关键配置说明：

```yaml
services:
  db:
    image: postgres:15-alpine
    privileged: true          # CentOS 7 必须，否则 PG 无法写入数据卷
    environment:
      POSTGRES_DB: tta
      POSTGRES_USER: tta_user
      POSTGRES_PASSWORD: tta_pass_dev
    ports:
      - "5432:5432"
    volumes:
      - ./pgdata:/var/lib/postgresql/data    # 使用 bind mount
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tta_user -d tta"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass redis_dev_pass
    ports:
      - "6379:6379"
    volumes:
      - ./redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "redis_dev_pass", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
```

### 3. 创建数据目录

```bash
mkdir -p /root/tta-dev/pgdata /root/tta-dev/redisdata
chmod 777 /root/tta-dev/pgdata /root/tta-dev/redisdata
```

### 4. 拉取镜像

```bash
docker pull postgres:15-alpine
docker pull redis:7-alpine
```

### 5. 启动容器

```bash
cd /root/tta-dev
docker compose up -d
```

### 6. 等待健康检查

```bash
# 查看容器状态
docker compose ps

# 等待直到两个容器都显示 (healthy)
watch -n 2 'docker compose ps'
```

### 7. 验证

```bash
# PG 连接测试
docker exec tta-db-dev psql -U tta_user -d tta -c 'SELECT version();'

# Redis 连接测试
docker exec tta-redis-dev redis-cli -a redis_dev_pass ping
# 应输出 PONG
```

## 常见问题

### PG 容器不断 Restarting

**症状**：`docker ps` 显示 tta-db-dev 状态为 `Restarting (1)`

**根因**：CentOS 7 SELinux 阻止容器写入数据卷

**解决方案**：
1. 确认 SELinux 已设为 Permissive：`getenforce` → 应输出 `Permissive`
2. 确认 docker-compose.yml 中 PG 容器有 `privileged: true`
3. 删除旧数据目录重新初始化：
   ```bash
   docker compose down -v
   rm -rf /root/tta-dev/pgdata/*
   docker compose up -d
   ```

### 端口被占用

**症状**：容器启动失败，提示 `bind: address already in use`

**解决方案**：
```bash
# 查看占用端口的进程
ss -tlnp | grep -E '5432|6379'

# 停止占用端口的容器
docker stop $(docker ps -q)

# 或强制清理所有容器
docker rm -f $(docker ps -aq)
```

### 数据卷残留导致初始化失败

**症状**：PG 日志显示 `directory "/var/lib/postgresql/data" exists but is not empty`

**解决方案**：
```bash
docker compose down -v
rm -rf /root/tta-dev/pgdata/*
docker compose up -d
```

## 容器管理常用命令

```bash
# 查看状态
docker compose ps

# 查看日志
docker compose logs db
docker compose logs redis

# 重启
docker compose restart

# 停止
docker compose down

# 停止并删除数据（谨慎！）
docker compose down -v

# 进入 PG
docker exec -it tta-db-dev psql -U tta_user -d tta

# 进入 Redis
docker exec -it tta-redis-dev redis-cli -a redis_dev_pass
```
