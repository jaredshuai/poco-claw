# Batch 4: 缺口修补 + 前端类型闭环

## Status（闭环 — 2026-04-04）

| 项                         | 状态     | 说明                                                                                                                       |
| -------------------------- | -------- | -------------------------------------------------------------------------------------------------------------------------- |
| Step 1 前端类型            | **完成** | `ExecutionSettings` 等定义在 `frontend/features/settings/types.ts`（与初稿 `types/index.ts` 不同，模块解析为同名 `types`） |
| Step 2 Permissions API     | **完成** | `GET/PATCH .../execution-settings/permissions` 已实现                                                                      |
| Step 3 MCP builder（可选） | **完成** | `executor/app/core/mcp_config.py` 已落地并与 engine 集成                                                                   |
| 本地验证                   | **通过** | `pnpm tsc --noEmit`；backend `test_execution_settings_service`；executor 全量 pytest                                       |
| 远端 CI（抽样）            | **通过** | `main` 上 Prettier、Markdownlint、GitLeaks 等近期 run 为 `success`                                                         |

下方「交叉验证」表保留为**当时扫描快照**；以本表为当前事实来源。

---

## Context

**问题**：Batch 1-3 核心功能已全部完成并提交。三路并行扫描（Claude + Gemini + Qwen）发现若干残留缺口，其中两个确认需要修复。

**目标**：修补真实缺口，确保 Execution Settings 前后端闭环。

---

## 三方交叉验证结论

| 缺口              | Gemini 判断 | Qwen 判断 | Claude 验证                                      | 结论         |
| ----------------- | ----------- | --------- | ------------------------------------------------ | ------------ |
| Git 错误类缺失    | ❌ 缺失     | ❌ 缺失   | ✅ 已存在 (`github.py:23-29`, `gitlab.py:24-30`) | **无需修复** |
| i18n 翻译键缺失   | ❌ 缺失     | —         | ✅ 已存在 (`translation.json:1593-1605`)         | **无需修复** |
| Frontend 类型定义 | ❌ 缺失     | ❌ 缺失   | ❌ 确认缺失                                      | **需修复**   |
| Permissions API   | ❌ 缺失     | ❌ 缺失   | ❌ 确认缺失                                      | **需修复**   |
| Engine MCP TODO   | ⚠️ 需重构   | ⚠️ 需重构 | ⚠️ 非关键，`engine.py:596`                       | **可选改进** |

---

## 实现范围

### Step 1: Frontend ExecutionSettings 类型定义

**问题**：`execution-settings-tab.tsx:23` 导入 `ExecutionSettings` from `@/features/settings/types`，但该文件/目录不存在。

**文件**：`frontend/features/settings/types/index.ts`（新建）

**实现**：

```typescript
// frontend/features/settings/types/index.ts
export interface HookPipelineEntry {
  key: string;
  phase: string;
  order: number;
  enabled: boolean;
  config?: Record<string, unknown>;
}

export interface ExecutionSettings {
  schema_version: string;
  hooks: {
    pipeline: HookPipelineEntry[];
  };
  permissions: Record<string, unknown>;
  workspace: {
    checkout_strategy?:
      | "clone"
      | "worktree"
      | "sparse-clone"
      | "sparse-worktree";
  };
  skills: Record<string, unknown>;
}
```

**验证**：

```bash
cd frontend && pnpm tsc --noEmit
```

---

### Step 2: Backend Permissions API 端点

**问题**：`execution_settings.py` 有 `GET ""` 和 `PATCH ""` 和 `GET "/catalog"`，但缺少 `/permissions` 子路由。前端权限配置 UI 需要独立端点。

**文件**：`backend/app/api/v1/execution_settings.py`（修改）

**实现**：在现有路由中追加 2 个端点：

```python
from app.schemas.permission_policy import PermissionPolicy

@router.get("/permissions")
async def get_permission_policy(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    settings = service.get_or_create(db, user_id)
    permissions = settings.settings.get("permissions", {})
    return Response.success(data={"permissions": permissions})

@router.patch("/permissions")
async def update_permission_policy(
    request: PermissionPolicy,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.update(db, user_id, {"permissions": request.model_dump(mode="json")})
    permissions = result.settings.get("permissions", {})
    return Response.success(data={"permissions": permissions})
```

**验证**：

```bash
cd backend && uv run pytest tests/ -v -k "execution_settings"
```

---

### Step 3（可选）: Engine MCP Config Builder 重构

**问题**：`engine.py:596` 有 TODO 注释，Playwright MCP 注入逻辑内联在 engine 中。

**文件**：

- `executor/app/core/mcp_config.py`（新建）
- `executor/app/core/engine.py`（修改）

**实现**：将 `_inject_playwright_mcp` 的字典构建逻辑提取到独立 builder。

**优先级**：低。不影响功能，纯代码组织改进。可推迟到后续批次。

---

## 关键文件

| 文件                                        | 操作         | 说明                       |
| ------------------------------------------- | ------------ | -------------------------- |
| `frontend/features/settings/types/index.ts` | 新建         | ExecutionSettings 类型定义 |
| `backend/app/api/v1/execution_settings.py`  | 修改         | 追加 /permissions 端点     |
| `executor/app/core/mcp_config.py`           | 新建（可选） | MCP 配置 builder           |

---

## 风险与缓解

| 风险                         | 缓解措施                                   |
| ---------------------------- | ------------------------------------------ |
| 类型定义与后端 schema 不一致 | 以 `ExecutionSettings` Pydantic model 为准 |
| Permissions API 认证问题     | 复用 `get_current_user_id` 依赖            |
| Step 3 重构引入回归          | 可跳过，不影响当前功能                     |

---

## 验证

```bash
# Frontend
cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm build

# Backend
cd backend && uv run pytest tests/ -v -k "execution_settings"

# Executor
cd executor && uv run pytest tests/ -v
```

---

## 不在范围内

- Git 错误类（已验证存在）
- i18n 翻译键（已验证存在）
- Frontend Execution Settings 页面路由（组件已存在且可用）
- Engine MCP 重构（可选，低优先级）
