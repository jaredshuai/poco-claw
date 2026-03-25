# 自主调优系统设计

## 概述

借鉴 autoresearch 的实验循环模式，为 poco-claw 项目构建代码质量和测试覆盖率的自主调优系统。

## 核心理念

```
选择模块 → 建立 Baseline → 改进实验 → 验证 → 保留/回滚 → 记录 → 循环
```

## 目录结构

```
poco-claw/
├── .autoresearch/
│   ├── program.md           # Agent 指令文件
│   ├── results.tsv          # 实验结果记录
│   ├── baseline.json        # 各模块 baseline 指标
│   └── config.toml          # 调优配置（目标模块、优先级等）
├── backend/
│   └── tests/               # 测试文件（逐步扩充）
├── executor/
│   └── tests/
└── executor_manager/
    └── tests/
```

## 工具链

| 工具 | 用途 | 命令 |
|------|------|------|
| uv | 包管理 | `uv sync`, `uv run` |
| ruff | lint + format | `uv run ruff check`, `uv run ruff format` |
| ty | 类型检查 | `uv run ty check` |

## 指标体系

| 指标 | 命令 | 成功标准 |
|------|------|----------|
| Lint 错误 | `uv run ruff check backend/` | 数量减少 |
| 格式检查 | `uv run ruff format --check backend/` | 通过 |
| 类型错误 | `uv run ty check backend/` | 数量减少 |
| 测试覆盖率 | `uv run pytest --cov=app tests/` | 百分比提升 |
| 测试通过 | `uv run pytest tests/` | 全部通过 |

## Baseline 格式

```json
{
  "backend/services/session_service.py": {
    "lint_errors": 12,
    "type_errors": 5,
    "test_coverage": 45.2,
    "timestamp": "2026-03-25T10:00:00"
  }
}
```

## 分支策略

采用独立分支实验模式，与 autoresearch 一致：

```
main (master)
  │
  └── autoresearch/<tag>  ← 实验分支（如 autoresearch/mar25）
        │
        ├── commit A (keep)   ← 改善保留
        ├── commit B (keep)   ← 改善保留
        ├── (reset)           ← 变差回滚，不留 commit
        └── commit C (keep)   ← 改善保留
```

**分支命名**：`autoresearch/<date>`，如 `autoresearch/mar25`

**优势**：
- 主分支保持干净
- 实验历史完整保留
- 失败改动不留痕迹
- 可随时合并或丢弃整个分支

**合并时机**：
- 完成一个 Phase 后，可考虑合并到 main
- 或等整个调优周期结束后统一合并

## 实验循环流程

1. **创建分支** - `git checkout -b autoresearch/<tag>` 从 main 创建
2. **选择模块** - 按优先级选择下一个待调优模块
3. **记录 baseline** - 运行检查命令，记录当前指标
4. **分析改进** - Agent 分析代码，提出改进建议
5. **应用改进** - 修改代码或添加测试
6. **验证** - 重新运行检查
7. **决策**：
   - 改善 → `git commit`，记录 `keep`
   - 无改善/变差 → `git reset --hard HEAD`，记录 `discard`
8. **记录** - 写入 `results.tsv`
9. **循环** - 继续下一个改进或下一个模块

## 可修改文件

- `backend/app/services/*.py`
- `backend/app/repositories/*.py`
- `backend/app/api/v1/*.py`
- `backend/app/schemas/*.py`
- `backend/tests/*.py`
- `executor/app/**/*.py`
- `executor_manager/app/**/*.py`

## 不可修改文件

- `backend/app/models/*.py`（数据库模型结构）
- `backend/app/core/settings.py`（配置）
- `backend/alembic/**/*.py`（迁移文件）
- `pyproject.toml`（依赖配置）

## 调优目标

1. 消除所有 ruff lint 错误
2. 消除所有 ty 类型错误
3. 测试覆盖率提升到 80%+
4. 保持代码简洁，避免过度工程

## 约束

- 不破坏现有功能
- 测试必须通过
- 单次改动不超过 50 行（保持原子性）

## Results TSV 格式

```
timestamp	module	change_type	lint_before	lint_after	type_before	type_after	cov_before	cov_after	status	description
```

## 调优顺序

### Phase 1 - Backend 核心服务

1. `services/session_service.py`
2. `services/task_service.py`
3. `services/run_service.py`
4. `services/callback_service.py`
5. `repositories/session_repository.py`
6. `repositories/run_repository.py`

### Phase 2 - Backend 扩展

7. 其他 `services/*.py`
8. 其他 `repositories/*.py`
9. `api/v1/*.py`
10. `schemas/*.py`

### Phase 3 - Executor & Executor Manager

11. `executor/app/core/*.py`
12. `executor_manager/app/*.py`