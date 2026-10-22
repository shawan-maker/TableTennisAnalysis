# 部署手册 — 乒乓智能分析平台

> 版本：v1.0 | 更新日期：2026-10-22 | 适用范围：S1+ 后端开发环境

## 架构概览

```
本机 Windows (Python 3.11+ .venv)
    │
    ├── uvicorn :8000 → FastAPI 应用
    │
    ├── asyncpg :5432 ──────→ PostgreSQL 15 (tta-db-dev)
    │
    └── redis   :6379 ──────→ Redis 7 (tta-redis-dev)
                                  │
                          VM 192.168.40.147
                          CentOS 7 + Docker 26.1.4
                          SELinux: permissive
```

## 文档目录

| 文档 | 内容 | 适用场景 |
|------|------|----------|
| [01-VM环境准备.md](01-VM环境准备.md) | 虚拟机 OS、Docker 安装、SELinux 配置 | 新虚拟机初始化 |
| [02-PG-Redis部署.md](02-PG-Redis部署.md) | Docker Compose 部署 PG 15 + Redis 7 | 数据库/缓存部署 |
| [03-本机开发环境配置.md](03-本机开发环境配置.md) | Python venv、依赖安装、.env 配置 | 本机开发环境搭建 |
| [04-验证与测试.md](04-验证与测试.md) | 连接验证、uvicorn、Alembic、pytest | 部署后验证 |

## 脚本目录

| 脚本 | 用途 | 运行位置 |
|------|------|----------|
| [scripts/vm_deploy.py](scripts/vm_deploy.py) | 远程部署 PG+Redis 到虚拟机 | 本机（SSH 远程执行） |
| [scripts/test_connectivity.py](scripts/test_connectivity.py) | 测试本机到虚拟机的 PG/Redis 连接 | 本机 |
| [scripts/verify_db.py](scripts/verify_db.py) | 验证数据库表和索引 | 本机 |
| [scripts/docker-compose.vm.yml](scripts/docker-compose.vm.yml) | 虚拟机上的 Docker Compose 配置 | 虚拟机 /root/tta-dev/ |

## 快速部署（已有虚拟机）

```bash
# 1. 本机执行：远程部署 PG+Redis
python docs/08部署手册/scripts/vm_deploy.py

# 2. 本机执行：验证连接
python docs/08部署手册/scripts/test_connectivity.py

# 3. 本机执行：生成迁移并测试
# （详见 04-验证与测试.md）
```

## 环境要求

| 组件 | 版本 | 备注 |
|------|------|------|
| Python | 3.11+ | 本机开发用 |
| Docker | 26.0+ | 虚拟机运行 PG+Redis |
| Docker Compose | v2.27+ | 虚拟机编排 |
| PostgreSQL | 15-alpine | 数据库 |
| Redis | 7-alpine | 缓存 + Celery Broker |
| VMware | 任意版本 | 虚拟化平台 |
| Linux | CentOS 7 / Ubuntu 22.04 | 虚拟机 OS |
