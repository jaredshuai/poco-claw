import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { FileNode } from "@/features/chat/types";
import { ApiError } from "@/lib/errors";

// ---------------------------------------------------------------------------
// Set env vars BEFORE module evaluation (vi.hoisted runs before imports)
// ---------------------------------------------------------------------------

vi.hoisted(() => {
  process.env.NEXT_PUBLIC_OFFICE_VIEWER_ENABLED = "true";
  process.env.NEXT_PUBLIC_OFFICE_VIEWER_URL = "http://localhost:8100";
});

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@/lib/i18n/client", () => ({
  useT: () => ({ t: (key: string) => key }),
}));

vi.mock("lucide-react", () => ({
  Download: () => null,
  ExternalLink: () => null,
  FileWarning: () => null,
  Loader2: () => null,
}));

vi.mock("@/components/ui/button", () => ({
  Button: (props: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props} />
  ),
}));

vi.mock("@/services/api-client", () => ({
  apiClient: {
    post: vi.fn(),
  },
  API_ENDPOINTS: { officeViewerConfig: "/office/viewer-config" },
}));

// ---------------------------------------------------------------------------
// Import after mocks
// ---------------------------------------------------------------------------

import { apiClient } from "@/services/api-client";
import { OfficeIframeViewer } from "@/features/chat/components/execution/file-panel/document-viewer/viewers/office-iframe-viewer";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const docxFile: FileNode = {
  id: "f1",
  name: "big.xlsx",
  type: "file",
  path: "big.xlsx",
  url: "https://example.com/big.xlsx",
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("OfficeIframeViewer tooLarge error handling", () => {
  it("shows tooLarge error when backend rejects with ApiError 400 'too large'", async () => {
    vi.mocked(apiClient.post).mockRejectedValueOnce(
      new ApiError("File is too large for preview (limit: 50 MB)", 400),
    );

    render(<OfficeIframeViewer file={docxFile} sessionId="sess-1" />);

    await waitFor(() => {
      expect(
        screen.getByText("artifacts.viewer.office.tooLarge"),
      ).toBeInTheDocument();
    });
  });

  it("shows generic error for non-too-large ApiError", async () => {
    vi.mocked(apiClient.post).mockRejectedValueOnce(
      new ApiError("Internal server error", 500),
    );

    render(<OfficeIframeViewer file={docxFile} sessionId="sess-1" />);

    await waitFor(() => {
      expect(
        screen.getByText("artifacts.viewer.office.genericHint"),
      ).toBeInTheDocument();
    });
  });

  it("shows generic error for non-ApiError exceptions", async () => {
    vi.mocked(apiClient.post).mockRejectedValueOnce(new Error("Network fail"));

    render(<OfficeIframeViewer file={docxFile} sessionId="sess-1" />);

    await waitFor(() => {
      expect(
        screen.getByText("artifacts.viewer.office.genericHint"),
      ).toBeInTheDocument();
    });
  });
});
