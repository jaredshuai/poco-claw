# Autoresearch Tuning 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 poco-claw 项目构建自主代码质量和测试覆盖率调优系统，实现实验循环自动化。

**Architecture:** 基于 autoresearch 模式，使用 uv + ruff + ty 工具链，在独立分支上进行实验循环：建立 baseline → 改进 → 验证 → 保留/回滚 → 记录。

**Tech Stack:** Python 3.12+, uv, ruff, ty, pytest, pytest-cov

---

## 文件结构

```
.autoresearch/
├── program.md           # Agent 指令 (已创建)
├── config.toml          # 模块优先级配置 (已创建)
├── baseline.json        # Baseline 指标 (需初始化)
├── results.tsv          # 实验结果 (已创建表头)
└── run.py               # 实验循环脚本 (新建)
```

---

## Task 1: 环境准备与工具验证

**Files:**
- Verify: `backend/pyproject.toml`
- Modify: `backend/pyproject.toml` (add pytest-cov)

- [ ] **Step 1: 检查 pytest 和 pytest-cov 是否已安装**

```bash
cd E:/codespace/poco-claw/backend && uv run pytest --version
```

Expected: 显示 pytest 版本

- [ ] **Step 2: 如果缺少 pytest-cov，添加依赖**

```bash
cd E:/codespace/poco-claw/backend && uv add pytest-cov --dev
```

Expected: 成功添加 pytest-cov

- [ ] **Step 3: 验证工具链全部可用**

```bash
cd E:/codespace/poco-claw && uv run ruff --version && ty --version
```

Expected: ruff 0.15.7+, ty 0.0.25+

---

## Task 2: 创建实验循环脚本

**Files:**
- Create: `.autoresearch/run.py`

- [ ] **Step 1: 创建 run.py 实验脚本**

```python
#!/usr/bin/env python3
"""
Autoresearch Tuning - 实验循环脚本
运行代码质量检查并记录结果
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
AUTOSEARCH_DIR = PROJECT_ROOT / ".autoresearch"
BASELINE_FILE = AUTOSEARCH_DIR / "baseline.json"
RESULTS_FILE = AUTOSEARCH_DIR / "results.tsv"


def run_command(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    """Run a command and return (exit_code, output)."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd or PROJECT_ROOT,
    )
    return result.returncode, result.stdout + result.stderr


def count_ruff_errors(path: str) -> int:
    """Count ruff lint errors for a path."""
    code, output = run_command(["uv", "run", "ruff", "check", path, "--output-format=json"])
    if code == 0:
        return 0
    try:
        errors = json.loads(output)
        return len(errors) if isinstance(errors, list) else 0
    except json.JSONDecodeError:
        # Fallback: count lines with "error"
        return sum(1 for line in output.split("\n") if "error" in line.lower())


def count_ty_errors(path: str) -> int:
    """Count ty type errors for a path."""
    code, output = run_command(["ty", "check", path])
    if code == 0:
        return 0
    # Count error lines in output
    return sum(1 for line in output.split("\n") if "error" in line.lower())


def get_test_coverage(module_path: str) -> float:
    """Get test coverage percentage for a module."""
    backend_dir = PROJECT_ROOT / "backend"
    code, output = run_command(
        ["uv", "run", "pytest", "--cov=app", "--cov-report=term-missing", "tests/"],
        cwd=backend_dir,
    )
    # Parse coverage from output
    for line in output.split("\n"):
        if "TOTAL" in line:
            parts = line.split()
            for part in parts:
                if "%" in part:
                    return float(part.rstrip("%"))
    return 0.0


def load_baseline() -> dict:
    """Load baseline metrics from file."""
    if BASELINE_FILE.exists():
        return json.loads(BASELINE_FILE.read_text())
    return {}


def save_baseline(baseline: dict) -> None:
    """Save baseline metrics to file."""
    BASELINE_FILE.write_text(json.dumps(baseline, indent=2))


def record_result(
    module: str,
    change_type: str,
    lint_before: int,
    lint_after: int,
    type_before: int,
    type_after: int,
    cov_before: float,
    cov_after: float,
    status: str,
    description: str,
) -> None:
    """Append experiment result to TSV file."""
    timestamp = datetime.now().isoformat(timespec="seconds")
    line = f"{timestamp}\t{module}\t{change_type}\t{lint_before}\t{lint_after}\t{type_before}\t{type_after}\t{cov_before:.1f}\t{cov_after:.1f}\t{status}\t{description}\n"
    with RESULTS_FILE.open("a") as f:
        f.write(line)


def measure_module(module_path: str) -> dict:
    """Measure all metrics for a module."""
    full_path = PROJECT_ROOT / module_path
    if not full_path.exists():
        print(f"Module not found: {module_path}")
        return {}

    return {
        "lint_errors": count_ruff_errors(module_path),
        "type_errors": count_ty_errors(module_path),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python run.py <command> [args]")
        print("Commands:")
        print("  baseline <module>  - Measure and save baseline for module")
        print("  measure <module>   - Measure current metrics for module")
        print("  compare <module>   - Compare current vs baseline")
        return 1

    command = sys.argv[1]

    if command == "baseline":
        if len(sys.argv) < 3:
            print("Usage: python run.py baseline <module>")
            return 1
        module = sys.argv[2]
        metrics = measure_module(module)
        if metrics:
            baseline = load_baseline()
            baseline[module] = metrics
            save_baseline(baseline)
            print(f"Baseline saved for {module}:")
            print(f"  lint_errors: {metrics['lint_errors']}")
            print(f"  type_errors: {metrics['type_errors']}")
        return 0

    elif command == "measure":
        if len(sys.argv) < 3:
            print("Usage: python run.py measure <module>")
            return 1
        module = sys.argv[2]
        metrics = measure_module(module)
        if metrics:
            print(f"Current metrics for {module}:")
            print(f"  lint_errors: {metrics['lint_errors']}")
            print(f"  type_errors: {metrics['type_errors']}")
        return 0

    elif command == "compare":
        if len(sys.argv) < 3:
            print("Usage: python run.py compare <module>")
            return 1
        module = sys.argv[2]
        baseline = load_baseline()
        if module not in baseline:
            print(f"No baseline found for {module}")
            return 1
        current = measure_module(module)
        base = baseline[module]
        print(f"Comparison for {module}:")
        print(f"  lint_errors: {base['lint_errors']} -> {current['lint_errors']} ({current['lint_errors'] - base['lint_errors']:+d})")
        print(f"  type_errors: {base['type_errors']} -> {current['type_errors']} ({current['type_errors'] - base['type_errors']:+d})")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 测试脚本基本功能**

```bash
cd E:/codespace/poco-claw && python .autoresearch/run.py measure backend/app/services/session_service.py
```

Expected: 输出当前 lint/type 错误数

---

## Task 3: 第一个实验 - 建立 Baseline

**Files:**
- Measure: `backend/app/services/session_service.py`
- Update: `.autoresearch/baseline.json`

- [ ] **Step 1: 对 session_service.py 建立 baseline**

```bash
cd E:/codespace/poco-claw && python .autoresearch/run.py baseline backend/app/services/session_service.py
```

Expected: baseline.json 更新，显示 lint/type 错误数

- [ ] **Step 2: 查看 baseline.json 确认记录正确**

```bash
cat E:/codespace/poco-claw/.autoresearch/baseline.json
```

Expected: JSON 包含 session_service.py 的指标

---

## Task 4: 第一个改进实验

**Files:**
- Modify: `backend/app/services/session_service.py`
- Update: `.autoresearch/results.tsv`

- [ ] **Step 1: 运行 ruff check 查看具体错误**

```bash
cd E:/codespace/poco-claw && uv run ruff check backend/app/services/session_service.py
```

Expected: 显示所有 lint 错误详情

- [ ] **Step 2: 使用 ruff 自动修复可修复的错误**

```bash
cd E:/codespace/poco-claw && uv run ruff check backend/app/services/session_service.py --fix
```

Expected: 自动修复部分错误

- [ ] **Step 3: 比较改进效果**

```bash
cd E:/codespace/poco-claw && python .autoresearch/run.py compare backend/app/services/session_service.py
```

Expected: 显示 lint 错误减少量

- [ ] **Step 4: 如果有改善，提交 commit**

```bash
cd E:/codespace/poco-claw && git add backend/app/services/session_service.py && git commit -m "fix(lint): auto-fix lint errors in session_service"
```

Expected: 成功提交

- [ ] **Step 5: 记录结果到 results.tsv**

```bash
# 手动或通过脚本记录结果
```

---

## Task 5: 类型检查实验

**Files:**
- Modify: `backend/app/services/session_service.py`

- [ ] **Step 1: 运行 ty check 查看类型错误**

```bash
cd E:/codespace/poco-claw && ty check backend/app/services/session_service.py
```

Expected: 显示所有类型错误

- [ ] **Step 2: 分析类型错误，制定修复策略**

根据 ty 输出的错误，确定需要添加的类型注解

- [ ] **Step 3: 应用类型注解修复**

手动或自动添加类型注解

- [ ] **Step 4: 验证类型错误减少**

```bash
cd E:/codespace/poco-claw && ty check backend/app/services/session_service.py
```

Expected: 类型错误减少

- [ ] **Step 5: 如果改善，提交 commit**

```bash
cd E:/codespace/poco-claw && git add backend/app/services/session_service.py && git commit -m "fix(types): add type annotations to session_service"
```

---

## Task 6: 建立持续实验模式

**Files:**
- Modify: `.autoresearch/program.md` (添加执行细节)

- [ ] **Step 1: 总结第一个实验的经验**

记录：
- 每个 lint 修复平均耗时
- 每个类型修复平均耗时
- 需要注意的陷阱

- [ ] **Step 2: 更新 program.md 添加执行细节**

补充具体的命令行示例和注意事项

- [ ] **Step 3: 提交实验框架**

```bash
cd E:/codespace/poco-claw && git add .autoresearch/ && git commit -m "feat: add autoresearch tuning framework"
```

---

## 后续迭代（按 config.toml 优先级）

完成 Task 1-6 后，按以下顺序继续：

1. `backend/app/services/task_service.py`
2. `backend/app/services/run_service.py`
3. `backend/app/services/callback_service.py`
4. `backend/app/repositories/session_repository.py`
5. `backend/app/repositories/run_repository.py`

每个模块重复：
- 建立 baseline
- Lint 修复实验
- 类型修复实验
- 记录结果