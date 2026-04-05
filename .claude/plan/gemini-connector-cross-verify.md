# Gemini cross-verify: MCP connectors UI (post-Codex)

**Repo:** e:/codespace/poco-claw

**Scope:** Codex wired `frontend/features/connectors/**` and `chat-input.tsx` to real MCP install + run connection state (no App OAuth).

**Read and analyze (no file writes):**
- `frontend/features/connectors/components/connectors/connectors-dialog.tsx`
- `frontend/features/connectors/components/connectors/connector-card.tsx`
- `frontend/features/connectors/components/connectors/connector-detail.tsx` (if exists)
- `frontend/features/chat/components/chat/chat-input.tsx` (connector entry)
- `frontend/features/connectors/lib/` if present (mcp-connector-state etc.)

**Check:**
1. i18n: no new user-visible English hardcoding; keys exist for new labels.
2. Security: no secrets in client; API calls use existing authenticated client patterns.
3. OAuth: Gmail/GitHub-style flows not accidentally started.
4. UX: disabled vs coming-soon semantics coherent.

**Output:** Verdict PASS/PASS WITH NOTES/FAIL, evidence table, P0/P1 risks, manual QA bullets.
