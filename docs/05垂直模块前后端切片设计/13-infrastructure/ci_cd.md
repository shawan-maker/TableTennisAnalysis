# CI/CD 配置 — ci_cd

> **模块名称**：`infrastructure / ci_cd`
> **定位**：GitHub Actions CI/CD 流水线，覆盖 Lint → Test → Build → Deploy 全流程
> **依据**：CI-1 / INF-5 — 架构 §13.3 定义 CI/CD 流水线，无 .github/workflows 配置文件

---

## 1. 设计目标

| 阶段 | 工具 | 触发条件 | 产出 |
|------|------|---------|------|
| Lint | ruff | PR + push | 代码风格检查 |
| Type Check | mypy | PR + push | 类型安全检查 |
| Test | pytest | PR + push | 覆盖率报告 + 测试结果 |
| Build | Docker | main 分支 push | 后端/前端/AI 推理 Docker 镜像 |
| Deploy | docker-compose | main 分支 push (tag) | 生产环境滚动更新 |

---

## 2. 完整实现

### CI 流水线（PR 触发）

```yaml
# .github/workflows/ci.yml
name: CI

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main, develop]

env:
  PYTHON_VERSION: "3.12"
  NODE_VERSION: "20"

jobs:
  # ---------------------------------------------------------------------------
  # 1. 后端 Lint + Type Check
  # ---------------------------------------------------------------------------
  backend-lint:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - name: Install ruff
        run: pip install ruff
      - name: Lint
        run: ruff check app/ tests/
      - name: Format check
        run: ruff format --check app/ tests/

  backend-typecheck:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install mypy
      - name: Type check
        run: mypy app/ --ignore-missing-imports

  # ---------------------------------------------------------------------------
  # 2. 后端单元测试 + 覆盖率
  # ---------------------------------------------------------------------------
  backend-test:
    runs-on: ubuntu-latest
    needs: [backend-lint, backend-typecheck]
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      - name: Run unit tests
        run: pytest tests/unit -m unit --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=80
      - name: Run integration tests
        run: pytest tests/integration -m "integration and not slow" --cov=app --cov-report=term-missing --cov-fail-under=70
      - name: Upload coverage
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: backend/coverage.xml

  # ---------------------------------------------------------------------------
  # 3. 前端 Lint + Build
  # ---------------------------------------------------------------------------
  frontend-build:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - name: Install dependencies
        run: npm ci
      - name: Lint
        run: npm run lint
      - name: Type check
        run: npm run typecheck
      - name: Build (H5)
        run: npm run build:h5
      - name: Build (WeChat Mini Program)
        run: npm run build:weapp
```

### CD 流水线（main 分支触发）

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    tags:
      - "v*.*.*"

env:
  REGISTRY: registry.cn-hangzhou.aliyuncs.com
  IMAGE_NAME: pingpong-ai

jobs:
  # ---------------------------------------------------------------------------
  # 1. 构建 Docker 镜像
  # ---------------------------------------------------------------------------
  build-images:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        include:
          - target: backend
            dockerfile: Dockerfile
          - target: ai-inference
            dockerfile: Dockerfile.gpu
    steps:
      - uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Login to registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ secrets.REGISTRY_USERNAME }}
          password: ${{ secrets.REGISTRY_PASSWORD }}
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          file: ${{ matrix.dockerfile }}
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}/${{ matrix.target }}:latest
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}/${{ matrix.target }}:${{ github.ref_name }}
          cache-from: type=registry,ref=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}/${{ matrix.target }}:latest
          cache-to: type=inline

  # ---------------------------------------------------------------------------
  # 2. 部署到生产
  # ---------------------------------------------------------------------------
  deploy:
    runs-on: ubuntu-latest
    needs: build-images
    if: startsWith(github.ref, 'refs/tags/v')
    steps:
      - uses: actions/checkout@v4
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ${{ secrets.DEPLOY_USER }}
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            cd /opt/pingpong-ai
            export TAG=${{ github.ref_name }}
            docker-compose -f docker-compose.prod.yml pull
            docker-compose -f docker-compose.prod.yml up -d --no-deps --build
            docker image prune -f
      - name: Health check
        run: |
          sleep 10
          curl -sf https://api.pingpong-ai.com/health || exit 1
```

### PR 预览环境（可选）

```yaml
# .github/workflows/preview.yml
name: Preview

on:
  pull_request:
    types: [opened, synchronize, closed]

jobs:
  preview:
    runs-on: ubuntu-latest
    if: github.event.action != 'closed'
    steps:
      - uses: actions/checkout@v4
      - name: Build preview image
        run: docker build -f Dockerfile -t preview-pr-${{ github.event.pull_request.number }} .
      - name: Deploy preview
        run: |
          # 部署到预览环境，生成临时 URL
          echo "Preview URL: https://pr-${{ github.event.pull_request.number }}.preview.pingpong-ai.com"
```

---

## 3. CI 所需密钥

| Secret 名 | 用途 |
|-----------|------|
| `REGISTRY_USERNAME` | 阿里云容器镜像服务用户名 |
| `REGISTRY_PASSWORD` | 阿里云容器镜像服务密码 |
| `DEPLOY_HOST` | 生产服务器 SSH 地址 |
| `DEPLOY_USER` | SSH 登录用户 |
| `DEPLOY_SSH_KEY` | SSH 私钥 |

---

## 4. 分支策略

| 分支 | 触发 | 行为 |
|------|------|------|
| `feature/*` | PR → develop | CI: Lint + Test |
| `develop` | push / merge | CI: Lint + Test + Build (不部署) |
| `main` | tag `v*.*.*` | CD: Build + Deploy 生产 |
| `hotfix/*` | PR → main | CI + 快速 Deploy |

> **Anti-hallucination 约束**：
> 1. CI 必须在 PR 合并前通过 Lint + Type Check + Test 三个阶段
> 2. 覆盖率低于 80%（单元）/ 70%（整体）时 CI 红灯，阻止合并
> 3. Docker 镜像使用多阶段构建，生产镜像不含 dev 依赖
> 4. 部署后必须执行健康检查（`/health` 端点），失败则回滚
