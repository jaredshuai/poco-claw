import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ConnectorsDialog } from "@/features/connectors/components/connectors/connectors-dialog";
import { mcpService } from "@/features/capabilities/mcp/api/mcp-api";
import { chatService } from "@/features/chat/api/chat-api";
import { apiClient } from "@/services/api-client";

vi.mock("@/features/capabilities/mcp/api/mcp-api", () => ({
  mcpService: {
    listServers: vi.fn(),
    listInstalls: vi.fn(),
    createInstall: vi.fn(),
    updateInstall: vi.fn(),
  },
}));

vi.mock("@/features/chat/api/chat-api", () => ({
  chatService: {
    getRunsBySession: vi.fn(),
  },
}));

vi.mock("@/services/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/services/api-client")>(
    "@/services/api-client",
  );

  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      get: vi.fn(),
    },
  };
});

describe("ConnectorsDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(mcpService.listServers).mockResolvedValue([
      {
        id: 1,
        name: "filesystem",
        description: "Local files",
        scope: "system",
        owner_user_id: null,
        server_config: {
          mcpServers: {
            filesystem: {
              type: "stdio",
              command: "npx",
            },
          },
        },
        created_at: "2026-04-04T00:00:00Z",
        updated_at: "2026-04-04T00:00:00Z",
      },
    ]);
    vi.mocked(mcpService.listInstalls).mockResolvedValue([]);
    vi.mocked(chatService.getRunsBySession).mockResolvedValue([]);
    vi.mocked(apiClient.get).mockResolvedValue([]);
  });

  it("creates a real MCP install and reflects enabled state", async () => {
    vi.mocked(mcpService.createInstall).mockResolvedValue({
      id: 10,
      user_id: "user-1",
      server_id: 1,
      enabled: true,
      created_at: "2026-04-04T00:00:00Z",
      updated_at: "2026-04-04T00:00:00Z",
    });

    const user = userEvent.setup();

    render(<ConnectorsDialog open onOpenChange={vi.fn()} defaultTab="mcp" />);

    const filesystemCard = await screen.findByRole("button", {
      name: /file system/i,
    });
    await user.click(filesystemCard);

    const enableButton = await screen.findByRole("button", { name: "Enable" });
    await user.click(enableButton);

    await waitFor(() => {
      expect(mcpService.createInstall).toHaveBeenCalledWith({
        server_id: 1,
        enabled: true,
      });
    });

    expect(
      await screen.findByRole("button", { name: "Disable" }),
    ).toBeInTheDocument();
  });

  it("shows active run MCP runtime state when session context exists", async () => {
    vi.mocked(mcpService.listInstalls).mockResolvedValue([
      {
        id: 10,
        user_id: "user-1",
        server_id: 1,
        enabled: true,
        created_at: "2026-04-04T00:00:00Z",
        updated_at: "2026-04-04T00:00:00Z",
      },
    ]);
    vi.mocked(chatService.getRunsBySession).mockResolvedValue([
      {
        run_id: "run-old",
        status: "completed",
        created_at: "2026-04-04T00:00:00Z",
      },
      {
        run_id: "run-active",
        status: "running",
        created_at: "2026-04-04T00:01:00Z",
      },
    ] as never);
    vi.mocked(apiClient.get).mockResolvedValue([
      {
        id: "conn-1",
        run_id: "run-active",
        session_id: "session-1",
        server_id: 1,
        server_name: "filesystem",
        state: "connected",
        health: "healthy",
        attempt_count: 1,
        last_error: null,
        connection_metadata: null,
        created_at: "2026-04-04T00:01:05Z",
        updated_at: "2026-04-04T00:01:06Z",
      },
    ]);

    const user = userEvent.setup();

    render(
      <ConnectorsDialog
        open
        onOpenChange={vi.fn()}
        defaultTab="mcp"
        sessionId="session-1"
      />,
    );

    const filesystemCard = await screen.findByRole("button", {
      name: /file system/i,
    });
    await user.click(filesystemCard);

    expect(await screen.findByText("Connected")).toBeInTheDocument();
    await waitFor(() => {
      expect(chatService.getRunsBySession).toHaveBeenCalledWith("session-1", {
        limit: 1000,
        offset: 0,
      });
      expect(apiClient.get).toHaveBeenCalled();
    });
  });
});
