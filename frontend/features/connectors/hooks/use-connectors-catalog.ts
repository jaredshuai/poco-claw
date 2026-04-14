"use client";

import * as React from "react";
import { toast } from "sonner";

import { mcpService } from "@/features/capabilities/mcp/api/mcp-api";
import type { UserMcpInstall } from "@/features/capabilities/mcp/types";
import { chatService } from "@/features/chat/api/chat-api";
import { useT } from "@/lib/i18n/client";
import { invalidateStartupPreloadValues } from "@/lib/startup-preload";
import { API_ENDPOINTS, apiClient } from "@/services/api-client";
import { AVAILABLE_CONNECTORS } from "@/features/connectors/constants/connectors";
import { useCapabilityToggle } from "@/features/connectors/context/capability-toggle-context";
import {
  buildConnectorCatalog,
  type ConnectorCatalogItem,
  type McpRunConnection,
} from "@/features/connectors/lib/mcp-connector-state";

interface UseConnectorsCatalogOptions {
  open: boolean;
  sessionId?: string;
}

const ACTIVE_RUN_STATUSES = new Set(["queued", "claimed", "running"]);
const RUNTIME_POLL_INTERVAL_MS = 5_000;

export function useConnectorsCatalog({
  open,
  sessionId,
}: UseConnectorsCatalogOptions) {
  const { t } = useT("translation");
  const capabilityToggle = useCapabilityToggle();
  const [servers, setServers] = React.useState<
    Awaited<ReturnType<typeof mcpService.listServers>>
  >([]);
  const [installs, setInstalls] = React.useState<UserMcpInstall[]>([]);
  const [runtimeConnections, setRuntimeConnections] = React.useState<
    McpRunConnection[]
  >([]);
  const [isLoading, setIsLoading] = React.useState(false);
  const [pendingConnectorId, setPendingConnectorId] = React.useState<
    string | null
  >(null);

  const loadRuntimeConnections = React.useCallback(async () => {
    if (!sessionId) {
      setRuntimeConnections([]);
      return;
    }

    try {
      const runs = await chatService.getRunsBySession(sessionId, {
        limit: 1000,
        offset: 0,
      });
      const activeRun = [...(runs ?? [])]
        .filter((run) => ACTIVE_RUN_STATUSES.has(run.status))
        .sort(
          (left, right) =>
            new Date(right.created_at).getTime() -
            new Date(left.created_at).getTime(),
        )[0];

      if (!activeRun) {
        setRuntimeConnections([]);
        return;
      }

      const connections = await apiClient.get<McpRunConnection[]>(
        API_ENDPOINTS.runMcpConnections(activeRun.run_id),
        { cache: "no-store" },
      );
      setRuntimeConnections(connections ?? []);
    } catch (error) {
      console.error("[Connectors] Failed to fetch runtime MCP state:", error);
      setRuntimeConnections([]);
    }
  }, [sessionId]);

  const refresh = React.useCallback(async () => {
    setIsLoading(true);
    try {
      const [nextServers, nextInstalls] = await Promise.all([
        mcpService.listServers(),
        mcpService.listInstalls(),
      ]);
      setServers(nextServers);
      setInstalls(nextInstalls);
      await loadRuntimeConnections();
    } catch (error) {
      console.error("[Connectors] Failed to fetch connector catalog:", error);
      toast.error(t("library.mcpLibrary.toasts.error"));
    } finally {
      setIsLoading(false);
    }
  }, [loadRuntimeConnections, t]);

  React.useEffect(() => {
    if (!open) {
      return;
    }

    void refresh();

    if (!sessionId) {
      return;
    }

    const timer = window.setInterval(() => {
      void loadRuntimeConnections();
    }, RUNTIME_POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(timer);
    };
  }, [loadRuntimeConnections, open, refresh, sessionId]);

  const connectors = React.useMemo<ConnectorCatalogItem[]>(() => {
    return buildConnectorCatalog(
      AVAILABLE_CONNECTORS,
      servers,
      installs,
      runtimeConnections,
    );
  }, [installs, runtimeConnections, servers]);

  const toggleConnector = React.useCallback(
    async (connectorId: string) => {
      const connector = connectors.find((entry) => entry.id === connectorId);
      if (!connector || connector.type !== "mcp" || !connector.server) {
        return;
      }

      const nextEnabled = !(connector.install?.enabled ?? false);
      setPendingConnectorId(connectorId);

      try {
        let nextInstall: UserMcpInstall;

        if (connector.install) {
          nextInstall = await mcpService.updateInstall(connector.install.id, {
            enabled: nextEnabled,
          });
        } else {
          nextInstall = await mcpService.createInstall({
            server_id: connector.server.id,
            enabled: true,
          });
        }

        setInstalls((prev) => upsertInstall(prev, nextInstall));
        capabilityToggle?.toggleMcp(connector.server.id, nextInstall.enabled);
        invalidateStartupPreloadValues(["mcpInstalls"]);
      } catch (error) {
        console.error("[Connectors] Failed to toggle MCP connector:", error);
        toast.error(t("library.mcpLibrary.toasts.error"));
      } finally {
        setPendingConnectorId(null);
      }
    },
    [capabilityToggle, connectors, t],
  );

  return {
    connectors,
    isLoading,
    pendingConnectorId,
    refresh,
    toggleConnector,
  };
}

function upsertInstall(
  installs: UserMcpInstall[],
  nextInstall: UserMcpInstall,
): UserMcpInstall[] {
  const existingIndex = installs.findIndex(
    (item) => item.id === nextInstall.id,
  );
  if (existingIndex === -1) {
    return [...installs, nextInstall];
  }

  return installs.map((item) =>
    item.id === nextInstall.id ? nextInstall : item,
  );
}
