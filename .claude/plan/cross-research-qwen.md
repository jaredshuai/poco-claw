## 1. Recommended Next Engineering Items (Ranked 1–5)

| # | Item | Paths | Effort | Product Impact | New Backend? | Risks |
|---|------|-------|--------|----------------|--------------|-------|
| 1 | **Real user profile & credits API** | Frontend: `user-api.ts` · Backend: new `users.py` router (or extend existing user router) | M | High — core user data currently mocked; blocks billing, settings, quota UX | **Partial** — DB models likely exist; needs CRUD + Pydantic schemas | Medium — must align auth middleware & token claims; may expose sensitive fields if not scoped to `/me` |
| 2 | **Message feedback (like/dislike) endpoint** | Frontend: `assistant-message.tsx` · Backend: `messages.py` or new `feedback.py` | S | Medium — enables model quality tracking & RLHF loop | **Yes** — new table or reaction column + route | Low — simple upsert; idempotency & unique constraint on `(message_id, user_id)` needed |
| 3 | **Chat connector implementation** | Frontend: `chat-input.tsx` line ~289 | M | Medium — unlocks multi-connector workflow (key product differentiator) | No (frontend-only wiring if backend connectors already exist) | Medium — connector UX complexity; may require backend capability discovery endpoint |
| 4 | **Error monitoring & toast integration** | Frontend: `error-handler.ts` | S | Low-Medium — improves observability & user feedback quality | No | Low — Sentry SDK install + env var; toast hook may already exist in UI lib |
| 5 | **Capabilities page refactor** | Frontend: `capabilities-page-client.tsx` | L | Low — internal cleanup; no direct user-facing value | No | High — risk of regressions in routing/state; should be paired with test coverage |

## 2. Synthesis

Ship **real profile & credits API** first because it unblocks billing visibility, quota enforcement, and settings UX — all foundational to user trust and monetization. Pair it immediately with the **message feedback endpoint** (small effort, high ML ops value) to close the quality loop on agent responses. Connector wiring and error monitoring follow as UX polish, while the capabilities refactor should be deferred until routing/state patterns are stabilized and covered by tests.
