### 1. User Profile & Credits Integration

- **Paths**: `frontend/user-api.ts`, `backend/app/api/v1/` (needs new users/profile router)
- **Effort**: M
- **Product Impact**: High
- **New backend?**: Yes
- **Risks**: Transitioning from hardcoded `DEFAULT_*` values to real API calls requires establishing secure auth contexts and ensuring database schemas accurately reflect user credit states.

### 2. Assistant Message Feedback System

- **Paths**: `frontend/assistant-message.tsx`, `backend/app/api/v1/messages.py` (needs new routes)
- **Effort**: S
- **Product Impact**: High
- **New backend?**: Yes
- **Risks**: Local state currently hides the lack of persistence. Desynchronization between frontend UI state and backend database state if API calls fail or timeout.

### 3. Global Error Handling & Observability

- **Paths**: `frontend/error-handler.ts`
- **Effort**: S
- **Product Impact**: Medium
- **New backend?**: No
- **Risks**: Introducing Sentry could accidentally capture and leak PII if not configured correctly. Implementing toast notifications without debouncing could result in UI spam during cascading failures.

### 4. Chat Input Connection Logic

- **Paths**: `frontend/chat-input.tsx`
- **Effort**: M
- **Product Impact**: Medium
- **New backend?**: Partial
- **Risks**: Integrating connector UI logic directly into the chat input could bloat the component and complicate message-sending state management if edge cases (like unauthorized connectors) aren't handled cleanly.

### 5. Capabilities Page Route-State Refactor

- **Paths**: `frontend/capabilities-page-client.tsx`
- **Effort**: M
- **Product Impact**: Low
- **New backend?**: No
- **Risks**: Modifying route-state flow to remove obsolete branches is purely tech debt cleanup, but carries a high risk of introducing subtle frontend navigation regressions if routing parameters aren't strictly mapped.

### Synthesis

The **User Profile & Credits Integration** and **Assistant Message Feedback System** should be shipped first because they represent fundamental product gaps where the frontend is entirely stubbed out or relying on local state, and the backend lacks the corresponding endpoints. Implementing these establishes core user identity, billing/usage foundations, and AI telemetry, which are critical for a functional product loop. The frontend-only tasks (Error Handling, Connectors, Refactoring) should be tackled concurrently or immediately after to stabilize the UX and improve system observability while the backend catches up.
