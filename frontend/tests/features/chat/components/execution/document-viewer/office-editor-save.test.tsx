import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { FileNode } from "@/features/chat/types";
import { ApiError } from "@/lib/errors";

vi.hoisted(() => {
  process.env.NEXT_PUBLIC_OFFICE_VIEWER_ENABLED = "true";
  process.env.NEXT_PUBLIC_OFFICE_VIEWER_URL = "http://localhost:8100";
});

vi.mock("@/lib/i18n/client", () => ({
  useT: () => ({ t: (key: string) => key }),
}));

vi.mock("lucide-react", () => ({
  Download: () => null,
  ExternalLink: () => null,
  FileWarning: () => null,
  Loader2: () => null,
  Save: () => null,
  Pencil: () => null,
  Undo2: () => null,
}));

vi.mock("@/components/ui/button", () => ({
  Button: (props: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props} />
  ),
}));

vi.mock("@/components/ui/alert-dialog", () => ({
  AlertDialog: ({
    open,
    children,
  }: {
    open?: boolean;
    children: React.ReactNode;
  }) => (open ? <div role="alertdialog">{children}</div> : null),
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => (
    <h2>{children}</h2>
  ),
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => (
    <p>{children}</p>
  ),
  AlertDialogAction: (props: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props} />
  ),
  AlertDialogCancel: (props: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props} />
  ),
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("@/services/api-client", () => ({
  apiClient: {
    post: vi.fn(),
    get: vi.fn(),
  },
  API_ENDPOINTS: {
    officeViewerConfig: "/office/viewer-config",
    officeForceSave: "/office/forcesave",
    officeSaveStatus: "/office/save-status",
    officeDiscardEditSession: "/office/edit-session/discard",
    officeDownloadLatest: "/office/download-latest",
  },
}));

import { toast } from "sonner";
import { apiClient } from "@/services/api-client";
import { canLeaveDocumentViewer } from "@/lib/document-viewer-leave-guard";
import { OfficeIframeViewer } from "@/features/chat/components/execution/file-panel/document-viewer/viewers/office-iframe-viewer";

const file: FileNode = {
  id: "f1",
  name: "report.docx",
  type: "file",
  path: "report.docx",
  url: "https://example.com/report.docx",
};

function viewerConfig(mode: "view" | "edit") {
  return {
    document: {
      fileType: "docx",
      key: mode === "edit" ? "doc-key-edit" : "doc-key-view",
      title: "report.docx",
      url: "https://example.com/report.docx",
    },
    documentType: "word",
    editorConfig: {
      mode,
      lang: "en",
      callbackUrl:
        mode === "edit"
          ? "http://localhost:8000/api/v1/office/callback?token=abc"
          : undefined,
    },
    token: "jwt",
    type: "embedded",
    edit_session_id: mode === "edit" ? "edit-session-1" : undefined,
  };
}

describe("OfficeIframeViewer editing save flow", () => {
  let latestEvents: Record<string, (payload?: unknown) => void>;

  beforeEach(() => {
    latestEvents = {};
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(toast.success).mockReset();
    vi.mocked(toast.error).mockReset();

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers(),
    } as Response);

    window.DocsAPI = {
      DocEditor: vi.fn(function (
        _elementId: string,
        config: Record<string, unknown>,
      ) {
        latestEvents = config.events as Record<
          string,
          (payload?: unknown) => void
        >;
        queueMicrotask(() => latestEvents.onDocumentReady?.());
        return { destroyEditor: vi.fn() };
      }),
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
    delete window.DocsAPI;
    delete (window as Window & { poco?: unknown }).poco;
    delete (window as Window & { showSaveFilePicker?: unknown })
      .showSaveFilePicker;
  });

  it("forcesaves dirty edit content and shows success only after save-status is saved", async () => {
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce(viewerConfig("view"))
      .mockResolvedValueOnce(viewerConfig("edit"))
      .mockResolvedValueOnce({
        save_request_id: "save-request-1",
        status: "saving",
        poll_after_ms: 1,
      });
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      save_request_id: "save-request-1",
      status: "saved",
      error_code: null,
      error_message: null,
      completed_at: "2026-04-26T00:00:00Z",
    });
    const ensureFreshFile = vi.fn().mockResolvedValue(file);
    const user = userEvent.setup();

    render(
      <OfficeIframeViewer
        file={file}
        sessionId="00000000-0000-0000-0000-000000000001"
        ensureFreshFile={ensureFreshFile}
      />,
    );

    await screen.findByText("artifacts.viewer.office.edit");
    await user.click(screen.getByText("artifacts.viewer.office.edit"));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/office/viewer-config",
        expect.objectContaining({
          mode: "edit",
          file_path: "report.docx",
        }),
      );
    });

    latestEvents.onDocumentStateChange?.({ data: true });
    await user.click(screen.getByText("artifacts.viewer.office.save"));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/office/forcesave",
        {
          session_id: "00000000-0000-0000-0000-000000000001",
          file_path: "report.docx",
          edit_session_id: "edit-session-1",
        },
      );
    });
    expect(apiClient.get).toHaveBeenCalledWith(
      "/office/save-status?session_id=00000000-0000-0000-0000-000000000001&save_request_id=save-request-1",
    );
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        "artifacts.viewer.office.saveSuccess",
      );
    });
    expect(ensureFreshFile).toHaveBeenCalledWith(file, { force: true });
  });

  it("continues polling the active save request when forcesave reports save_in_progress", async () => {
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce(viewerConfig("view"))
      .mockResolvedValueOnce(viewerConfig("edit"))
      .mockRejectedValueOnce(
        new ApiError("save_in_progress", 409, {
          data: {
            active_save_request_id: "active-save-request-1",
          },
        }),
      );
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      save_request_id: "active-save-request-1",
      status: "saved",
      error_code: null,
      error_message: null,
      completed_at: "2026-04-26T00:00:00Z",
    });
    const ensureFreshFile = vi.fn().mockResolvedValue(file);
    const user = userEvent.setup();

    render(
      <OfficeIframeViewer
        file={file}
        sessionId="00000000-0000-0000-0000-000000000001"
        ensureFreshFile={ensureFreshFile}
      />,
    );

    await screen.findByText("artifacts.viewer.office.edit");
    await user.click(screen.getByText("artifacts.viewer.office.edit"));
    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/office/viewer-config",
        expect.objectContaining({ mode: "edit" }),
      );
    });

    latestEvents.onDocumentStateChange?.({ data: true });
    await user.click(screen.getByText("artifacts.viewer.office.save"));

    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledWith(
        "/office/save-status?session_id=00000000-0000-0000-0000-000000000001&save_request_id=active-save-request-1",
      );
    });
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        "artifacts.viewer.office.saveSuccess",
      );
    });
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("save as forcesaves first, refreshes latest file, and downloads the refreshed blob", async () => {
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce(viewerConfig("view"))
      .mockResolvedValueOnce(viewerConfig("edit"))
      .mockResolvedValueOnce({
        save_request_id: "save-as-request-1",
        status: "saving",
        poll_after_ms: 1,
      });
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      save_request_id: "save-as-request-1",
      status: "saved",
      error_code: null,
      error_message: null,
      completed_at: "2026-04-26T00:00:00Z",
    }).mockResolvedValueOnce({
      url: "https://example.com/report-latest.docx",
      file_path: "report.docx",
      expires_in: 600,
    });
    const ensureFreshFile = vi.fn().mockResolvedValue(file);
    const user = userEvent.setup();

    const click = vi.fn();
    vi.spyOn(document, "createElement").mockImplementation((tagName: string) => {
      const element = document.createElementNS(
        "http://www.w3.org/1999/xhtml",
        tagName,
      ) as HTMLElement;
      if (tagName === "a") {
        Object.defineProperty(element, "click", {
          configurable: true,
          value: click,
        });
      }
      return element;
    });
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:latest");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    vi.mocked(global.fetch).mockImplementation(async (_input, init) => {
      if (init?.method === "HEAD") {
        return {
          ok: true,
          headers: new Headers(),
        } as Response;
      }
      return {
        ok: true,
        blob: async () =>
          new Blob(["latest"], {
            type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          }),
      } as Response;
    });

    render(
      <OfficeIframeViewer
        file={file}
        sessionId="00000000-0000-0000-0000-000000000001"
        ensureFreshFile={ensureFreshFile}
      />,
    );

    await screen.findByText("artifacts.viewer.office.edit");
    await user.click(screen.getByText("artifacts.viewer.office.edit"));
    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/office/viewer-config",
        expect.objectContaining({ mode: "edit" }),
      );
    });

    latestEvents.onDocumentStateChange?.({ data: true });
    await user.click(screen.getByText("artifacts.viewer.office.saveAs"));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/office/forcesave",
        {
          session_id: "00000000-0000-0000-0000-000000000001",
          file_path: "report.docx",
          edit_session_id: "edit-session-1",
        },
      );
    });
    await waitFor(() => {
      expect(ensureFreshFile).toHaveBeenCalledWith(file, { force: true });
    });
    expect(apiClient.get).toHaveBeenCalledWith(
      "/office/download-latest?session_id=00000000-0000-0000-0000-000000000001&file_path=report.docx",
    );
    expect(global.fetch).toHaveBeenLastCalledWith(
      "https://example.com/report-latest.docx",
      { credentials: "omit" },
    );
    expect(click).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith(
      "artifacts.viewer.office.saveAsSuccess",
    );
  });

  it("uses desktop native save adapter before browser save fallbacks", async () => {
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce(viewerConfig("view"))
      .mockResolvedValueOnce(viewerConfig("edit"))
      .mockResolvedValueOnce({
        save_request_id: "native-save-request-1",
        status: "saving",
        poll_after_ms: 1,
      });
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({
        save_request_id: "native-save-request-1",
        status: "saved",
        error_code: null,
        error_message: null,
        completed_at: "2026-04-27T00:00:00Z",
      })
      .mockResolvedValueOnce({
        url: "https://example.com/report-latest.docx",
        file_path: "report.docx",
        expires_in: 600,
      });
    const ensureFreshFile = vi.fn().mockResolvedValue(file);
    const nativeSaveFile = vi.fn().mockResolvedValue(undefined);
    const showSaveFilePicker = vi.fn().mockResolvedValue({
      createWritable: vi.fn().mockResolvedValue({
        write: vi.fn(),
        close: vi.fn(),
      }),
    });
    (window as Window & { poco?: { saveFile: typeof nativeSaveFile } }).poco =
      { saveFile: nativeSaveFile };
    (
      window as Window & { showSaveFilePicker?: typeof showSaveFilePicker }
    ).showSaveFilePicker = showSaveFilePicker;
    vi.mocked(global.fetch).mockImplementation(async (_input, init) => {
      if (init?.method === "HEAD") {
        return {
          ok: true,
          headers: new Headers(),
        } as Response;
      }
      return {
        ok: true,
        blob: async () =>
          new Blob(["latest"], {
            type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          }),
      } as Response;
    });
    const user = userEvent.setup();

    render(
      <OfficeIframeViewer
        file={file}
        sessionId="00000000-0000-0000-0000-000000000001"
        ensureFreshFile={ensureFreshFile}
      />,
    );

    await screen.findByText("artifacts.viewer.office.edit");
    await user.click(screen.getByText("artifacts.viewer.office.edit"));
    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/office/viewer-config",
        expect.objectContaining({ mode: "edit" }),
      );
    });

    latestEvents.onDocumentStateChange?.({ data: true });
    await user.click(screen.getByText("artifacts.viewer.office.saveAs"));

    await waitFor(() => {
      expect(nativeSaveFile).toHaveBeenCalledWith(
        expect.objectContaining({
          suggestedName: "report.docx",
          mimeType:
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          data: expect.any(ArrayBuffer),
        }),
      );
    });
    expect(showSaveFilePicker).not.toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith(
      "artifacts.viewer.office.saveAsSuccess",
    );
  });

  it("prompts before browser unload while edit content is dirty", async () => {
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce(viewerConfig("view"))
      .mockResolvedValueOnce(viewerConfig("edit"));
    const user = userEvent.setup();

    render(
      <OfficeIframeViewer
        file={file}
        sessionId="00000000-0000-0000-0000-000000000001"
        ensureFreshFile={vi.fn().mockResolvedValue(file)}
      />,
    );

    await screen.findByText("artifacts.viewer.office.edit");
    await user.click(screen.getByText("artifacts.viewer.office.edit"));
    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/office/viewer-config",
        expect.objectContaining({ mode: "edit" }),
      );
    });

    latestEvents.onDocumentStateChange?.({ data: true });

    await waitFor(() => {
      const event = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(event);
      expect(event.defaultPrevented).toBe(true);
    });
  });

  it("uses a custom dialog to block in-app viewer close when dirty changes are not confirmed", async () => {
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce(viewerConfig("view"))
      .mockResolvedValueOnce(viewerConfig("edit"));
    const confirm = vi.spyOn(window, "confirm");
    const user = userEvent.setup();

    render(
      <OfficeIframeViewer
        file={file}
        sessionId="00000000-0000-0000-0000-000000000001"
        ensureFreshFile={vi.fn().mockResolvedValue(file)}
      />,
    );

    await screen.findByText("artifacts.viewer.office.edit");
    await user.click(screen.getByText("artifacts.viewer.office.edit"));
    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/office/viewer-config",
        expect.objectContaining({ mode: "edit" }),
      );
    });

    await act(async () => {
      latestEvents.onDocumentStateChange?.({ data: true });
    });
    await screen.findByText("artifacts.viewer.office.dirty");

    let leavePromise!: Promise<boolean>;
    await act(async () => {
      leavePromise = Promise.resolve(canLeaveDocumentViewer());
    });
    const dialog = await screen.findByRole("alertdialog");

    expect(dialog).toHaveTextContent("artifacts.viewer.office.unsavedTitle");
    expect(dialog).toHaveTextContent(
      "artifacts.viewer.office.unsavedDescription",
    );
    expect(confirm).not.toHaveBeenCalled();

    await user.click(screen.getByText("artifacts.viewer.office.stay"));

    await expect(leavePromise).resolves.toBe(false);
    expect(apiClient.post).not.toHaveBeenCalledWith(
      "/office/edit-session/discard",
      expect.anything(),
    );
  });

  it("discards dirty edit session and returns to view mode", async () => {
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce(viewerConfig("view"))
      .mockResolvedValueOnce(viewerConfig("edit"))
      .mockResolvedValueOnce({
        edit_session_id: "edit-session-1",
        status: "discarded",
      })
      .mockResolvedValueOnce(viewerConfig("view"));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();

    render(
      <OfficeIframeViewer
        file={file}
        sessionId="00000000-0000-0000-0000-000000000001"
        ensureFreshFile={vi.fn().mockResolvedValue(file)}
      />,
    );

    await screen.findByText("artifacts.viewer.office.edit");
    await user.click(screen.getByText("artifacts.viewer.office.edit"));
    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/office/viewer-config",
        expect.objectContaining({ mode: "edit" }),
      );
    });

    latestEvents.onDocumentStateChange?.({ data: true });
    await screen.findByText("artifacts.viewer.office.discardChanges");
    await user.click(screen.getByText("artifacts.viewer.office.discardChanges"));

    expect(confirm).toHaveBeenCalledWith(
      "artifacts.viewer.office.unsavedDescription",
    );
    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/office/edit-session/discard",
        {
          session_id: "00000000-0000-0000-0000-000000000001",
          file_path: "report.docx",
          edit_session_id: "edit-session-1",
        },
      );
    });
    await screen.findByText("artifacts.viewer.office.edit");
  });

  it("does not download stale content when edit session is missing", async () => {
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce(viewerConfig("view"))
      .mockResolvedValueOnce({
        ...viewerConfig("edit"),
        edit_session_id: undefined,
      });
    const click = vi.fn();
    vi.spyOn(document, "createElement").mockImplementation((tagName: string) => {
      const element = document.createElementNS(
        "http://www.w3.org/1999/xhtml",
        tagName,
      ) as HTMLElement;
      if (tagName === "a") {
        Object.defineProperty(element, "click", {
          configurable: true,
          value: click,
        });
      }
      return element;
    });
    const user = userEvent.setup();

    render(
      <OfficeIframeViewer
        file={file}
        sessionId="00000000-0000-0000-0000-000000000001"
        ensureFreshFile={vi.fn().mockResolvedValue(file)}
      />,
    );

    await screen.findByText("artifacts.viewer.office.edit");
    await user.click(screen.getByText("artifacts.viewer.office.edit"));
    await screen.findByText("artifacts.viewer.office.saveAs");

    latestEvents.onDocumentStateChange?.({ data: true });
    await user.click(screen.getByText("artifacts.viewer.office.saveAs"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        "artifacts.viewer.office.saveAsFailed",
      );
    });
    expect(apiClient.post).not.toHaveBeenCalledWith(
      "/office/forcesave",
      expect.anything(),
    );
    expect(click).not.toHaveBeenCalled();
  });
});
