# Cross-research packet (for Codex / Gemini / Qwen)

**Note:** facts resynced 2026-04-04.

## Deliverable format (output ONLY this structure in Markdown)

1. Ranked list **1–5** of recommended next engineering items.
2. For **each** item: **paths**, **effort** S/M/L, **product impact**, **new backend?** yes/no/partial, **risks**.
3. One **synthesis** paragraph: what to ship first and why.
4. Do **not** discuss git, CI, or upstream.

---

## Repo facts (extracted from `e:/codespace/poco-claw`, read-only)

### Frontend — `user-api.ts`

- `getMe()` uses `apiClient.get<UserMeResponse>(API_ENDPOINTS.usersMe)` to fetch profile + credits from `GET /users/me`.
- `getProfile` / `getCredits` both call `getMe()`; runtime data is no longer sourced from hardcoded `DEFAULT_*` values.

### Frontend — `error-handler.ts`

- `logError`: reports to Tencent Aegis RUM via `reportToRum(...)` when `NEXT_PUBLIC_AEGIS_ID` is set (and also reports in production mode).
- `handleError`: uses `sonner` `toast.error(...)` when `showToast` is true.

### Frontend — `assistant-message.tsx`

- `onLike`: performs an optimistic toggle and persists it with `PUT /messages/{id}/feedback` via `apiClient.put(API_ENDPOINTS.messageFeedback(messageId), { vote })`.
- Message responses carry `feedback_vote`; the frontend maps that value into `feedbackVote`.

### Frontend — `chat-input.tsx`

- The tools/connectors menu opens the real `ConnectorsDialog`, preselects the connector tab/item, and is no longer placeholder-only.
- `ConnectorsDialog` uses `useConnectorsCatalog()` to load the live connector catalog, including MCP installs and runtime connection state.

### Frontend — `capabilities-page-client.tsx`

- Top comment: **TODO: Refactor route-state flow and remove obsolete branches**.

### Backend — usage

- `backend/app/api/v1/usage.py`: **`GET /usage/analytics`** — implemented; ties to `UsageAnalyticsService`. Frontend already has `getUsageAnalytics` / settings usage tab.

### Backend — profile / credits / message feedback

- `backend/app/api/v1/users.py`: `GET /users/me` is implemented and returns combined profile + credits via `UserAccountService`.
- Message feedback is implemented end-to-end: `backend/alembic/versions/62c30d49d2b9_add_message_feedbacks.py` creates `message_feedbacks`, and `backend/app/api/v1/message_feedback.py` exposes `PUT /messages/{message_id}/feedback`.
- `backend/app/schemas/message.py` includes `feedback_vote` on message responses.

### Independence

Answer from facts above; do not assume other chat context.
