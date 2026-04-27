import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import type { FileNode } from "@/features/chat/types";

// ---------------------------------------------------------------------------
// Mocks — keep them lightweight so the routing logic can be exercised in
// isolation from the heavy viewer implementations.
// ---------------------------------------------------------------------------

vi.mock("@/lib/i18n/client", () => ({
  useT: () => ({ t: (key: string) => key }),
}));

vi.mock("next/dynamic", () => ({
  __esModule: true,
  default: () => {
    function DynamicStub() {
      return <div data-testid="dynamic-stub" />;
    }
    DynamicStub.displayName = "DynamicStub";
    return DynamicStub;
  },
}));

vi.mock("react-markdown", () => ({
  default: (props: Record<string, unknown>) => props.children,
}));
vi.mock("remark-gfm", () => ({ default: () => null }));
vi.mock("remark-breaks", () => ({ default: () => null }));
vi.mock("remark-math", () => ({ default: () => null }));
vi.mock("rehype-katex", () => ({ default: () => null }));

vi.mock("@/components/shared/markdown-code", () => ({
  MarkdownCode: (props: Record<string, unknown>) => props.children,
  MarkdownPre: (props: Record<string, unknown>) => props.children,
}));
vi.mock("@/components/shared/adaptive-markdown", () => ({
  AdaptiveMarkdown: (props: Record<string, unknown>) => props.children,
}));
vi.mock("@/lib/markdown/prism", () => ({
  SyntaxHighlighter: (props: Record<string, unknown>) => props.children,
  oneDark: {},
  oneLight: {},
}));

// ---------------------------------------------------------------------------
// Import after mocks are registered
// ---------------------------------------------------------------------------

import { DocumentViewer } from "@/features/chat/components/execution/file-panel/document-viewer";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const docxFile: FileNode = {
  id: "f1",
  name: "report.docx",
  type: "file",
  path: "report.docx",
  url: "https://example.com/report.docx",
  mimeType:
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
};

const pdfFile: FileNode = {
  id: "f2",
  name: "doc.pdf",
  type: "file",
  path: "doc.pdf",
  url: "https://example.com/doc.pdf",
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("DocumentViewer Office routing", () => {
  it("renders Office branch for docx when sessionId is present", () => {
    render(<DocumentViewer file={docxFile} sessionId="sess-1" />);

    // The toolbar subtitle shows the extension in uppercase
    expect(screen.getByText("DOCX")).toBeInTheDocument();
  });

  it("shows not-supported for docx without sessionId", () => {
    // Without sessionId the isOfficeFile && sessionId guard is false.
    // Office files are excluded from the text-viewer path, so they
    // fall all the way through to the "not supported" StatusLayout.
    render(<DocumentViewer file={docxFile} />);

    expect(screen.queryByText("DOCX")).not.toBeInTheDocument();
    expect(
      screen.getByText("artifacts.viewer.notSupported"),
    ).toBeInTheDocument();
  });

  it("shows not-supported for Office file without sessionId even without mimeType", () => {
    const noMimeFile: FileNode = {
      id: "f3",
      name: "report.docx",
      type: "file",
      path: "report.docx",
      url: "https://example.com/report.docx",
    };
    render(<DocumentViewer file={noMimeFile} />);

    expect(
      screen.getByText("artifacts.viewer.notSupported"),
    ).toBeInTheDocument();
  });

  it("routes PDF to docType branch, not Office", () => {
    render(<DocumentViewer file={pdfFile} sessionId="sess-1" />);

    expect(screen.getByText("PDF")).toBeInTheDocument();
    expect(screen.queryByText("DOCX")).not.toBeInTheDocument();
  });
});
