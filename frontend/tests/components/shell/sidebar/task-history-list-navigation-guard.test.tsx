import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TaskHistoryList } from "@/components/shell/sidebar/task-history-list";
import { SidebarProvider } from "@/components/ui/sidebar";
import type { TaskHistoryItem } from "@/features/projects";

const { pushMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({}),
  useRouter: () => ({
    push: pushMock,
  }),
}));

vi.mock("@/hooks/use-language", () => ({
  useLanguage: () => "en",
}));

vi.mock("@/lib/i18n/client", () => ({
  useT: () => ({
    t: (key: string, defaultValue?: string) => defaultValue ?? key,
  }),
}));

vi.mock("@dnd-kit/core", () => ({
  useDraggable: () => ({
    listeners: {},
    setNodeRef: vi.fn(),
    isDragging: false,
  }),
}));

vi.mock("@/features/projects", async () => {
  const React = await import("react");
  return {
    RenameTaskDialog: () => null,
    TaskActionsDropdown: ({ children }: { children: React.ReactNode }) =>
      React.createElement(React.Fragment, null, children),
    TASK_STATUS_META: {
      pending: {
        dotClassName: "bg-muted-foreground/40",
        labelKey: "task.status.pending",
      },
      running: {
        dotClassName: "bg-primary",
        labelKey: "task.status.running",
      },
      completed: {
        dotClassName: "bg-primary",
        labelKey: "task.status.completed",
      },
      failed: {
        dotClassName: "bg-destructive",
        labelKey: "task.status.failed",
      },
      canceled: {
        dotClassName: "bg-chart-4/60",
        labelKey: "task.status.canceled",
      },
    },
  };
});

const task: TaskHistoryItem = {
  id: "task-1",
  title: "Quarterly report",
  status: "completed",
  timestamp: "2026-04-27T00:00:00.000Z",
};

function renderTaskHistoryList(onNavigate = vi.fn()) {
  render(
    <SidebarProvider>
      <TaskHistoryList
        tasks={[task]}
        pinnedTaskIds={[]}
        onDeleteTask={vi.fn()}
        projects={[]}
        onNavigate={onNavigate}
      />
    </SidebarProvider>,
  );
}

describe("TaskHistoryList document viewer navigation guard", () => {
  afterEach(() => {
    pushMock.mockReset();
  });

  it("keeps the current route when document viewer navigation is prevented", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    const preventClose = (event: Event) => event.preventDefault();

    renderTaskHistoryList(onNavigate);

    window.addEventListener("before-close-document-viewer", preventClose);
    try {
      await user.click(screen.getByText("Quarterly report"));
    } finally {
      window.removeEventListener("before-close-document-viewer", preventClose);
    }

    expect(pushMock).not.toHaveBeenCalled();
    expect(onNavigate).not.toHaveBeenCalled();
  });

  it("navigates when document viewer navigation is allowed", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();

    renderTaskHistoryList(onNavigate);

    await user.click(screen.getByText("Quarterly report"));

    expect(pushMock).toHaveBeenCalledWith("/en/chat/task-1");
    expect(onNavigate).toHaveBeenCalledTimes(1);
  });
});
