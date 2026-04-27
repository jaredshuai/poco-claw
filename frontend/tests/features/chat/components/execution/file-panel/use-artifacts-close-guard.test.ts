import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useArtifacts } from "@/features/chat/components/execution/file-panel/hooks/use-artifacts";
import type { FileNode } from "@/features/chat/types";

vi.mock("@/features/chat/actions/query-actions", () => ({
  getFilesAction: vi.fn(),
}));

import { getFilesAction } from "@/features/chat/actions/query-actions";

const reportFile: FileNode = {
  id: "report",
  name: "report.docx",
  path: "report.docx",
  type: "file",
  url: "https://example.com/report.docx",
};

const slidesFile: FileNode = {
  id: "slides",
  name: "slides.pptx",
  path: "slides.pptx",
  type: "file",
  url: "https://example.com/slides.pptx",
};

describe("useArtifacts close guard", () => {
  beforeEach(() => {
    vi.mocked(getFilesAction).mockReset();
    vi.mocked(getFilesAction).mockResolvedValue([reportFile, slidesFile]);
  });

  it("keeps the document open when close is prevented", async () => {
    const { result } = renderHook(() =>
      useArtifacts({ sessionId: "session-1" }),
    );

    await waitFor(() => {
      expect(result.current.files).toHaveLength(2);
    });

    act(() => {
      result.current.selectFile(reportFile);
    });
    expect(result.current.viewMode).toBe("document");

    const preventClose = (event: Event) => event.preventDefault();
    window.addEventListener("before-close-document-viewer", preventClose);
    try {
      act(() => {
        result.current.closeViewer();
      });
    } finally {
      window.removeEventListener("before-close-document-viewer", preventClose);
    }

    expect(result.current.viewMode).toBe("document");
    expect(result.current.selectedFile?.path).toBe("report.docx");
  });

  it("keeps the current file selected when switching files is prevented", async () => {
    const { result } = renderHook(() =>
      useArtifacts({ sessionId: "session-1" }),
    );

    await waitFor(() => {
      expect(result.current.files).toHaveLength(2);
    });

    act(() => {
      result.current.selectFile(reportFile);
    });
    expect(result.current.selectedFile?.path).toBe("report.docx");

    const preventClose = (event: Event) => event.preventDefault();
    window.addEventListener("before-close-document-viewer", preventClose);
    try {
      act(() => {
        result.current.selectFile(slidesFile);
      });
    } finally {
      window.removeEventListener("before-close-document-viewer", preventClose);
    }

    expect(result.current.viewMode).toBe("document");
    expect(result.current.selectedFile?.path).toBe("report.docx");
  });
});
