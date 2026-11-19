# -*- coding: utf-8 -*-
"""调试期登录辅助：一键取最新 SMS mock 验证码。

用法（Windows PowerShell / 项目根目录）:
    .venv\\Scripts\\python.exe scripts\\fetch_sms_code.py            # 取最新一条
    .venv\\Scripts\\python.exe scripts\\fetch_sms_code.py 13800001111  # 按手机号过滤

流程：真机小程序登录页输入手机号 → 点「获取验证码」→ 运行本脚本 →
将打印出的 6 位验证码填入小程序 → 点「登录」。
"""
import sys

import paramiko

VM_HOST = "192.168.40.147"
VM_USER = "root"
VM_PASS = "123456"
CONTAINER = "tta-api"


def main() -> int:
    phone = sys.argv[1] if len(sys.argv) > 1 else None
    grep_expr = "SMS mock mode"
    if phone:
        grep_expr = f"SMS mock mode: phone={phone}"

    cmd = (
        f"docker logs {CONTAINER} --since 10m 2>&1 "
        f"| grep '{grep_expr}' | tail -3"
    )

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(VM_HOST, username=VM_USER, password=VM_PASS, timeout=10)
    try:
        _, stdout, stderr = ssh.exec_command(cmd, timeout=15)
        out = stdout.read().decode("utf-8", errors="replace").strip()
    finally:
        ssh.close()

    if not out:
        print("最近 10 分钟无验证码记录。请先在小程序点「获取验证码」，再运行本脚本。")
        return 1

    print("最近验证码记录（时间倒序最后一条为最新）：")
    lines = [l for l in out.splitlines() if l.strip()]
    for line in lines:
        print("  " + line)
    latest = lines[-1]
    # 提取 code=xxxxxx
    idx = latest.find("code=")
    code = latest[idx + 5 : idx + 11] if idx >= 0 else "?"
    print()
    print(f"==> 最新验证码: {code}  （5 分钟内有效）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
