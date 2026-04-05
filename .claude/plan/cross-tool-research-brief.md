# Cross-tool research brief (Codex / Gemini / Qwen)

**Repo root:** `e:/codespace/poco-claw` (Poco: Next.js frontend + FastAPI services + executor).

**Goal:** Cross-investigate **substantive coding work** (exclude git, CI, branch policy). Find the best next engineering investments.

**Must read (open + skim related imports):**

- `frontend/features/user/api/user-api.ts`
- `frontend/features/user/hooks/use-user-account.ts`
- `frontend/lib/errors/error-handler.ts`
- `frontend/features/chat/components/chat/messages/assistant-message.tsx`
- `frontend/features/capabilities/components/capabilities-page-client.tsx`
- `frontend/features/chat/components/chat/chat-input.tsx` (search for TODO / connection)

**Backend scan (grep or open):** any routes or schemas for **user profile**, **credits**, **message feedback / thumbs**, **usage** — under `backend/app/api`, `backend/app/services`.

**Deliverable (Markdown):**

1. **Ranked list (1–5)** of recommended next work items.
2. For **each** item: **file paths**, **effort** (S/M/L), **product impact**, **depends on new backend?** (yes/no/partial), **risks**.
3. **Synthesis:** one paragraph — what you would ship first and why.
4. **Explicitly omit:** git workflow, upstream PR, CI configuration.

**Independence:** Answer from the codebase; do not assume prior chat context.
