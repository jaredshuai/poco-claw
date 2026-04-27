"use client";

import * as React from "react";
import {
  Download,
  ExternalLink,
  FileWarning,
  Loader2,
  Pencil,
  Save,
  Undo2,
} from "lucide-react";
import { toast } from "sonner";
import { useT } from "@/lib/i18n/client";
import { ApiError } from "@/lib/errors";
import {
  BEFORE_CLOSE_DOCUMENT_VIEWER_EVENT,
  type BeforeCloseDocumentViewerEvent,
} from "@/lib/document-viewer-leave-guard";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { apiClient, API_ENDPOINTS } from "@/services/api-client";
import type { FileNode } from "@/features/chat/types";
import {
  ensureAbsoluteUrl,
  downloadFileFromUrl,
  extractExtension,
  isSameOriginUrl,
} from "../utils";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const OFFICE_VIEWER_URL = process.env.NEXT_PUBLIC_OFFICE_VIEWER_URL ?? "";
/** Explicit opt-in: unset or false keeps Office preview off until OnlyOffice is configured. */
const OFFICE_VIEWER_ENABLED =
  process.env.NEXT_PUBLIC_OFFICE_VIEWER_ENABLED === "true";
// Total timeout for the entire initialization process (fetch config, load api.js, init editor)
const TOTAL_TIMEOUT_MS = Number(
  process.env.NEXT_PUBLIC_OFFICE_VIEWER_TIMEOUT_MS ?? "30000",
);
// Timeout specifically for editor rendering after DocEditor is instantiated
const EDITOR_RENDER_TIMEOUT_MS = 15000;
const OFFICE_FILE_SIZE_LIMIT_MB = Number(
  process.env.NEXT_PUBLIC_OFFICE_FILE_SIZE_LIMIT_MB ?? "50",
);
const OFFICE_FILE_SIZE_LIMIT = OFFICE_FILE_SIZE_LIMIT_MB * 1024 * 1024;

const IS_DEV =
  typeof process !== "undefined" && process.env.NODE_ENV === "development";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Error kinds map to i18n only — never surface raw API/Error.message to users. */
type OfficeViewerErrorKind = "timeout" | "tooLarge" | "editor" | "generic";

interface OfficeViewerConfig {
  document: {
    fileType: string;
    key: string;
    title: string;
    url: string;
  };
  documentType: string;
  editorConfig: {
    mode: string;
    lang: string;
  };
  token: string;
  type: string;
  edit_session_id?: string;
}

interface OfficeForceSaveResponse {
  save_request_id: string;
  status: "pending" | "saving";
  poll_after_ms?: number;
}

interface OfficeSaveStatusResponse {
  save_request_id: string;
  status: "pending" | "saving" | "saved" | "failed";
  error_code?: string | null;
  error_message?: string | null;
  completed_at?: string | null;
}

interface OfficeDiscardEditSessionResponse {
  edit_session_id: string;
  status: "discarded";
}

interface OfficeDownloadLatestResponse {
  url: string;
  file_path: string;
  expires_in: number;
}

declare global {
  interface Window {
    DocsAPI?: {
      DocEditor: new (
        elementId: string,
        config: Record<string, unknown>,
      ) => { destroyEditor?: () => void };
    };
  }
}

export interface OfficeIframeViewerProps {
  file: FileNode;
  sessionId?: string;
  ensureFreshFile?: (
    file: FileNode,
    options?: { force?: boolean },
  ) => Promise<FileNode | undefined>;
}

type ViewerState =
  | { status: "loading" }
  | { status: "ready" }
  | { status: "error"; kind: OfficeViewerErrorKind }
  | { status: "disabled" };

type OfficeMode = "view" | "edit";
type SaveState = "idle" | "saving" | "saved" | "failed";

type FileSystemWritable = {
  write: (data: Blob) => Promise<void>;
  close: () => Promise<void>;
};

type FileSystemHandle = {
  createWritable: () => Promise<FileSystemWritable>;
};

type FileSystemAccessWindow = Window &
  typeof globalThis & {
    showSaveFilePicker?: (options?: {
      suggestedName?: string;
      types?: Array<{
        description: string;
        accept: Record<string, string[]>;
      }>;
    }) => Promise<FileSystemHandle>;
  };

type PocoNativeWindow = Window &
  typeof globalThis & {
    poco?: {
      saveFile?: (options: {
        suggestedName: string;
        mimeType: string;
        data: ArrayBuffer;
      }) => Promise<void>;
    };
  };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let apiJsPromise: Promise<void> | null = null;

function loadOnlyOfficeApiJs(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.DocsAPI) return Promise.resolve();

  if (!apiJsPromise) {
    apiJsPromise = new Promise<void>((resolve, reject) => {
      const src = `${OFFICE_VIEWER_URL.replace(/\/+$/, "")}/web-apps/apps/api/documents/api.js`;
      const existing = document.querySelector(
        `script[src="${src}"]`,
      ) as HTMLScriptElement | null;

      if (existing) {
        if (window.DocsAPI) {
          resolve();
          return;
        }
        existing.addEventListener("load", () => resolve());
        existing.addEventListener("error", () =>
          reject(new Error("Failed to load OnlyOffice api.js")),
        );
        return;
      }

      const script = document.createElement("script");
      script.src = src;
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () =>
        reject(new Error("Failed to load OnlyOffice api.js"));
      document.head.appendChild(script);
    }).catch((err) => {
      apiJsPromise = null;
      throw err;
    });
  }

  return apiJsPromise;
}

/**
 * Probe file size via HEAD request.  Returns the Content-Length in bytes,
 * or `null` when the size cannot be determined (CORS, missing header, etc.).
 */
async function probeFileSize(url: string): Promise<number | null> {
  try {
    const isSameOrigin =
      typeof window !== "undefined" &&
      new URL(url, window.location.origin).origin === window.location.origin;
    const resp = await fetch(url, {
      method: "HEAD",
      credentials: isSameOrigin ? "include" : "omit",
    });
    const cl = resp.headers.get("content-length");
    if (cl) {
      const n = Number(cl);
      if (Number.isFinite(n) && n >= 0) return n;
    }
  } catch (err) {
    if (IS_DEV) {
      console.warn(
        "[OfficeIframeViewer] HEAD probe failed; size guard may be bypassed if CORS hides Content-Length:",
        err,
      );
    }
  }
  return null;
}

/**
 * Maps browser `document.documentElement.lang` to OnlyOffice `editorConfig.lang` codes.
 */
function mapEditorLang(browserLang: string): string {
  const lower = browserLang.trim().toLowerCase();
  if (lower.startsWith("zh")) return "zh";
  if (lower.startsWith("ja")) return "ja";
  if (lower.startsWith("ko")) return "ko";
  if (lower.startsWith("de")) return "de";
  if (lower.startsWith("fr")) return "fr";
  if (lower.startsWith("ru")) return "ru";
  if (lower.startsWith("en")) return "en";
  return "en";
}

function triggerBlobDownload(blob: Blob, filename: string) {
  const blobUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
}

async function saveBlobLocally(blob: Blob, filename: string) {
  const nativeWindow = window as PocoNativeWindow;
  if (nativeWindow.poco?.saveFile) {
    await nativeWindow.poco.saveFile({
      suggestedName: filename,
      mimeType: blob.type || "application/octet-stream",
      data: await blob.arrayBuffer(),
    });
    return;
  }

  const fsWindow = window as FileSystemAccessWindow;
  if (fsWindow.showSaveFilePicker) {
    const handle = await fsWindow.showSaveFilePicker({
      suggestedName: filename,
      types: [
        {
          description: "Office document",
          accept: {
            [blob.type || "application/octet-stream"]: [
              `.${filename.split(".").pop() || "bin"}`,
            ],
          },
        },
      ],
    });
    const writable = await handle.createWritable();
    await writable.write(blob);
    await writable.close();
    return;
  }

  triggerBlobDownload(blob, filename);
}

function getActiveSaveRequestId(error: unknown): string | undefined {
  if (!(error instanceof ApiError) || error.statusCode !== 409) {
    return undefined;
  }

  const details = error.details;
  if (!details || typeof details !== "object") {
    return undefined;
  }

  const payload =
    "data" in details && details.data && typeof details.data === "object"
      ? details.data
      : details;
  if (
    "active_save_request_id" in payload &&
    typeof payload.active_save_request_id === "string"
  ) {
    return payload.active_save_request_id;
  }

  return undefined;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function OfficeIframeViewer({
  file,
  sessionId,
  ensureFreshFile,
}: OfficeIframeViewerProps) {
  const { t } = useT("translation");
  const reactId = React.useId();
  /** Stable unique DOM id for OnlyOffice container (avoids duplicate id if multiple instances). */
  const placeholderDomId = React.useMemo(
    () => `oo-editor-${reactId.replace(/:/g, "")}`,
    [reactId],
  );
  const containerRef = React.useRef<HTMLDivElement>(null);
  const editorRef = React.useRef<{ destroyEditor?: () => void } | null>(null);
  const editSessionIdRef = React.useRef<string | undefined>(undefined);
  const [state, setState] = React.useState<ViewerState>({ status: "loading" });
  const [mode, setMode] = React.useState<OfficeMode>("view");
  const [editSessionId, setEditSessionId] = React.useState<string | undefined>();
  const [isDirty, setIsDirty] = React.useState(false);
  const [saveState, setSaveState] = React.useState<SaveState>("idle");
  const [isSaveAsRunning, setIsSaveAsRunning] = React.useState(false);
  const [isLeaveDialogOpen, setIsLeaveDialogOpen] = React.useState(false);
  const [isDiscardingForLeave, setIsDiscardingForLeave] =
    React.useState(false);
  const leaveConfirmationPromiseRef = React.useRef<Promise<boolean> | null>(
    null,
  );
  const leaveConfirmationResolveRef = React.useRef<
    ((allowed: boolean) => void) | null
  >(null);

  // Feature enabled only when env explicitly true and Document Server URL is set
  const isEnabled = OFFICE_VIEWER_ENABLED && Boolean(OFFICE_VIEWER_URL.trim());

  React.useEffect(() => {
    editSessionIdRef.current = editSessionId;
  }, [editSessionId]);

  const discardEditSession = React.useCallback(async () => {
    if (!sessionId || !editSessionId) return;
    await apiClient.post<OfficeDiscardEditSessionResponse>(
      API_ENDPOINTS.officeDiscardEditSession,
      {
        session_id: sessionId,
        file_path: file.path,
        edit_session_id: editSessionId,
      },
    );
    setIsDirty(false);
    setSaveState("idle");
    setEditSessionId(undefined);
    setMode("view");
  }, [editSessionId, file.path, sessionId]);

  const settleLeaveConfirmation = React.useCallback((allowed: boolean) => {
    leaveConfirmationResolveRef.current?.(allowed);
    leaveConfirmationResolveRef.current = null;
    leaveConfirmationPromiseRef.current = null;
    setIsLeaveDialogOpen(false);
    setIsDiscardingForLeave(false);
  }, []);

  const requestLeaveConfirmation = React.useCallback(() => {
    if (leaveConfirmationPromiseRef.current) {
      return leaveConfirmationPromiseRef.current;
    }

    const promise = new Promise<boolean>((resolve) => {
      leaveConfirmationResolveRef.current = resolve;
      setIsLeaveDialogOpen(true);
    });
    leaveConfirmationPromiseRef.current = promise;
    return promise;
  }, []);

  React.useEffect(() => {
    return () => {
      leaveConfirmationResolveRef.current?.(false);
      leaveConfirmationResolveRef.current = null;
      leaveConfirmationPromiseRef.current = null;
    };
  }, []);

  const confirmLeaveAndDiscard = React.useCallback(async () => {
    if (isDiscardingForLeave) return;
    setIsDiscardingForLeave(true);
    try {
      await discardEditSession();
      settleLeaveConfirmation(true);
    } catch (error) {
      if (IS_DEV) {
        console.error("[OfficeIframeViewer] discard before leave failed", error);
      }
      toast.error(t("artifacts.viewer.office.discardFailed"));
      settleLeaveConfirmation(false);
    }
  }, [
    discardEditSession,
    isDiscardingForLeave,
    settleLeaveConfirmation,
    t,
  ]);

  React.useEffect(() => {
    if (mode !== "edit" || !isDirty) return;

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, [isDirty, mode]);

  React.useEffect(() => {
    if (mode !== "edit" || !isDirty) return;

    const handleBeforeClose = (event: Event) => {
      const detail = (event as BeforeCloseDocumentViewerEvent).detail;
      if (detail?.waitUntil) {
        detail.waitUntil(requestLeaveConfirmation());
        return;
      }

      event.preventDefault();
      void requestLeaveConfirmation();
    };

    window.addEventListener(
      BEFORE_CLOSE_DOCUMENT_VIEWER_EVENT,
      handleBeforeClose,
    );
    return () => {
      window.removeEventListener(
        BEFORE_CLOSE_DOCUMENT_VIEWER_EVENT,
        handleBeforeClose,
      );
    };
  }, [isDirty, mode, requestLeaveConfirmation]);

  React.useEffect(() => {
    if (!isEnabled) {
      setState({ status: "disabled" });
      return;
    }

    let cancelled = false;
    let editorReady = false;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    // Total timeout for the entire initialization process
    timeoutId = setTimeout(() => {
      if (!cancelled && !editorReady) {
        setState({ status: "error", kind: "timeout" });
      }
    }, TOTAL_TIMEOUT_MS);

    const clearTimer = () => {
      if (timeoutId !== undefined) {
        clearTimeout(timeoutId);
        timeoutId = undefined;
      }
    };

    const init = async () => {
      try {
        setState({ status: "loading" });
        // 1) Check file size limit via HEAD request with fresh URL
        const freshFile = ensureFreshFile ? await ensureFreshFile(file) : file;
        const probeUrl = ensureAbsoluteUrl(freshFile?.url ?? file.url);
        if (probeUrl) {
          const fileSize = await probeFileSize(probeUrl);
          if (cancelled) return;
          if (fileSize !== null && fileSize > OFFICE_FILE_SIZE_LIMIT) {
            clearTimer();
            setState({ status: "error", kind: "tooLarge" });
            return;
          }
        }

        // 2) Fetch viewer config from backend (backend resolves presigned URL)
        if (!sessionId) {
          clearTimer();
          setState({ status: "error", kind: "generic" });
          return;
        }
        const ext = extractExtension(file);
        const config = await apiClient.post<OfficeViewerConfig>(
          API_ENDPOINTS.officeViewerConfig,
          {
            session_id: sessionId,
            file_path: file.path,
            file_type: ext || undefined,
            language: mapEditorLang(
              typeof document !== "undefined"
                ? document.documentElement.lang || "en"
                : "en",
            ),
            mode,
            edit_session_id:
              mode === "edit" ? editSessionIdRef.current : undefined,
          },
        );
        if (cancelled) return;
        if (config.edit_session_id) {
          setEditSessionId(config.edit_session_id);
        }

        // 4) Load OnlyOffice api.js
        await loadOnlyOfficeApiJs();
        if (cancelled) return;

        if (!window.DocsAPI) {
          throw new Error("DocsAPI not available after script load");
        }

        // 5) Initialize DocEditor
        if (!containerRef.current) return;

        containerRef.current.innerHTML = "";
        const placeholder = document.createElement("div");
        placeholder.id = placeholderDomId;
        placeholder.style.width = "100%";
        placeholder.style.height = "100%";
        containerRef.current.appendChild(placeholder);

        // Reset timeout: wait for OnlyOffice onDocumentReady (not ctor return)
        clearTimer();
        timeoutId = setTimeout(() => {
          if (!cancelled && !editorReady) {
            setState({ status: "error", kind: "timeout" });
          }
        }, EDITOR_RENDER_TIMEOUT_MS);

        editorRef.current = new window.DocsAPI.DocEditor(placeholderDomId, {
          document: config.document,
          documentType: config.documentType,
          editorConfig: config.editorConfig,
          token: config.token,
          type: config.type ?? "embedded",
          width: "100%",
          height: "100%",
          events: {
            onDocumentReady: () => {
              if (cancelled) return;
              editorReady = true;
              clearTimer();
              setState({ status: "ready" });
            },
            onDocumentStateChange: (event: { data?: boolean }) => {
              if (cancelled) return;
              setIsDirty(Boolean(event?.data));
              if (event?.data) {
                setSaveState("idle");
              }
            },
            onError: () => {
              if (!cancelled) {
                clearTimer();
                setState({ status: "error", kind: "editor" });
              }
            },
          },
        });
      } catch (err) {
        if (cancelled) return;
        clearTimer();
        if (IS_DEV) {
          console.error("[OfficeIframeViewer] init failed", err);
        }
        // Map backend "too large" rejections to the dedicated error kind
        const kind: OfficeViewerErrorKind =
          err instanceof ApiError &&
          err.statusCode === 400 &&
          /too large/i.test(err.message)
            ? "tooLarge"
            : "generic";
        setState({ status: "error", kind });
      }
    };

    void init();

    return () => {
      cancelled = true;
      clearTimer();
      try {
        editorRef.current?.destroyEditor?.();
      } catch {
        // ignore cleanup errors
      }
      editorRef.current = null;
    };
  }, [
    file,
    sessionId,
    isEnabled,
    ensureFreshFile,
    placeholderDomId,
    mode,
  ]);

  const resolvedUrl = ensureAbsoluteUrl(file.url);

  const handleDownload = async () => {
    const refreshed = ensureFreshFile ? await ensureFreshFile(file) : file;
    await downloadFileFromUrl({
      url: refreshed?.url ?? resolvedUrl,
      filename: refreshed?.name || refreshed?.path || "document",
    });
  };

  const handleOpenNewWindow = async () => {
    const refreshed = ensureFreshFile ? await ensureFreshFile(file) : file;
    const url = ensureAbsoluteUrl(refreshed?.url ?? resolvedUrl);
    if (url) {
      window.open(url, "_blank", "noopener,noreferrer");
    }
  };

  const pollSaveStatus = React.useCallback(
    async (saveRequestId: string): Promise<OfficeSaveStatusResponse> => {
      if (!sessionId) {
        throw new Error("Missing session id");
      }
      const params = new URLSearchParams({
        session_id: sessionId,
        save_request_id: saveRequestId,
      });

      for (let attempt = 0; attempt < 60; attempt += 1) {
        const result = await apiClient.get<OfficeSaveStatusResponse>(
          `${API_ENDPOINTS.officeSaveStatus}?${params.toString()}`,
        );
        if (result.status === "saved" || result.status === "failed") {
          return result;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }

      return {
        save_request_id: saveRequestId,
        status: "failed",
        error_code: "client_poll_timeout",
      };
    },
    [sessionId],
  );

  const handleEdit = React.useCallback(() => {
    setMode("edit");
    setSaveState("idle");
  }, []);

  const forceWorkspaceSave = React.useCallback(async () => {
    if (!sessionId) {
      throw new Error("missing_session_id");
    }
    if (!editSessionId) {
      throw new Error("missing_edit_session_id");
    }
    if (saveState === "saving") {
      throw new Error("save_in_progress");
    }
    setSaveState("saving");
    let saveRequestId: string;
    try {
      const result = await apiClient.post<OfficeForceSaveResponse>(
        API_ENDPOINTS.officeForceSave,
        {
          session_id: sessionId,
          file_path: file.path,
          edit_session_id: editSessionId,
        },
      );
      saveRequestId = result.save_request_id;
    } catch (error) {
      const activeSaveRequestId = getActiveSaveRequestId(error);
      if (!activeSaveRequestId) {
        throw error;
      }
      saveRequestId = activeSaveRequestId;
    }
    const status = await pollSaveStatus(saveRequestId);
    if (status.status !== "saved") {
      throw new Error(status.error_code ?? "save_failed");
    }
    setIsDirty(false);
    setSaveState("saved");
    if (!ensureFreshFile) return file;
    return (await ensureFreshFile(file, { force: true })) ?? file;
  }, [
    editSessionId,
    ensureFreshFile,
    file,
    pollSaveStatus,
    saveState,
    sessionId,
  ]);

  const handleSave = React.useCallback(async () => {
    try {
      await forceWorkspaceSave();
      toast.success(t("artifacts.viewer.office.saveSuccess"));
    } catch (error) {
      if (IS_DEV) {
        console.error("[OfficeIframeViewer] save failed", error);
      }
      setSaveState("failed");
      toast.error(t("artifacts.viewer.office.saveFailed"));
    }
  }, [forceWorkspaceSave, t]);

  const handleSaveAs = React.useCallback(async () => {
    if (isSaveAsRunning) return;
    setIsSaveAsRunning(true);
    try {
      const refreshed = (await forceWorkspaceSave()) ?? file;
      const params = new URLSearchParams({
        session_id: sessionId ?? "",
        file_path: file.path,
      });
      const latest = await apiClient.get<OfficeDownloadLatestResponse>(
        `${API_ENDPOINTS.officeDownloadLatest}?${params.toString()}`,
      );
      const latestUrl = ensureAbsoluteUrl(latest.url);
      if (!latestUrl) {
        throw new Error("missing_latest_file_url");
      }
      const response = await fetch(latestUrl, {
        credentials: isSameOriginUrl(latestUrl) ? "include" : "omit",
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const blob = await response.blob();
      await saveBlobLocally(blob, refreshed.name || file.name || "document");
      toast.success(t("artifacts.viewer.office.saveAsSuccess"));
    } catch (error) {
      if (IS_DEV) {
        console.error("[OfficeIframeViewer] save as failed", error);
      }
      toast.error(t("artifacts.viewer.office.saveAsFailed"));
    } finally {
      setIsSaveAsRunning(false);
    }
  }, [file, forceWorkspaceSave, isSaveAsRunning, sessionId, t]);

  const handleDiscardChanges = React.useCallback(async () => {
    if (!window.confirm(t("artifacts.viewer.office.unsavedDescription"))) {
      return;
    }
    try {
      await discardEditSession();
    } catch (error) {
      if (IS_DEV) {
        console.error("[OfficeIframeViewer] discard failed", error);
      }
      toast.error(t("artifacts.viewer.office.discardFailed"));
    }
  }, [discardEditSession, t]);

  // Fallback UI (disabled / error)
  if (state.status === "disabled" || state.status === "error") {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-4 p-8 text-center">
        <div className="rounded-full bg-muted p-4 opacity-50">
          <FileWarning className="size-10 text-muted-foreground" />
        </div>
        <h3 className="text-base font-semibold">
          {state.status === "disabled"
            ? t("artifacts.viewer.office.disabled")
            : t("artifacts.viewer.office.error")}
        </h3>
        {state.status === "error" && (
          <p className="max-w-xs text-xs text-muted-foreground">
            {
              (
                {
                  timeout: t("artifacts.viewer.office.timeout"),
                  tooLarge: t("artifacts.viewer.office.tooLarge"),
                  editor: t("artifacts.viewer.office.editorError"),
                  generic: t("artifacts.viewer.office.genericHint"),
                } satisfies Record<OfficeViewerErrorKind, string>
              )[state.kind]
            }
          </p>
        )}
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={() => void handleOpenNewWindow()}
          >
            <ExternalLink className="size-4" />
            {t("artifacts.viewer.openInNewWindow")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={() => void handleDownload()}
          >
            <Download className="size-4" />
            {t("artifacts.viewer.downloadOriginal")}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />
      {state.status === "ready" && (
        <div className="absolute right-3 top-3 z-10 flex items-center gap-2 rounded-md border bg-background/95 px-2 py-2 shadow-sm">
          {mode === "view" ? (
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={handleEdit}
            >
              <Pencil className="size-4" />
              {t("artifacts.viewer.office.edit")}
            </Button>
          ) : (
            <>
              <span className="px-1 text-xs text-muted-foreground">
                {saveState === "saving"
                  ? t("artifacts.viewer.office.saving")
                  : isDirty
                    ? t("artifacts.viewer.office.dirty")
                    : t("artifacts.viewer.office.saved")}
              </span>
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={() => void handleSave()}
                disabled={!isDirty || saveState === "saving" || isSaveAsRunning}
              >
                <Save className="size-4" />
                {t("artifacts.viewer.office.save")}
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={() => void handleSaveAs()}
                disabled={saveState === "saving" || isSaveAsRunning}
              >
                <Download className="size-4" />
                {t("artifacts.viewer.office.saveAs")}
              </Button>
              {isDirty && (
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-2"
                  onClick={() => void handleDiscardChanges()}
                  disabled={saveState === "saving" || isSaveAsRunning}
                >
                  <Undo2 className="size-4" />
                  {t("artifacts.viewer.office.discardChanges")}
                </Button>
              )}
            </>
          )}
        </div>
      )}
      <AlertDialog
        open={isLeaveDialogOpen}
        onOpenChange={(open) => {
          if (!open && isLeaveDialogOpen) {
            settleLeaveConfirmation(false);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("artifacts.viewer.office.unsavedTitle")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("artifacts.viewer.office.unsavedDescription")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel
              disabled={isDiscardingForLeave}
              onClick={() => settleLeaveConfirmation(false)}
            >
              {t("artifacts.viewer.office.stay")}
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={isDiscardingForLeave}
              onClick={(event) => {
                event.preventDefault();
                void confirmLeaveAndDiscard();
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t("artifacts.viewer.office.discardAndLeave")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      {state.status === "loading" && (
        <div
          role="status"
          aria-live="polite"
          className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-3 bg-background/70"
        >
          <Loader2 className="size-8 animate-spin text-muted-foreground" />
          <span className="text-sm text-muted-foreground">
            {t("artifacts.viewer.office.loading")}
          </span>
        </div>
      )}
    </div>
  );
}
