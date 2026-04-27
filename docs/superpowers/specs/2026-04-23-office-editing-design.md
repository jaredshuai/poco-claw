# Poco Office Editing Design

- Status: Approved in conversation
- Date: 2026-04-23
- Branch: `main`
- Scope: Poco existing session workspace, pure Web UI Office editing for current-session Word, Excel, and PowerPoint files

## 1. Overview

This design extends Poco's existing OnlyOffice-based document preview path into a controlled editing experience for Office files that are still alive inside the current session workspace.

The target experience is:

- users open a workspace Office file in the existing document viewer
- the file opens in read-only preview by default
- users click `Edit` to enter an in-place editing mode
- users click `Save` to write the latest content back to the current session workspace file
- users click `Save As` to export a local copy of the latest edited content without changing the workspace file
- users see a clear success signal only after the backend has actually written the content back and refreshed workspace metadata

This design intentionally reuses the current OnlyOffice path rather than introducing separate browser-native editors for Word, Excel, or PowerPoint.

Phase 1 release requirement:

- supported Office-editing deployments must support the OnlyOffice export path required by `Save As`
- a deployment that cannot support `downloadAs + onDownloadAs` is not considered a supported phase 1 Office-editing deployment

## 2. Product Goal

Add reliable in-browser editing for current-session Office files while preserving Poco's existing sandbox/session/workspace model:

- editing applies only to files that still exist in the current session workspace
- saving overwrites the current workspace file
- exporting a copy never mutates the workspace file
- the same session can continue working on the updated file after save

## 3. Goals

### 3.1 Primary Goals

- Support `doc`, `docx`, `xls`, `xlsx`, `ppt`, and `pptx` editing in the existing Web UI.
- Keep preview and editing in one viewer shell.
- Save edited content back to the current session workspace file.
- Show an explicit success signal only after backend write-back is complete.
- Export the latest edited content as a local copy.
- Preserve compatibility with the current manifest-driven workspace file tree.

### 3.2 Secondary Goals

- Keep the design compatible with a future desktop shell, without depending on one.
- Minimize new backend persistence in phase 1.
- Keep the feature safe under the current single-user, single-session workspace assumptions.
- Reuse the current Office size-limit configuration already present in frontend and backend.

## 4. Non-Goals

The first release will not aim to provide:

- multi-user collaborative editing
- cross-session shared documents
- background autosave into the workspace file
- file history, version rollback, or diff browsing
- browser-native spreadsheet editing engines such as SheetJS- or grid-based editors
- a guaranteed native Windows file-picker experience in every browser
- hardening for multi-instance backend deployment

## 5. Existing Foundation To Reuse

The current repository already provides the backbone needed for this project:

- Office-file detection and routing
  - `frontend/features/chat/components/execution/file-panel/document-viewer/utils.ts`
  - `frontend/features/chat/components/execution/file-panel/document-viewer/index.tsx`
- OnlyOffice iframe viewer shell
  - `frontend/features/chat/components/execution/file-panel/document-viewer/viewers/office-iframe-viewer.tsx`
- Session-owned workspace file listing from manifest
  - `backend/app/api/v1/sessions.py`
  - `backend/app/utils/workspace_manifest.py`
- OnlyOffice viewer config generation
  - `backend/app/api/v1/office.py`
  - `backend/app/services/office_viewer_service.py`
- Workspace file storage primitives
  - `backend/app/services/storage_service.py`
- Frontend workspace file refresh path
  - `frontend/features/chat/components/execution/file-panel/hooks/use-artifacts.ts`

This project should extend these foundations, not replace them.

## 6. Fixed Product Constraints

The following product constraints were explicitly confirmed in conversation and are treated as hard requirements:

- support `doc`, `docx`, `xls`, `xlsx`, `ppt`, and `pptx`
- default to read-only preview
- enter editing only after an explicit `Edit` action
- `Save` overwrites the current session workspace file
- show an obvious success indication after save
- `Save As` exports a user-local copy and does not mutate the workspace
- the feature is scoped to single-user, single-session workspaces
- if the session workspace is cleaned up, editing is naturally unavailable

## 7. Core Architectural Decision

The product will continue using OnlyOffice Document Server as the single Office rendering and editing engine.

This means:

- no separate browser-native editor stack for Excel
- no separate Word or PowerPoint editing path
- no dual-mode architecture where preview uses OnlyOffice but editing uses a different engine

The viewer shell stays unified:

- the existing Office branch in the document viewer remains the only Office entry
- the OnlyOffice iframe viewer becomes a `preview + edit` container instead of a `preview-only` container

## 8. User Experience Design

## 8.1 Entry And Modes

Every supported Office file opens in one of two modes:

- `preview`
- `edit`

### Preview Mode

- default mode when a file is opened
- toolbar shows `Edit`, `Open in new window`, and `Download original`
- the file is not editable

### Edit Mode

- entered only after the user clicks `Edit`
- the same viewer shell remains mounted
- toolbar changes to show `Save`
- `Save As` becomes available as a secondary action
- the viewer shows editing-state indicators such as `Editing`, `Saving`, or `Saved`

## 8.2 Save

`Save` means:

- trigger an explicit OnlyOffice save
- wait for backend write-back completion
- overwrite the current session workspace file
- refresh viewer/file metadata
- show a success toast

The UI must not claim success when the command request is merely accepted. Success is defined only by completed backend write-back.

## 8.3 Save As

`Save As` means:

- export a local copy of the latest in-memory document state from OnlyOffice
- do not read the workspace file as the source for export
- do not require the workspace file to be overwritten first
- do not change workspace manifest, file tree, or session file contents
- preserve the current document format by default

Phase 1 does not include format conversion in `Save As`. It exports only the current document format.

Pure Web UI cannot guarantee a Windows-native save dialog in every browser. Therefore the baseline export behavior is:

- browser download from the latest OnlyOffice-generated export stream
- optional File System Access API enhancement in supported Chromium browsers when the export stream can be bridged into a local file write

File System Access API is an enhancement, not the primary architectural dependency.

## 8.4 Unsaved-Change Protection

When the editor has unsaved changes:

- closing the viewer
- switching files
- refreshing the page
- leaving the route

must trigger a confirmation flow.

The dirty state must come from OnlyOffice editor events rather than from outer React heuristics.

The confirmation flow has only two supported outcomes in phase 1:

- `Continue editing`
- `Discard and close`

There is no implicit "save on close" action in the normal UI path.

If the user chooses `Discard and close`:

- the frontend must explicitly tell the backend that the edit session is discarded
- the backend must invalidate that edit session
- any later callback tied to that discarded edit session must be ignored

If the browser disappears unexpectedly without an explicit discard:

- a late `status=2` callback may still be accepted during the callback grace window
- that is treated as crash-recovery behavior, not as the normal save model

Before the editor has emitted its first ready/dirty-capable event, the frontend should treat the document as not yet dirty-capable and avoid showing a false unsaved-change prompt.

## 8.5 Fallback

If OnlyOffice editing is unavailable because:

- the service is disabled
- the service is unhealthy
- the file is too large
- the edit session cannot be initialized

the UI falls back to:

- read-only preview when the current view-mode Office config can still be initialized
- `Open in new window`
- `Download original`

The UI must not expose a dead `Edit` button.

The source of the "too large" decision in phase 1 is the existing Office preview size limit:

- backend: `OFFICE_FILE_SIZE_LIMIT_MB`, default `50`
- frontend: `NEXT_PUBLIC_OFFICE_FILE_SIZE_LIMIT_MB`, default `50`

The backend limit is the source of truth. The frontend probe is an early UX optimization only.

## 9. Phase 1 Operating Model

Phase 1 explicitly assumes:

- one active user per session workspace
- one backend instance handling the feature
- no attempt to preserve pending edit-session state across backend restart
- one active edit session per `(session_id, file_path)`

If the backend process restarts during an active edit session:

- pending edit/save request tracking is lost
- the user must reopen the file and re-enter editing mode

This is acceptable for phase 1 and should be documented as an operational assumption.

If the same user opens the same file in multiple tabs or windows:

- preview mode is always allowed
- only one active edit session may exist for that file
- a later `Edit` request for the same file must fail with `edit_session_conflict` until the active edit session is saved, discarded, expired, or otherwise closed

Reuse rule:

- if the frontend presents the currently active `edit_session_id` for the same file and that session is still valid, the backend may reuse and renew it
- if no matching valid `edit_session_id` is presented and another active edit session already exists for the file, the backend must return `edit_session_conflict`

Single-user reclaim rule:

- an `edit_session_conflict` response must include the current `active_edit_session_id`
- the same user may explicitly retry with that `active_edit_session_id` to resume the active edit session after refresh, remount, or tab loss

## 10. Runtime State Model

## 10.1 Edit Session

An `edit session` is a backend-tracked, short-lived logical object that binds:

- `session_id`
- `file_path`
- `document_key`
- `edit_session_id`
- `save_token`
- current mode (`preview` or `edit`)
- expiration time

The edit session exists so that callback processing never trusts the frontend to identify the write target directly.

Phase 1 edit-session TTL:

- active TTL: `30 minutes` since the last successful edit-session activity
- renewal points:
  - edit-mode `viewer-config` issuance
  - successful `forcesave` request creation
  - accepted callback tied to the same edit session

If an edit session expires while the editor is still open:

- the next explicit save must fail with an `expired_edit_session` error
- the frontend must prompt the user to reopen editing

The callback grace window is separate from active editing:

- callback acceptance grace: `15 minutes` after the last valid `save_request` creation for that edit session

This allows delayed `status=2` or `status=6` callbacks to complete after the browser is gone, without keeping the interactive session open forever.

## 10.2 Save Request

A `save request` is a short-lived save operation created when the user clicks `Save`.

Suggested fields:

- `save_request_id`
- `edit_session_id`
- `session_id`
- `file_path`
- `document_key`
- `status`
- `created_at`
- `updated_at`
- `last_error`

Phase 1 status values:

- `pending`
- `saving`
- `saved`
- `failed`

Phase 1 save-request TTL:

- save-request lifetime: `10 minutes`
- after `10 minutes`, unresolved requests become `failed` with `error_code = callback_timeout`

Phase 1 save-request transitions:

- `pending`
  - created by `POST /office/forcesave` before the command-service result is known
- `saving`
  - set by the same `forcesave` handler after OnlyOffice command service accepts the request
- `saved`
  - set by callback processing after write-back and manifest refresh complete
- `failed`
  - set by command rejection, callback error, timeout expiry, or write-back failure

The state store may be in-memory with TTL in phase 1, but the interface should be isolated so Redis or database-backed state can replace it later without changing the API contract.

## 10.3 Dirty State

The frontend owns UI-level dirty state, but its source of truth must be OnlyOffice editor events.

The frontend should not infer dirty state from outer shell actions or time-based guesses.

## 11. OnlyOffice Integration Rules

## 11.1 document.key

`document.key` must follow this rule:

- stable for the lifetime of one edit session
- refreshed only when the user exits editing and later re-enters editing

The generation input should combine:

- a canonical backend-computed `document_version`
- `edit_session_id`

The canonical `document_version` must be generated in this exact order:

1. object `etag` when available
2. otherwise object `last_modified` converted to a stable timestamp string
3. otherwise object content length as a last-resort fallback

This yields the required behavior:

- the same edit session does not break after a save
- a fresh edit session forces OnlyOffice to treat the file as a fresh document load

## 11.2 userdata

Every explicit save operation must inject `save_request_id` into OnlyOffice `userdata`.

That requirement is not optional in phase 1. It is the binding mechanism between:

- frontend `Save`
- backend `forcesave`
- asynchronous callback arrival

Without `userdata`, the backend cannot safely reconcile callback events with a specific in-flight save request.

## 11.3 callbackUrl

The edit config must include a callback URL that identifies the edit session through a backend-issued `save_token`.

The callback URL must not depend on browser cookies or current-user session state because the callback is issued by Document Server, not the browser.

Suggested semantics:

- the callback URL carries `save_token`
- the backend resolves `save_token` to `session_id`, `file_path`, and `edit_session_id`
- the backend never trusts the callback body to choose the workspace write target directly

## 11.4 Editor Events

The frontend edit shell must listen to:

- document dirty-state change
- document ready
- editor error
- download-as completion

At minimum, the design requires an explicit dirty-state event bridge so unsaved-change protection is reliable.

## 11.5 Save As Behavior

The design baseline is:

- export from the current OnlyOffice in-memory document state
- browser download as the universal fallback
- optional File System Access API enhancement only after the latest export stream has been acquired

Reading the current workspace file as the source for `Save As` is forbidden because it may be stale relative to the editor's current state.

The concrete phase 1 integration contract is:

1. the edit config registers `onDownloadAs`
2. the frontend calls `docEditor.downloadAs(format?)`
3. OnlyOffice asynchronously emits `onDownloadAs` with a download URL and file type
4. the frontend fetches that URL as the latest export artifact
5. the frontend either:
   - triggers browser download, or
   - bridges the blob into File System Access API where supported

If the current deployment or OnlyOffice edition cannot provide `downloadAs + onDownloadAs` reliably:

- the Office editing feature is unsupported in that deployment
- the product falls back to preview/download-only behavior for Office files
- the product does not fake `Save As` by exporting the workspace file instead

`Save As` failure handling in phase 1:

- if `downloadAs` cannot be invoked, show `save_as_unavailable`
- if `onDownloadAs` does not arrive before timeout, show `save_as_timeout`
- if the export URL fetch fails, show `save_as_fetch_failed`
- if browser download or local write fails, show `save_as_write_failed`

These errors do not mutate the workspace file and do not change edit state.

## 12. Frontend Design

## 12.1 Viewer Shell

Extend the current Office viewer path inside:

- `frontend/features/chat/components/execution/file-panel/document-viewer/index.tsx`
- `frontend/features/chat/components/execution/file-panel/document-viewer/viewers/office-iframe-viewer.tsx`

Key responsibilities:

- preview/edit mode toggle
- toolbar actions
- save state
- dirty-state guard
- post-save refresh
- fallback rendering

## 12.2 Toolbar Contract

Preview mode:

- `Edit`
- `Open in new window`
- `Download original`

Edit mode:

- `Save`
- `Save As`
- optional `Back to preview`

The toolbar should also expose a compact status label:

- `Read only`
- `Editing`
- `Saving`
- `Saved`
- `Save failed`

Only one save may be in flight for one edit session.

While a save request is `pending` or `saving`:

- the `Save` button must be disabled
- repeated clicks must not create additional save requests
- `Back to preview` must be disabled

`Back to preview` semantics in phase 1:

- allowed only when there is no in-flight save
- if the editor is clean, it closes the active edit session and returns to preview mode
- if the editor is dirty, the user must either continue editing or explicitly discard before returning to preview

## 12.3 Save Flow In The Frontend

When the user clicks `Save`:

1. create a local pending save state
2. call `POST /office/forcesave`
3. receive or already know the `save_request_id`
4. poll `GET /office/save-status`
5. when backend returns `saved`, refresh the selected file using the existing workspace refresh path
6. only then show the success toast

The success toast must be tied to backend-completed state, not command acceptance.

If `POST /office/forcesave` returns `save_in_progress`, the frontend must continue tracking the returned active `save_request_id` instead of creating a new one.

If `POST /office/forcesave` returns a terminal error:

- keep the user in edit mode when recovery is possible
- leave the workspace file unchanged
- surface the returned machine-readable error through the existing Office error presentation path

## 12.4 Save As Flow In The Frontend

When the user clicks `Save As`:

1. request latest content export from OnlyOffice
2. receive an export stream or download URL for the current document state
3. if supported and practical, bridge the blob into File System Access API
4. otherwise trigger browser download

This flow must not depend on workspace overwrite completion.

If any step in this flow fails:

- surface a `Save As`-specific error
- keep the user in edit mode
- keep workspace content unchanged

## 12.5 Cache Refresh

After a successful save, the frontend must refresh:

- selected file metadata
- presigned URL
- file tree cache

This is necessary because stale `file.url` would otherwise make:

- `Download original`
- `Open in new window`

open the pre-save file.

## 12.6 OnlyOffice Native Menu Control

The frontend config should disable or constrain the native OnlyOffice `Save As` entry when possible so the product exposes one coherent export path.

If the embedded editor cannot fully suppress the native menu in a supported deployment, the external toolbar still remains the product-supported path and documentation must state that clearly.

## 13. Backend Design

## 13.1 Extend Viewer Config

Extend:

- `POST /office/viewer-config`

The request must support `mode = view | edit`.

### View Mode

- current behavior, read-only

### Edit Mode

Must include at least:

- edit-capable `editorConfig.mode`
- callback URL with `save_token`
- user metadata needed by OnlyOffice
- document permissions suitable for editing
- editor customization needed to support the Poco toolbar contract

Phase 1 request contract:

- `session_id`
- `file_path`
- `file_type` when needed by current backend schema
- `language`
- `mode = "view" | "edit"`
- optional `requested_edit_session_id`

Phase 1 response contract in `edit` mode additionally exposes:

- `edit_session_id`
- `document.key`
- callback URL semantics embedded in the returned config
- explicit editor events required by the frontend shell
- `capabilities`

Phase 1 capabilities contract:

- `can_edit`
- `can_save_as`
- `fallback_reason | null`
- `save_as_reason | null`

Phase 1 capability rule:

- in a supported Office-editing deployment, `can_edit = true` implies `can_save_as = true`
- if `downloadAs` support cannot be guaranteed for the deployment, the Office editing feature must not be enabled for that deployment

Frontend rules:

- hide or disable `Edit` when `can_edit = false`
- hide or disable `Save As` when `can_save_as = false`
- use `fallback_reason` and `save_as_reason` to choose user-facing fallback copy

Phase 1 capability source of truth:

- `OfficeCapabilityResolver` computes `can_edit` and `can_save_as`
- its inputs are:
  - deployment-level `OFFICE_EDITING_ENABLED` flag
  - deployment-level `OFFICE_SAVE_AS_ENABLED` flag
  - Document Server health status

Validation source in phase 1:

- static deployment config provides the enable/disable flags
- `/office/health` provides runtime Document Server availability
- `OFFICE_SAVE_AS_ENABLED` may be turned on only for deployments that have validated `downloadAs + onDownloadAs` support for the active OnlyOffice stack

The frontend does not infer these capabilities on its own.

## 13.2 Add Force Save Endpoint

Add:

- `POST /office/forcesave`

Responsibilities:

- validate the current session and file still exist
- create a `save_request`
- inject `save_request_id` into `userdata`
- call OnlyOffice command service to trigger explicit save
- return enough information for frontend progress tracking

Phase 1 response contract:

- `202 accepted`
  - `save_request_id`
  - `status = "pending"`
  - `poll_after_ms`
  - `active_edit_session_id`
- `409 duplicate save`
  - `error_code = save_in_progress`
  - `active_save_request_id`
  - `active_edit_session_id`
- terminal error
  - machine-readable `error_code`
  - `active_edit_session_id | null`

The frontend must treat the returned status as "request accepted", not "save completed".

`forcesave` is a trigger endpoint, not a success endpoint.

Phase 1 duplicate-save rule:

- one in-flight save per edit session
- if a second save is requested while one is already `pending` or `saving`, the backend returns `409` with `error_code = save_in_progress` plus the active `save_request_id`

## 13.3 Add Callback Endpoint

Add:

- `POST /office/callback`

Responsibilities:

- validate `save_token`
- resolve the backend-owned edit session context
- reconcile callback payload with the current edit session
- treat relevant save statuses as save events
- fetch the latest file content from Document Server
- overwrite the workspace object
- update manifest metadata
- mark the related `save_request` as `saved` or `failed`

The callback endpoint must not rely on ordinary browser-auth user middleware.

Phase 1 callback status mapping:

- `1`: informational editor-connect/disconnect event; no write-back
- `2`: terminal save after editor close with changes; fetch `url`, overwrite workspace file, refresh manifest, mark matching request complete when applicable
- `3`: save error; do not write back, mark matching request failed when applicable
- `4`: closed with no changes; no write-back
- `6`: explicit force-save success; fetch `url`, overwrite workspace file, refresh manifest, mark matching `save_request_id` as `saved`
- `7`: force-save error; do not write back, mark matching `save_request_id` as failed

Statuses outside this set are ignored in phase 1.

Repeated `status=2` or `status=6` callbacks for the same completed save request must be idempotent and safe no-ops after completion.

`status=2` support in phase 1 is explicitly limited:

- accepted only when the edit session was not explicitly discarded
- accepted only within the callback grace window
- treated as crash-recovery or close-after-edit persistence, not as the primary UI save model

## 13.4 Add Discard Edit Session Endpoint

Add:

- `POST /office/edit-session/discard`

Responsibilities:

- validate the current session and edit session
- mark the edit session as discarded
- invalidate its `save_token`
- cause subsequent late callbacks for that edit session to be ignored

This endpoint exists to keep the explicit-save model coherent when the user intentionally discards changes.

## 13.5 Add Save Status Endpoint

Add:

- `GET /office/save-status`

Responsibilities:

- expose the status of a short-lived save request
- return one of `pending`, `saving`, `saved`, or `failed`
- optionally include machine-readable failure reason

Phase 1 request contract:

- `session_id`
- `save_request_id`

Phase 1 response contract:

- `status`
- `error_code | null`
- `error_message | null`
- `completed_at | null`
- `active_save_request_id | null`

Phase 1 polling rules:

- poll interval: `1000 ms`
- stop on `saved` or `failed`
- stop auto-polling after `60 seconds` and surface a "save taking longer than expected" state
- if the request is missing or expired, return `failed` with `error_code = not_found_or_expired`

Phase 1 uses polling because it is simpler to integrate into the current frontend shell than introducing a new push channel.

Client-side timeout is a soft timeout, not a server-side terminal state:

- after `60 seconds`, the UI stops automatic polling
- the save request may still complete in the backend until its `10 minute` TTL expires
- the UI must offer `Check status again` and `Refresh file list`
- if the backend later reports `saved`, the refreshed file tree becomes the source of truth

## 13.6 State Store

Phase 1 should introduce an explicit backend state abstraction for:

- edit sessions
- save requests

The first implementation may be:

- in-memory
- TTL-based
- single-instance

But it must be encapsulated behind a service boundary so the project can switch to Redis or database-backed state later.

## 13.7 Core Backend Units

The planning baseline should split backend responsibilities into these units:

- `EditSessionStore`
  - `create_session`
  - `reuse_session`
  - `renew_session`
  - `discard_session`
  - `expire_session`
  - `resolve_by_token`
- `SaveRequestStore`
  - `create_request`
  - `mark_saving`
  - `mark_saved`
  - `mark_failed`
  - `get_request`
  - `expire_requests`
- `OnlyOfficeConfigService`
  - build `view` and `edit` configs
- `OfficeCapabilityResolver`
  - compute `can_edit`, `can_save_as`, `fallback_reason`, and `save_as_reason` from deployment settings and current health
- `OnlyOfficeCommandClient`
  - send `forcesave` commands and normalize command-service failures
- `OnlyOfficeCallbackService`
  - validate callback context, map callback statuses, and drive write-back decisions
- `WorkspaceFileWritebackService`
  - fetch latest document payload, overwrite workspace object, and refresh manifest metadata through one helper

These boundaries are required for implementation planning. The callback route must orchestrate these units rather than embedding all logic inline.

## 13.8 Auth And Transport

Browser-authenticated endpoints in phase 1:

- `POST /office/viewer-config`
- `POST /office/forcesave`
- `GET /office/save-status`
- `POST /office/edit-session/discard`

These endpoints use the normal current-user browser auth model already used by session-bound APIs.

Phase 1 transport rules:

- `viewer-config`: JSON body
- `forcesave`: JSON body
- `edit-session/discard`: JSON body
- `save-status`: query parameters `session_id` and `save_request_id`

The callback endpoint is different:

- `POST /office/callback` does not use browser user auth
- it authenticates through `save_token` and backend-owned edit-session resolution

## 13.9 Compatibility And Rollout

This feature is an additive extension of the current Office preview path.

Compatibility rules:

- existing read-only preview behavior remains valid when edit mode is not requested
- new request/response fields are additive extensions, not a versioned API fork
- the feature still requires coordinated frontend/backend rollout before the UI exposes editing controls

In mixed deployments:

- older frontends continue using preview-only behavior
- newer frontends must not expose editing controls until the backend advertises edit capabilities

## 14. Save And Export Flows

## 14.1 Save Flow

1. User opens Office file in preview mode.
2. User clicks `Edit`.
3. Frontend requests edit config from `/office/viewer-config`.
4. Backend creates/refreshes an edit session and returns edit-capable config.
5. User edits the file.
6. User clicks `Save`.
7. Frontend calls `/office/forcesave`.
8. Backend creates `save_request`, sends OnlyOffice command request, and returns pending status.
9. Document Server emits callback for the relevant save event.
10. Backend validates the callback, fetches the latest file content, overwrites the workspace file, updates manifest metadata, and marks the save request complete.
11. Frontend polls `/office/save-status` until `saved` or `failed`.
12. On `saved`, frontend refreshes the file tree and selected file URL, then shows success.

If the frontend reaches the `60 second` soft timeout first:

- it shows a non-success timeout state
- it does not claim save failure unless backend later marks the request `failed`
- the user may recheck status or refresh the file list

## 14.2 Save As Flow

1. User is in edit mode.
2. User clicks `Save As`.
3. Frontend calls the OnlyOffice `downloadAs` path from the active editor instance.
4. OnlyOffice emits `onDownloadAs` with a URL for the latest current document state.
5. Frontend fetches the export URL as a blob.
6. Browser download becomes the guaranteed baseline behavior.
7. If the browser supports File System Access API and the blob is available for local bridging, the UI may offer a richer local-save path.

This flow does not mutate the workspace and does not wait for callback-driven workspace write-back.

## 14.3 Browser-Close Scenario

If the user closes the tab or browser while an edit session exists:

- the frontend may disappear before save-status polling completes
- Document Server may still issue a terminal callback later

Phase 1 behavior:

- backend still processes the callback if the edit session is valid
- the workspace file may still be updated
- no live success notification is required because the browser has already left
- if the edit session was explicitly discarded before close, the callback is ignored

The next time the user opens the session, the updated file tree should reflect the saved content if the callback completed successfully.

## 15. Manifest And Storage Update Policy

The workspace file tree is manifest-driven, so save success requires:

- object overwrite
- manifest metadata refresh

The manifest update must at minimum refresh:

- `size`
- `etag`
- `last_modified`

If hashes such as `sha256` or `md5` are maintained for that entry, they should also be refreshed.

Phase 1 policy:

- implement manifest updates through one dedicated helper/service
- prefer a storage-backed precondition or version-aware update when the storage stack makes it practical
- if the storage backend cannot provide a clean conditional-write contract in the current deployment, fall back to single-writer phase 1 behavior and document that assumption explicitly

The design must not scatter ad hoc manifest mutation logic across multiple endpoints.

From the API perspective, save success is atomic: the API may report `saved` only after both object overwrite and manifest refresh complete.

## 16. Security And Integrity Rules

## 16.1 Required In Phase 1

- `save_token` on callback URL
- backend-owned resolution from token to write target
- path normalization and workspace-prefix boundary checks
- no trust in callback/body-provided write target
- no reliance on frontend cookies for callback authorization

## 16.2 Optional Hardening

If the deployment can reliably surface and validate OnlyOffice callback token semantics in the current environment, JWT validation may be layered on top of `save_token`.

That is a hardening improvement, not the only correctness mechanism for phase 1.

## 16.3 SSRF Guard

When backend fetches the latest saved document from Document Server:

- the source URL must be validated against the expected Document Server origin or other trusted callback contract
- arbitrary external URLs must not be fetched and written into the workspace

## 16.4 Error Contract Matrix

Phase 1 machine-readable error codes should include at least:

### `viewer-config`

- `office_disabled`
- `office_unhealthy`
- `file_too_large`
- `file_not_found`
- `invalid_file_type`
- `expired_edit_session`
- `edit_session_conflict`

Frontend behavior:

- hide or disable `Edit`
- keep preview/download fallback available

### `forcesave`

- `save_in_progress`
- `expired_edit_session`
- `file_not_found`
- `office_command_rejected`
- `office_unhealthy`
- `token_invalid`

Frontend behavior:

- if `save_in_progress`, continue tracking returned `active_save_request_id`
- otherwise surface save failure and remain in edit mode unless the session is invalid

### `save-status`

- `not_found_or_expired`
- `callback_timeout`
- `writeback_failed`
- `manifest_update_failed`
- `office_callback_error`

Frontend behavior:

- stop auto-polling on terminal `failed`
- allow manual refresh/retry guidance
- never show success toast on these errors

### `callback`

- callback errors are backend-handled and mapped into save-request failure states rather than returned to the browser directly

### `save-as`

- `save_as_unavailable`
- `save_as_timeout`
- `save_as_fetch_failed`
- `save_as_write_failed`

## 17. Browser Compatibility

The product is Web-first.

Guaranteed behavior:

- in-browser preview
- in-browser editing
- explicit save back to workspace
- browser-download export for `Save As`

Enhanced behavior when possible:

- File System Access API-assisted local save in supported Chromium browsers

Unsupported assumptions:

- guaranteed native Windows save dialog in every browser
- identical export UX across Chrome, Edge, Firefox, and Safari

## 18. Testing And Acceptance

## 18.1 Backend Tests

Expand or add tests for:

- view-mode config generation
- edit-mode config generation
- `save_token` issuance and validation
- `userdata` propagation
- callback write-back success
- callback failure paths
- save-status lifecycle
- manifest metadata refresh
- edit-session expiration behavior
- discard-and-close behavior
- duplicate save handling

Relevant starting points:

- `backend/tests/test_office_api.py`
- `backend/tests/test_office_viewer_service.py`

## 18.2 Frontend Tests

Add tests for:

- preview-to-edit mode transition
- save button state transitions
- dirty-state guard behavior
- success toast only after backend-complete save
- file URL refresh after save
- `Save As` path using latest editor-state export
- `downloadAs` / `onDownloadAs` export path
- `Save As` failure handling
- fallback behavior when edit mode is unavailable

Relevant starting points:

- `frontend/tests/features/chat/components/execution/document-viewer/office-branch.test.tsx`
- `frontend/tests/features/chat/components/execution/document-viewer/office-viewer-too-large.test.tsx`

## 18.3 Acceptance Criteria

The first release is done when:

- a supported Office file in the current session workspace opens in preview mode
- `Edit` enters working edit mode inside the existing viewer shell
- `Save` overwrites the current workspace file
- save success is shown only after backend write-back completes
- reopening or downloading the file after save returns the new content
- `Save As` exports the latest edited content as a local copy
- edit becomes unavailable when the configured Office size limit is exceeded
- unsupported or unhealthy edit conditions degrade safely to preview/download actions

## 19. Deferred Items

The following are intentionally deferred:

- multi-user collaboration
- cross-session persistent editing state
- background autosave into workspace
- full database or Redis backing for save state
- guaranteed File System Access API flow in all browsers
- full conflict-resolution UI
- document history and rollback
- strict callback JWT hardening if `save_token` and deployment boundaries already satisfy phase 1 risk tolerance
