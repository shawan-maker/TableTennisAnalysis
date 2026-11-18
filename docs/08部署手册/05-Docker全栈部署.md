# 05 - 单机 Docker 全栈部署（VM 192.168.40.147）

> 版本：v1.0 | 更新日期：2026-11-18 | 适用范围：后端 api + Celery worker/beat 容器化部署，供微信小程序真机预览 / 体验版联调

## 一、目标与架构

```
手机（微信扫「预览」二维码，与 VM 同一局域网）
    │  http://192.168.40.147:8000/api/v1   （勾选「不校验合法域名」后 http 可用）
    │  ws://192.168.40.147:8000/ws
    ▼
VM 192.168.40.147（CentOS 7 + Docker 26.1.4，SELinux permissive）
    ├── tta-api       :8000  FastAPI（REST + WS /ws）        ← 本文档部署
    ├── tta-worker    Celery worker（异步任务）               ← 本文档部署
    ├── tta-beat      Celery beat（定时任务调度）             ← 本文档部署
    ├── tta-db-dev    :5432  PostgreSQL 15（02 文档已部署）  ─┐ 数据落
    └── tta-redis-dev :6379  Redis 7（02 文档已部署）        ─┘ bind mount 保留
```

| 与既有文档的关系 | 说明 |
|---|---|
| [01-VM环境准备.md](01-VM环境准备.md) / [02-PG-Redis部署.md](02-PG-Redis部署.md) | 前置：VM + PG/Redis 已运行（本文档只新增后端容器） |
| [03-本机开发环境配置.md](03-本机开发环境配置.md) | 本机 Python 直跑模式（开发期主力）；本文档是全容器化形态，两者共用同一份 `.env`（主机地址一致，可直接 SFTP 复用） |

**当前阶段全部外联走 Mock，无需任何云资质即可真机体验**：

| 开关 | 状态 | 行为 |
|---|---|---|
| `SMS_MOCK` | true | 验证码不发短信，打到 `tta-api` 日志（见 §5.5） |
| `WECHAT_PAY_MOCK` | true | JSAPI 支付模拟成功，会员链路可完整体验 |
| `FILE_STORAGE_MOCK` | true | 视频上传走本地 mock 存储，分析流水线照常 |
| `AI_INFERENCE_MOCK` | true | AI 推理返回模拟结果，报告照常生成 |
| `DEBUG` | true | Celery `task_always_eager`：分析任务在 api 进程内同步执行（worker 已部署待命，切 false 后接管，见 §九） |

## 二、部署资产清单

| 文件 | 位置 | 职责 |
|---|---|---|
| `Dockerfile.backend` | 仓库根 | 后端镜像（python:3.11-slim + 依赖 + app/alembic/scripts） |
| `docker-compose.app.yml` | 仓库根 | api / worker / beat / migrate 四服务编排（host 网络） |
| `.dockerignore` | 仓库根 | 构建上下文瘦身 + `.env` 防入镜像 |
| `scripts/vm_fullstack_deploy.py` | `docs/08部署手册/scripts/` | 一键部署（打包 HEAD → SFTP → build → migrate → up → 防火墙 → 验证） |
| `.env` | 虚拟机 `/root/tta-app/.env` | **不入库**；部署脚本从本机 `.env` SFTP 注入（主机地址一致可直接复用） |

## 三、一键部署（推荐）

**本机仓库根目录**执行（Windows PowerShell）：

```powershell
.venv\Scripts\python.exe docs\08部署手册\scripts\vm_fullstack_deploy.py
```

脚本步骤（幂等，重复执行安全）：

| 步 | 动作 | 预计耗时 |
|---|---|---|
| 0 | 本机 `git archive HEAD` 打包（**未提交的改动不会上服务器**——先 commit） | 秒级 |
| 1 | VM 预检：Docker/Compose 版本、db/redis healthy、端口 8000、磁盘、firewalld | 秒级 |
| 2 | SFTP 传输代码包 + `.env`（密钥只在通道内，不落日志） | 数秒 |
| 3 | 解压到 `/root/tta-app`（旧目录整体替换） | 秒级 |
| 4 | `docker compose build`（pip 走清华源；二次构建命中缓存秒级） | 首次 2~5 分钟 |
| 5 | `run --rm migrate`：alembic 迁移 + 知识库/徽章种子（幂等） | ~1 分钟 |
| 6 | `up -d` 并等待 tta-api healthy | ~1 分钟 |
| 7 | firewalld 放行 8000（未启用则跳过） | 秒级 |
| 8 | 验证：/health、/docs、docker ps、api 日志尾部 | 秒级 |

部署完成后**本机**浏览器打开 `http://192.168.40.147:8000/docs` 应出现 Swagger UI——通了即整链就绪。

## 四、手动分步部署（脚本等价拆解）

```bash
# 4.0 预检（VM 上）
docker ps --filter name=tta --format 'table {{.Names}}\t{{.Status}}'   # db/redis 须 healthy
ss -tlnp | grep ':8000' || echo '8000 空闲'
df -h / | tail -1 && free -h | grep Mem

# 4.1 代码传送（本机）——脚本 Step 0/2 等价
git archive --format=tar.gz -o tmp\tta_app.tar.gz HEAD
#   再将 tta_app.tar.gz 与本机 .env SFTP 上传（.env → /root/tta-app/.env）

# 4.3 构建（VM）
cd /root/tta-app && docker compose -f docker-compose.app.yml build
#   pip 镜像源覆盖示例：docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

# 4.4 迁移 + 种子（VM，幂等可重复）
cd /root/tta-app && docker compose -f docker-compose.app.yml run --rm migrate

# 4.5 启动（VM）
cd /root/tta-app && docker compose -f docker-compose.app.yml up -d

# 4.6 防火墙（VM，firewalld 运行时才需要）
firewall-cmd --permanent --add-port=8000/tcp && firewall-cmd --reload

# 4.7 验证（VM 本地 + Windows 本机各一次）
curl -s http://127.0.0.1:8000/health          # VM 自身
curl -s http://192.168.40.147:8000/health     # Windows 本机（跨网段验证）
```

## 五、微信开发者工具与真机联调

### 5.1 AppID 现实约束（必须先处理）

| 现状 | 限制 | 处置 |
|---|---|---|
| `project.config.json` 为 `touristappid`（游客模式） | **不能真机预览、不能上传体验版**，仅模拟器可用 | 到 [mp.weixin.qq.com](https://mp.weixin.qq.com) **免费注册个人主体小程序**（身份证 + 手机号，约 5 分钟，无需备案/认证），把 `frontend/project.config.json` 的 `appid` 替换为真实值 |

> 个人 AppID 即可真机「预览」+ 上传「体验版」；不能用微信支付——本项目当前支付走 mock 路径，不受影响。

### 5.2 前端环境变量（编译期注入，改完必须重新构建）

`frontend/.env.development` **和** `.env.production` 都指向 VM（两个文件都改，避免 build 模式差异导致 QR 端点不一致）：

```ini
# .env.development / .env.production（联调期）
TARO_APP_API=http://192.168.40.147:8000/api/v1
TARO_APP_WS=ws://192.168.40.147:8000/ws
```

> 提审前把 `.env.production` 改回 `https://api.<备案域名>/api/v1`（wss 同理）。

### 5.3 开发者工具三处设置

1. **详情 → 本地设置**：勾选「不校验合法域名、web-view（业务域名）、TLS 版本以及 HTTPS 证书」（开发版/体验版的 http://、ws:// 局域网地址全靠它放行）
2. **重新构建**（env 是编译期变量，改完必须重编译）：`npm run dev:weapp`（watch）或 `npm run build:weapp`
3. **工具栏「预览」** → 生成二维码 → 手机微信扫码（手机与 VM 同一局域网）

### 5.4 体验版说明

真实 AppID 下可「上传」代码 → mp 后台「版本管理」设为体验版 → 分发体验版二维码。若体验版连不上 VM：手机端打开小程序 → 右上角胶囊 →「开发调试」打开。

### 5.5 验证码获取（SMS_MOCK）

```powershell
# 本机远程取码
ssh root@192.168.40.147 "docker logs tta-api 2>&1 | grep 'SMS mock mode' | tail -1"
# 输出形如：SMS mock mode: phone=138xxxx1234 code=482031
```

> 同一手机号 **60 秒防刷**（频繁请求 429，换号或等 1 分钟）；验证码 Redis 存储 5 分钟有效。

## 六、真机验收清单（对应 04-前端实施计划 §8.4 可本地验证项）

| # | 用例 | 操作 | 预期 | 服务端核对 |
|---|---|---|---|---|
| 1 | 验证码登录 | 输入手机号 → 获取验证码 → 按 §5.5 取码输入 | 登录成功，进入 onboarding 分步引导 | `docker logs tta-api` 登录态签发 |
| 2 | 档案编辑 | 填写握拍/打法/水平等 | 保存成功，档案完整度提升 | `docker exec tta-db-dev psql -U tta_user -d tta -c 'select id,display_name from users;'` |
| 3 | 实时记分 | 创建比赛 → 记分牌记分 | 分数/局分实时变化（WS 推送） | `docker logs tta-api` grep ws |
| 4 | 视频上传分析 | 上传任意 mp4 | queued → processing → 分析报告页可见（mock 推理，eager 模式秒级完成） | `docker logs tta-api` 流水线日志 |
| 5 | 训练建议/训练单 | 从分析报告进训练建议 → 完成训练单 | 积分 +5 Toast，重新评估生效 | `docker exec tta-db-dev psql -U tta_user -d tta -c 'select count(*) from badge_definition;'`（种子 6 徽章） |
| 6 | 游戏化 | 签到/连击等 | 积分流水 / 徽章解锁 | 同上 |
| 7 | 会员+支付 mock | 额度用尽 → 开通会员 → JSAPI 支付 | mock 模拟支付成功，权益刷新 | `docker exec tta-db-dev psql -U tta_user -d tta -c 'select order_no,status from payment_order order by id desc limit 3;'` |
| 8 | 通知中心 | 分析完成 / 支付成功后 | 通知列表出现记录 | `docker logs tta-api` grep notification |
| 9 | 注销冷静期 | 设置页申请注销 | 72h 冷静期横幅 + 可撤销 | `docker logs tta-api` grep deletion |

## 七、运维手册

```bash
# ---- 常用（VM /root/tta-app）----
docker compose -f docker-compose.app.yml ps             # 三容器状态（api 须 healthy）
docker logs tta-api -f --tail 50                        # api 日志（验证码也在这）
docker logs tta-worker -f --tail 50                     # worker 日志（DEBUG=false 时必看）
docker compose -f docker-compose.app.yml restart api    # 单服务重启
docker compose -f docker-compose.app.yml down           # 停止后端三容器（PG/Redis 不受影响）

# ---- 代码更新流程（本机：commit + push 之后重跑，幂等）----
.venv\Scripts\python.exe docs\08部署手册\scripts\vm_fullstack_deploy.py
# 依赖未变时 build 命中缓存，全程约 2~3 分钟；migrate 幂等；数据保留

# ---- 数据备份 ----
docker exec tta-db-dev pg_dump -U tta_user tta > /root/backup_$(date +%F).sql

# ---- 回滚 ----
cd /root/tta-app && docker compose -f docker-compose.app.yml down
# 仅停后端；pgdata/redisdata 在 /root/tta-dev 下完好
```

## 八、故障排查

| 症状 | 原因 | 处置 |
|---|---|---|
| 手机请求超时/连不上 | ① 手机不在 VM 同一网段 ② firewalld 未放行 ③ 未勾选「不校验合法域名」④ 改了 env 没重新构建 | `firewall-cmd --list-ports` 查 8000；重新 build:weapp 后再预览 |
| 验证码找不到 | SMS_MOCK 打日志不弹窗 | `docker logs tta-api 2>&1 \| grep "SMS mock mode" \| tail -1` |
| 频繁获取验证码 429 | 60 秒防刷 | 换手机号或等 1 分钟 |
| 分析任务一直 queued | 切了 `DEBUG=false` 但 worker 未就绪 | `docker logs tta-worker -f`；确认 `up -d` 全量启动 |
| build 卡在 pip 下载 | VM 出网慢 | `--build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/` |
| build 卡在 apt（tzdata） | debian 源不可达 | 重试；或注释掉 Dockerfile 的 apt 段（牺牲 beat 时区精度） |
| beat 报 schedule 文件权限 | 工作区只读 | 已用 `--schedule=/tmp/celerybeat-schedule` 规避，确认未改动 |
| VM 内 /health 通、Windows 不通 | firewalld | `firewall-cmd --permanent --add-port=8000/tcp && firewall-cmd --reload` |
| 预览能连、体验版连不上 | 体验版未开调试 | 手机端胶囊菜单 →「开发调试」 |
| 工具栏没有「预览」按钮 | touristappid 游客模式 | 按 §5.1 注册免费个人 AppID 并替换 |
| 磁盘不足 | 镜像/日志膨胀 | `df -h`；`docker system prune`（bind mount 的 pgdata/redisdata 不受影响） |

## 九、切换生产形态（资质就绪后）

| 开关（.env） | 换真值前置 |
|---|---|
| `DEBUG=false` | 无（worker/beat 已部署，随时接管异步链路） |
| `SMS_MOCK=false` | 阿里云短信签名/模板 + AK |
| `WECHAT_PAY_MOCK=false` | 商户号 + APIv3 密钥 + 证书 + 备案域名 notify_url（合法域名 TLS 依赖备案） |
| `FILE_STORAGE_MOCK=false` | 阿里云 OSS Bucket + RAM 子账号 AK + STS + uploadFile 合法域名 |
| `AI_INFERENCE_MOCK=false` | 推理服务 `INFERENCE_BASE_URL` 可达 |
| `.env.production` 端点 | 备案域名 + HTTPS 证书 + 小程序后台三类合法域名配置（request/uploadFile/socket） |

## 十、验证记录

> 2026-11-18 首次部署实测记录见本文件同批次提交说明（commit 含「单机 Docker 全栈部署」）。健康基线：`GET /health` 200、Swagger `/docs` 可达、`docker ps` 三容器 Up（api healthy）、Windows→VM:8000 跨网段连通。
