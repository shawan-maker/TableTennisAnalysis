#!/usr/bin/env python3
"""
vm_fullstack_deploy.py — 后端全栈容器化一键部署（api + worker + beat + migrate）

前置：
  1. 01/02 文档已完成：VM Docker 就绪，tta-db-dev / tta-redis-dev 运行且 healthy
  2. 本机在仓库根目录运行（git archive 打包 HEAD，未提交改动不上服务器）
  3. 本机 .env 可用（直接 SFTP 复用到 VM——两者主机地址 192.168.40.147 一致）

使用：
  .venv\\Scripts\\python.exe docs/08部署手册/scripts/vm_fullstack_deploy.py

步骤（幂等，可重复执行）：
  0 git archive 打包 → 1 VM 预检 → 2 SFTP 传输（代码包 + .env）
  → 3 解压 → 4 docker compose build → 5 迁移+种子 → 6 up -d 等 healthy
  → 7 firewalld 放行 8000 → 8 验证（/health、/docs、docker ps、日志尾部）

依据：docs/08部署手册/05-Docker全栈部署.md
"""

import os
import subprocess
import sys
import time

import paramiko

# ============================================================
# 配置
# ============================================================
VM_HOST = "192.168.40.147"
VM_USER = "root"
VM_PASS = "123456"

APP_DIR = "/root/tta-app"
LOCAL_TARBALL = os.path.join("tmp", "tta_app.tar.gz")
REMOTE_TARBALL = "/root/tta_app.tar.gz"
COMPOSE = "docker-compose.app.yml"


def run_cmd(ssh, cmd, timeout=300):
    """SSH 执行命令，返回 (stdout, stderr, exit_code)。"""
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    code = stdout.channel.recv_exit_status()
    return out, err, code


def step(num, title):
    print(f"\n[Step {num}] {title}")
    print("-" * 50)


def main():
    # ---- 前置校验：必须在仓库根目录 ----
    if not os.path.isdir("app") or not os.path.isfile("docker-compose.app.yml"):
        print("[FAIL] 请在仓库根目录运行本脚本（需 app/ 与 docker-compose.app.yml）")
        sys.exit(1)

    print("=" * 60)
    print("TTA Fullstack Deployment (backend containers)")
    print(f"Target: {VM_USER}@{VM_HOST}  ->  {APP_DIR}")
    print("=" * 60)

    # ---- Step 0: git archive HEAD ----
    step(0, "git archive HEAD（打包已提交内容）")
    os.makedirs("tmp", exist_ok=True)
    if os.path.exists(LOCAL_TARBALL):
        os.remove(LOCAL_TARBALL)
    r = subprocess.run(
        ["git", "archive", "--format=tar.gz", "-o", LOCAL_TARBALL, "HEAD"],
        capture_output=True,
    )
    if r.returncode != 0:
        print(f"[FAIL] git archive failed: {r.stderr.decode(errors='replace')}")
        sys.exit(1)
    size_mb = os.path.getsize(LOCAL_TARBALL) / 1024 / 1024
    print(f"[OK] {LOCAL_TARBALL} ({size_mb:.1f} MB)")

    # ---- 连接 ----
    print(f"\nConnecting to {VM_HOST} ...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(VM_HOST, port=22, username=VM_USER, password=VM_PASS, timeout=15)
        print("[OK] SSH connected.")
    except Exception as e:
        print(f"[FAIL] SSH connection failed: {e}")
        sys.exit(1)

    try:
        # ---- Step 1: 预检 ----
        step(1, "Preflight")
        out, _, _ = run_cmd(ssh, "docker --version && docker compose version")
        print(f"  Docker: {out.replace(chr(10), ' | ')}")

        out, _, _ = run_cmd(
            ssh, "docker ps --filter name=tta --format '{{.Names}}|{{.Status}}'"
        )
        print(f"  Containers:\n    {out.replace(chr(10), chr(10) + '    ')}")
        if "tta-db-dev" not in out or "tta-redis-dev" not in out:
            print("[FAIL] tta-db-dev / tta-redis-dev 未运行——先执行 01/02 文档部署")
            sys.exit(1)

        out, _, _ = run_cmd(ssh, "ss -tlnp | grep ':8000 ' || echo 'port 8000 free'")
        print(f"  Port 8000: {out}")
        if "port 8000 free" not in out:
            print("  [WARN] 8000 已被占用，up 时会冲突（如为旧 tta-api 请先 down）")

        out, _, _ = run_cmd(ssh, "df -h / | tail -1")
        print(f"  Disk: {out}")
        out, _, _ = run_cmd(ssh, "free -h | grep Mem")
        print(f"  Memory: {out}")
        out, _, _ = run_cmd(ssh, "firewall-cmd --state 2>/dev/null || echo inactive")
        print(f"  firewalld: {out}")

        # ---- Step 2: SFTP 传输 ----
        step(2, "Transfer (code + .env via SFTP)")
        sftp = ssh.open_sftp()
        sftp.put(LOCAL_TARBALL, REMOTE_TARBALL)
        print(f"  uploaded: {REMOTE_TARBALL}")
        with open(".env", "rb") as f:
            env_bytes = f.read()
        if not env_bytes:
            print("[FAIL] 本机 .env 为空——先按 03 文档配置")
            sys.exit(1)
        with sftp.file(f"{APP_DIR}/.env.uploading", "wb") as rf:
            rf.write(env_bytes)
        print(f"  uploaded: {APP_DIR}/.env.uploading (from local .env)")
        sftp.close()

        # ---- Step 3: 解压（旧目录整体替换，.env 移入新目录）----
        step(3, "Extract to /root/tta-app")
        run_cmd(
            ssh,
            f"mkdir -p {APP_DIR} && mv {APP_DIR}/.env.uploading /root/.env.keep "
            f"&& rm -rf {APP_DIR} && mkdir -p {APP_DIR} "
            f"&& tar -xzf {REMOTE_TARBALL} -C {APP_DIR} "
            f"&& mv /root/.env.keep {APP_DIR}/.env",
            timeout=120,
        )
        out, _, code = run_cmd(ssh, f"ls {APP_DIR} | head -8 && test -f {APP_DIR}/.env && echo ENV_OK")
        print(f"  {out}  (exit={code})")
        if "ENV_OK" not in out:
            print("[FAIL] 解压或 .env 就位失败")
            sys.exit(1)

        # ---- Step 4: build ----
        step(4, "docker compose build（首次 2~5 分钟）")
        out, err, code = run_cmd(
            ssh,
            f"cd {APP_DIR} && docker compose -f {COMPOSE} build 2>&1 | tail -6",
            timeout=900,
        )
        print(out or err)
        if code != 0:
            print(f"[FAIL] build 失败（exit={code}）——看上方输出；pip 慢可加 --build-arg PIP_INDEX_URL")
            sys.exit(1)

        # ---- Step 5: migrate + 种子（幂等）----
        step(5, "alembic upgrade head + seed scripts（幂等）")
        out, err, code = run_cmd(
            ssh,
            f"cd {APP_DIR} && docker compose -f {COMPOSE} run --rm migrate 2>&1 | tail -12",
            timeout=600,
        )
        print(out or err)
        if code != 0:
            print(f"[FAIL] migrate 失败（exit={code}）——检查 DATABASE_URL / db 容器状态")
            sys.exit(1)

        # ---- Step 6: up -d 并等 healthy ----
        step(6, "up -d (api/worker/beat)")
        out, _, _ = run_cmd(
            ssh, f"cd {APP_DIR} && docker compose -f {COMPOSE} up -d 2>&1", timeout=180
        )
        print(f"  {out.replace(chr(10), ' | ')}")
        healthy = False
        for i in range(12):
            time.sleep(5)
            out, _, _ = run_cmd(
                ssh, "docker ps --filter name=tta-api --format '{{.Status}}'"
            )
            print(f"  [{(i + 1) * 5}s] tta-api: {out}")
            if "healthy" in out:
                healthy = True
                break
        if not healthy:
            logs, _, _ = run_cmd(ssh, "docker logs tta-api 2>&1 | tail -15")
            print(f"  [WARN] 未在 60s 内 healthy，api 日志尾部：\n{logs}")

        # ---- Step 7: 防火墙 ----
        step(7, "firewalld: open 8000 (if active)")
        out, _, _ = run_cmd(ssh, "firewall-cmd --state 2>/dev/null || echo inactive")
        if "running" in out:
            run_cmd(ssh, "firewall-cmd --permanent --add-port=8000/tcp")
            out2, _, _ = run_cmd(ssh, "firewall-cmd --reload && firewall-cmd --list-ports")
            print(f"  opened: {out2}")
        else:
            print("  firewalld inactive，跳过（无入站过滤）")

        # ---- Step 8: 验证 ----
        step(8, "Verify")
        out, _, _ = run_cmd(ssh, "curl -s -m 5 http://127.0.0.1:8000/health || echo CURL_FAIL")
        print(f"  /health: {out}")
        out, _, _ = run_cmd(
            ssh,
            "curl -s -o /dev/null -w '%{http_code}' -m 5 http://127.0.0.1:8000/docs",
        )
        print(f"  /docs: HTTP {out}")
        out, _, _ = run_cmd(
            ssh,
            "docker ps --filter name=tta --format 'table {{.Names}}\\t{{.Status}}'",
        )
        print(f"  containers:\n{out}")
        logs, _, _ = run_cmd(ssh, "docker logs tta-api 2>&1 | tail -5")
        print(f"  api log tail:\n{logs}")

        print("\n" + "=" * 60)
        print("Deployment complete!")
        print("=" * 60)
        print(f"""
  API:        http://{VM_HOST}:8000/api/v1
  Swagger:    http://{VM_HOST}:8000/docs
  验证码:     ssh {VM_USER}@{VM_HOST} "docker logs tta-api 2>&1 | grep 'SMS mock mode' | tail -1"

  真机联调（详见 05-Docker全栈部署.md §5）：
  1) frontend/.env.development + .env.production 指向 http://{VM_HOST}:8000
  2) npm run build:weapp / dev:weapp 重新构建
  3) 微信开发者工具勾选「不校验合法域名」→ 预览二维码 → 手机扫码（同局域网）
""")
    finally:
        ssh.close()


if __name__ == "__main__":
    main()
