# Pytest 测试配置 — pytest_config

> **模块名称**：`infrastructure / pytest_config`
> **定位**：全局 pytest 配置，定义覆盖率阈值、异步模式、测试发现规则
> **依据**：TE-1 — 架构 §13.3 定义测试覆盖率 ≥ 70%，切片未配置 pytest.ini 或 coverage 配置

---

## 1. 设计目标

| 目标 | 说明 |
|------|------|
| 覆盖率门控 | 核心模块行覆盖率 ≥ 80%，整体 ≥ 70%，CI 中低于阈值则失败 |
| 异步支持 | `pytest-asyncio` 自动识别 async 测试函数 |
| 测试发现 | 自动发现 `tests/unit/` 和 `tests/integration/` 下的 `test_*.py` |
| 快照隔离 | 每个测试独立数据库会话 + Redis mock，互不污染 |
| 失败快跑 | `--ff` 优先运行上次失败的测试，加速迭代 |

---

## 2. 完整实现

### pyproject.toml（推荐）

```toml
# pyproject.toml

[tool.pytest.ini_options]
# 测试发现
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]

# 异步支持
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"

# 标记
markers = [
    "unit: 单元测试（Service 层逻辑，无外部依赖）",
    "integration: 集成测试（API 端点 + 内存数据库）",
    "slow: 耗时较长的测试（AI 推理模拟等）",
    "gpu: 需要 GPU 的测试（CI 中跳过）",
]

# 输出
addopts = [
    "-v",
    "--tb=short",
    "--strict-markers",
    "--color=yes",
    "-p", "no:cacheprovider",
]
```

### pytest.ini（替代方案）

```ini
# pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
asyncio_default_fixture_loop_scope = session
markers =
    unit: 单元测试（Service 层逻辑，无外部依赖）
    integration: 集成测试（API 端点 + 内存数据库）
    slow: 耗时较长的测试
    gpu: 需要 GPU 的测试（CI 中跳过）
addopts = -v --tb=short --strict-markers --color=yes
```

### 覆盖率配置

```ini
# .coveragerc
[run]
source = app
omit =
    app/__init__.py
    app/main.py
    app/core/config.py
    */migrations/*
    */tests/*

[report]
show_missing = True
skip_covered = False
precision = 2
exclude_lines =
    pragma: no cover
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:
    @overload

[html]
directory = htmlcov
```

### tox.ini（可选，多环境测试）

```ini
# tox.ini
[tox]
envlist = py311,lint,typecheck
isolated_build = True

[testenv]
deps =
    -r requirements.txt
    -r requirements-dev.txt
commands =
    pytest tests/unit -m unit --cov=app --cov-report=term-missing --cov-fail-under=80
    pytest tests/integration -m integration --cov=app --cov-report=term-missing --cov-fail-under=70

[testenv:lint]
deps = ruff
commands = ruff check app/ tests/

[testenv:typecheck]
deps = mypy
commands = mypy app/ --ignore-missing-imports
```

---

## 3. 测试目录结构

```
backend/
├── tests/
│   ├── conftest.py              # 共享 fixture（见 conftest.py.md）
│   ├── unit/
│   │   ├── test_auth_service.py
│   │   ├── test_user_service.py
│   │   ├── test_video_analysis_service.py
│   │   ├── test_scoring_service.py
│   │   ├── test_match_data_service.py
│   │   ├── test_dashboard_service.py
│   │   ├── test_training_advice_service.py
│   │   ├── test_progress_analysis_service.py
│   │   ├── test_gamification_service.py
│   │   ├── test_membership_service.py
│   │   ├── test_payment_service.py
│   │   └── test_notification_service.py
│   ├── integration/
│   │   ├── test_auth_api.py
│   │   ├── test_user_api.py
│   │   ├── test_video_analysis_api.py
│   │   ├── test_scoring_api.py
│   │   ├── test_match_data_api.py
│   │   ├── test_membership_api.py
│   │   └── test_payment_api.py
│   └── conftest_integration.py  # 集成测试专用 fixture
├── pyproject.toml
├── .coveragerc
└── pytest.ini
```

---

## 4. 运行命令

```bash
# 运行全部测试（含覆盖率报告）
pytest --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=70

# 仅单元测试
pytest tests/unit -m unit --cov=app --cov-report=term-missing --cov-fail-under=80

# 仅集成测试
pytest tests/integration -m integration

# 跳过 GPU 测试（CI 环境）
pytest -m "not gpu and not slow"

# 优先运行上次失败的测试
pytest --ff

# 并行运行（需 pytest-xdist）
pytest -n auto -m "not gpu"

# 生成 HTML 覆盖率报告
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

---

## 5. CI 覆盖率门控规则

| 测试层 | 覆盖目标 | CI 门控 |
|--------|---------|---------|
| 单元测试（unit/） | ≥ 80% | `--cov-fail-under=80` 失败则 CI 红 |
| 集成测试（integration/） | ≥ 70% | `--cov-fail-under=70` 失败则 CI 红 |
| 整体覆盖率 | ≥ 70% | 合并 unit + integration 后检查 |

> **Anti-hallucination 约束**：
> 1. 测试覆盖率仅统计 `app/` 目录，不含 `migrations/` 和 `tests/`
> 2. `pragma: no cover` 标记需在 code review 中审核，不得滥用
> 3. `asyncio_mode = auto` 意味着所有 async def test_ 函数自动识别为异步测试
> 4. GPU 相关测试标记 `@pytest.mark.gpu`，CI 环境通过 `-m "not gpu"` 跳过
