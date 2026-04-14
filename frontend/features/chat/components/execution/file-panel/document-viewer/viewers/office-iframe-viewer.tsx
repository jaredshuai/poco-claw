"use client";

import * as React from "react";
import { Download, ExternalLink, FileWarning, Loader2 } from "lucide-react";
import { useT } from "@/lib/i18n/client";
import { ApiError } from "@/lib/errors";
import { Button } from "@/components/ui/button";
import { apiClient, API_ENDPOINTS } from "@/services/api-client";
import type { FileNode } from "@/features/chat/types";
import {
  ensureAbsoluteUrl,
  downloadFileFromUrl,
  extractExtension,
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
  ensureFreshFile?: (file: FileNode) => Promise<FileNode | undefined>;
}

type ViewerState =
  | { status: "loading" }
  | { status: "ready" }
  | { status: "error"; kind: OfficeViewerErrorKind }
  | { status: "disabled" };

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
    const resp = await fetch(url, { method: "HEAD" });
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
  const [state, setState] = React.useState<ViewerState>({ status: "loading" });

  // Feature enabled only when env explicitly true and Document Server URL is set
  const isEnabled = OFFICE_VIEWER_ENABLED && Boolean(OFFICE_VIEWER_URL.trim());

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
          },
        );
        if (cancelled) return;

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
  }, [file, sessionId, isEnabled, ensureFreshFile, placeholderDomId]);

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
      {state.status === "loading" && (
        <div role="status" aria-live="polite" className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-3 bg-background/70">
          <Loader2 className="size-8 animate-spin text-muted-foreground" />
          <span className="text-sm text-muted-foreground">
            {t("artifacts.viewer.office.loading")}
          </span>
        </div>
      )}
    </div>
  );
}
