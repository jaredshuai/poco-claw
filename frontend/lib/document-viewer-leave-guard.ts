export const BEFORE_CLOSE_DOCUMENT_VIEWER_EVENT =
  "before-close-document-viewer";

export interface BeforeCloseDocumentViewerEventDetail {
  waitUntil: (decision: boolean | Promise<boolean>) => void;
}

export type BeforeCloseDocumentViewerEvent =
  CustomEvent<BeforeCloseDocumentViewerEventDetail>;

export async function canLeaveDocumentViewer(): Promise<boolean> {
  if (typeof window === "undefined") return true;

  const decisions: Array<Promise<boolean>> = [];
  const event = new CustomEvent<BeforeCloseDocumentViewerEventDetail>(
    BEFORE_CLOSE_DOCUMENT_VIEWER_EVENT,
    {
      cancelable: true,
      detail: {
        waitUntil: (decision) => {
          decisions.push(Promise.resolve(decision));
        },
      },
    },
  );

  window.dispatchEvent(event);
  if (event.defaultPrevented) return false;
  if (decisions.length === 0) return true;

  const results = await Promise.all(decisions);
  return results.every(Boolean);
}
