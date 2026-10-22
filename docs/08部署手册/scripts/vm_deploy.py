#!/usr/bin/env python3
"""
vm_deploy.py — 远程部署 PostgreSQL 15 + Redis 7 到虚拟机

功能：
  1. SSH 连接虚拟机
  2. 检查环境（OS、Docker 版本、端口占用、磁盘/内存）
  3. 停止并清理所有现有 Docker 容器
  4. 设置 SELinux 为 Permissive（CentOS 7）
  5. 在虚拟机创建 docker-compose.yml（bind mount + privileged）
  6. 拉取镜像并启动容器
  7. 等待健康检查通过
  8. 验证 PG 连接和 Redis PING

使用方式：
  python vm_deploy.py

修改 VM_HOST / VM_USER / VM_PASS 以适配你的虚拟机环境。

依赖：
  pip install paramiko

依据：docs/08部署手册/01-VM环境准备.md + 02-PG-Redis部署.md
"""

import paramiko
import sys
import time

# ============================================================
# 虚拟机连接配置 — 修改这些值以适配你的环境
# ============================================================
VM_HOST = "192.168.40.147"
VM_USER = "root"
VM_PASS = "123456"

# Docker Compose 配置（部署到虚拟机 /root/tta-dev/）
COMPOSE_DIR = "/root/tta-dev"
COMPOSE_FILE = f"{COMPOSE_DIR}/docker-compose.yml"

# 数据库和 Redis 配置
PG_DB = "tta"
PG_USER = "tta_user"
PG_PASS = "tta_pass_dev"
REDIS_PASS = "redis_dev_pass"

# docker-compose.yml 内容
# 注意：privileged: true 是 CentOS 7 的必需配置
#       bind mount 避免 Docker named volume 的 SELinux 标签问题
DOCKER_COMPOSE = f"""\
services:
  db:
    image: postgres:15-alpine
    container_name: tta-db-dev
    privileged: true
    environment:
      POSTGRES_DB: {PG_DB}
      POSTGRES_USER: {PG_USER}
      POSTGRES_PASSWORD: {PG_PASS}
    ports:
      - "5432:5432"
    volumes:
      - ./pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U {PG_USER} -d {PG_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: tta-redis-dev
    command: redis-server --requirepass {REDIS_PASS}
    ports:
      - "6379:6379"
    volumes:
      - ./redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "{REDIS_PASS}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
"""


def run_cmd(ssh, cmd, timeout=300):
    """Execute a command over SSH and return (stdout, stderr, exit_code)."""
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    exit_code = stdout.channel.recv_exit_status()
    return out, err, exit_code


def step(num, title):
    """Print a step header."""
    print(f"\n[Step {num}] {title}")
    print("-" * 50)


def main():
    print("=" * 60)
    print(f"TTA Dev Environment Deployment")
    print(f"Target: {VM_USER}@{VM_HOST}")
    print("=" * 60)

    # ---- Connect ----
    print(f"\nConnecting to {VM_HOST} ...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(VM_HOST, port=22, username=VM_USER, password=VM_PASS, timeout=15)
        print("[OK] SSH connected.")
    except Exception as e:
        print(f"[FAIL] SSH connection failed: {e}")
        print("  Check: VM is running, SSH is enabled, credentials are correct.")
        sys.exit(1)

    # ---- Step 1: Inspect environment ----
    step(1, "Inspecting VM environment")

    out, _, _ = run_cmd(ssh, "cat /etc/os-release | head -3")
    print(f"  OS: {out.split(chr(10))[0]}")

    out, _, _ = run_cmd(ssh, "docker --version 2>/dev/null && docker compose version 2>/dev/null")
    print(f"  Docker: {out.replace(chr(10), ' | ')}")

    out, _, _ = run_cmd(ssh, "getenforce 2>/dev/null || echo 'N/A'")
    print(f"  SELinux: {out}")

    out, _, _ = run_cmd(ssh, "ss -tlnp | grep -E '5432|6379' || echo 'Ports 5432/6379 are free'")
    print(f"  Ports: {out}")

    out, _, _ = run_cmd(ssh, "df -h / | tail -1")
    print(f"  Disk: {out}")

    out, _, _ = run_cmd(ssh, "free -h | grep Mem")
    print(f"  Memory: {out}")

    # ---- Step 2: Stop and clean existing containers ----
    step(2, "Stopping and cleaning existing containers")

    out, _, _ = run_cmd(ssh, "docker stop $(docker ps -q) 2>/dev/null; docker rm -f $(docker ps -aq) 2>/dev/null; echo 'done'")
    print(f"  {out}")

    # ---- Step 3: Configure SELinux ----
    step(3, "Configuring SELinux")

    out, _, _ = run_cmd(ssh, "setenforce 0 2>&1 && getenforce")
    print(f"  Current: {out}")

    out, _, _ = run_cmd(ssh, "sed -i 's/^SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config 2>/dev/null; grep '^SELINUX=' /etc/selinux/config")
    print(f"  Permanent: {out}")

    # ---- Step 4: Create directory and compose file ----
    step(4, f"Creating {COMPOSE_DIR}/docker-compose.yml")

    run_cmd(ssh, f"mkdir -p {COMPOSE_DIR}/pgdata {COMPOSE_DIR}/redisdata")
    run_cmd(ssh, f"chmod 777 {COMPOSE_DIR}/pgdata {COMPOSE_DIR}/redisdata")

    sftp = ssh.open_sftp()
    with sftp.file(COMPOSE_FILE, "w") as f:
        f.write(DOCKER_COMPOSE)
    sftp.close()
    print(f"  Written to {COMPOSE_FILE}")

    # ---- Step 5: Pull images ----
    step(5, "Pulling Docker images")

    out, _, _ = run_cmd(ssh, "docker pull postgres:15-alpine 2>&1 | tail -3")
    print(f"  postgres:15-alpine: {out.split(chr(10))[-1]}")

    out, _, _ = run_cmd(ssh, "docker pull redis:7-alpine 2>&1 | tail -3")
    print(f"  redis:7-alpine: {out.split(chr(10))[-1]}")

    # ---- Step 6: Start containers ----
    step(6, "Starting containers")

    out, _, _ = run_cmd(ssh, f"cd {COMPOSE_DIR} && docker compose up -d 2>&1")
    print(f"  {out.replace(chr(10), ' | ')}")

    # ---- Step 7: Wait for health ----
    step(7, "Waiting for containers to become healthy")

    healthy = False
    for i in range(30):
        time.sleep(3)
        out, _, _ = run_cmd(ssh, "docker ps --filter name=tta --format '{{.Names}}|{{.Status}}'")
        status = out.replace('\n', ' | ')
        print(f"  [{i*3}s] {status}")

        if "healthy" in out and "tta-db-dev" in out and "tta-redis-dev" in out:
            print("  Both containers are healthy!")
            healthy = True
            break

        if "Restarting" in out:
            logs, _, _ = run_cmd(ssh, "docker logs tta-db-dev 2>&1 | tail -10")
            print(f"\n  PG Logs (error):\n{logs}\n")
            print("  [TIP] If SELinux error, ensure 'setenforce 0' and 'privileged: true'")
            break

    if not healthy:
        print("\n  [WARNING] Containers may not be healthy. Check logs above.")
        print("  Continuing with verification anyway...")

    # ---- Step 8: Verify ----
    step(8, "Final verification")

    print("\n  Container status:")
    out, _, _ = run_cmd(ssh, "docker ps --filter name=tta --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'")
    print(f"  {out}")

    print("\n  PG connection test:")
    out, _, _ = run_cmd(ssh, f"docker exec tta-db-dev psql -U {PG_USER} -d {PG_DB} -c 'SELECT version();' 2>&1")
    print(f"  {out}")

    print("\n  Redis connection test:")
    out, _, _ = run_cmd(ssh, f"docker exec tta-redis-dev redis-cli -a {REDIS_PASS} ping 2>&1")
    print(f"  {out}")

    print("\n  Listening ports:")
    out, _, _ = run_cmd(ssh, "ss -tlnp | grep -E '5432|6379'")
    print(f"  {out}")

    ssh.close()

    # ---- Summary ----
    print("\n" + "=" * 60)
    print("Deployment complete!")
    print("=" * 60)
    print(f"\n  VM:          {VM_HOST}")
    print(f"  PG:          {VM_HOST}:5432 (db={PG_DB}, user={PG_USER})")
    print(f"  Redis:       {VM_HOST}:6379 (password={REDIS_PASS})")
    print(f"\n  Next: Update .env to point to {VM_HOST}")
    print(f"        Run: python docs/08部署手册/scripts/test_connectivity.py")


if __name__ == "__main__":
    main()
