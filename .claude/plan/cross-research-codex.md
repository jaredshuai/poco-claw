1. **Replace mocked profile/credits with real user data**
   - **paths:** `frontend/.../user-api.ts`, `backend/app/api/v1/` (new profile/user router), `backend/app/services/`, `backend/app/schemas/`
   - **effort:** M
   - **product impact:** High. This removes obviously fake account state from the product and makes profile/credits surfaces trustworthy.
   - **new backend?** yes
   - **risks:** Requires deciding source of truth for credits/profile fields; if auth identity or billing data is not already normalized in backend, scope can expand.

2. **Add persistent assistant-message feedback API and wire the like action**
   - **paths:** `frontend/.../assistant-message.tsx`, `backend/app/api/v1/messages*.py` or new feedback route, `backend/app/services/`, `backend/app/models/`, `backend/app/schemas/`
   - **effort:** M
   - **product impact:** High. It turns a dead-end UI toggle into usable product signal for quality, ranking, and future moderation/analytics.
   - **new backend?** yes
   - **risks:** Needs feedback schema design and idempotency rules; may require migration if no message-feedback persistence exists.

3. **Implement connector connection flow in chat input**
   - **paths:** `frontend/.../chat-input.tsx`, likely related connector/capabilities feature modules
   - **effort:** M
   - **product impact:** High if connectors are meant to be part of task setup or chat context; right now the UI appears to expose a path users cannot complete.
   - **new backend?** partial
   - **risks:** The frontend TODO is clear, but backend readiness is not. If connector auth/session endpoints are incomplete, this can turn from UI wiring into a broader integration project.

4. **Refactor capabilities route-state flow and remove obsolete branches**
   - **paths:** `frontend/.../capabilities-page-client.tsx`, likely nearby feature state/router helpers
   - **effort:** M
   - **product impact:** Medium. This should reduce navigation bugs, stale state branches, and future change cost in a feature that likely has already accumulated debt.
   - **new backend?** no
   - **risks:** Refactors in route-state code can create regressions in selection, tab persistence, or deep-link behavior if not validated against real usage paths.

5. **Finish the error handling layer: user toast behavior and real error reporting**
   - **paths:** `frontend/.../error-handler.ts`, any shared toast plumbing, Sentry/init wiring if present
   - **effort:** S-M
   - **product impact:** Medium. Users get visible failure feedback instead of silent errors, and the team gets production diagnostics instead of TODO stubs.
   - **new backend?** no
   - **risks:** Toast spam or double-reporting if the error boundary and local handlers overlap; Sentry rollout needs event filtering to avoid noise.

Ship **real profile/credits first**, then **message feedback**. The first removes fake core account data that undermines product trust everywhere it appears, while the second converts an already-exposed interaction into durable learning signal with clear downstream value. After those two, tackle **connector connection flow** if connectors are part of the main user journey, because it likely affects task setup more directly than the cleanup items. The route-state refactor and error-layer completion are both worthwhile, but they should follow once the product stops presenting mock data and no-op interactions in user-facing paths.
