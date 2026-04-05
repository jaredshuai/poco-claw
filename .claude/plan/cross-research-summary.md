# 交叉调研摘要（Codex / Gemini / Qwen · 2026-04-04）

## 方法与输入

- 统一简报：`cross-tool-research-brief.md`
- 事实包（避免各 CLI 反复扫盘失败）：`cross-research-input.md`（由仓库只读摘录 + 交付格式）

## 各工具结果

| 工具       | 结果       | 说明                                                                          |
| ---------- | ---------- | ----------------------------------------------------------------------------- |
| **Qwen**   | **成功**   | 见 `cross-research-qwen.md`（完整 Markdown 交付物）                           |
| **Gemini** | **未跑通** | 缺少 `GEMINI_API_KEY`（CLI 报错退出）                                         |
| **Codex**  | **未跑通** | 一次长会话因沙箱拦截 shell；stdin 短跑因 **API usage limit** 未生成 `-o` 文件 |

## 三方共识（基于 Qwen 报告 + 事实包；可与后续补跑对齐）

优先级与 Qwen 交付一致：

1. **真实用户资料 / 额度 API**（`user-api.ts`；后端需 `/me` 类路由与模型）— 影响最大，后端 **partial**。
2. **消息点赞/反馈 API**（`assistant-message.tsx` + 新后端路由/表）— 工作量 **S**，需新后端。
3. **Connector 连接逻辑**（`chat-input.tsx` TODO）— 偏产品与集成。
4. **Sentry + Toast**（`error-handler.ts`）— 前端为主，低风险。
5. **Capabilities 路由重构**（`capabilities-page-client.tsx`）— 价值偏工程卫生，风险较高。

**建议先交付**：(1) + (2) 形成「用户身份 + 用量闭环」与「反馈闭环」；(4) 可与 (1) 并行。

## 后续若要重跑 Gemini / Codex

- 配置 `GEMINI_API_KEY` 后：`Get-Content cross-research-input.md -Raw | gemini -p "…" --approval-mode yolo`
- Codex：额度恢复后 `… | codex exec -s read-only -C e:/codespace/poco-claw -o cross-research-codex.md -`
