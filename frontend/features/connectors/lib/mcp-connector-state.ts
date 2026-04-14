import type {
  McpServer,
  UserMcpInstall,
} from "@/features/capabilities/mcp/types";
import type { Connector } from "@/features/connectors/constants/connectors";

export interface McpRunConnection {
  id: string;
  run_id: string;
  session_id: string;
  server_id: number | null;
  server_name: string;
  state: string;
  health: string | null;
  attempt_count: number;
  last_error: string | null;
  connection_metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export type ConnectorCatalogState =
  | "connected"
  | "launching"
  | "failed"
  | "enabled"
  | "disabled"
  | "available"
  | "unavailable"
  | "coming-soon";

export interface ConnectorCatalogItem extends Connector {
  server: McpServer | null;
  install: UserMcpInstall | null;
  runtimeConnection: McpRunConnection | null;
  state: ConnectorCatalogState;
  isConnectable: boolean;
}

export function buildConnectorCatalog(
  connectors: Connector[],
  servers: McpServer[],
  installs: UserMcpInstall[],
  runtimeConnections: McpRunConnection[],
): ConnectorCatalogItem[] {
  return connectors.map((connector) => {
    if (connector.type !== "mcp") {
      return {
        ...connector,
        server: null,
        install: null,
        runtimeConnection: null,
        state: "coming-soon",
        isConnectable: false,
      };
    }

    const server = findMatchingServer(connector, servers);
    const install =
      server === null
        ? null
        : (installs.find((entry) => entry.server_id === server.id) ?? null);
    const runtimeConnection =
      server === null
        ? null
        : findRuntimeConnection(server, runtimeConnections);

    return {
      ...connector,
      server,
      install,
      runtimeConnection,
      state: deriveConnectorState(server, install, runtimeConnection),
      isConnectable: server !== null,
    };
  });
}

function deriveConnectorState(
  server: McpServer | null,
  install: UserMcpInstall | null,
  runtimeConnection: McpRunConnection | null,
): ConnectorCatalogState {
  if (runtimeConnection?.state === "connected") {
    return "connected";
  }
  if (
    runtimeConnection?.state === "requested" ||
    runtimeConnection?.state === "staged" ||
    runtimeConnection?.state === "launching"
  ) {
    return "launching";
  }
  if (runtimeConnection?.state === "failed") {
    return "failed";
  }
  if (install?.enabled) {
    return "enabled";
  }
  if (install) {
    return "disabled";
  }
  if (server) {
    return "available";
  }
  return "unavailable";
}

function findMatchingServer(
  connector: Connector,
  servers: McpServer[],
): McpServer | null {
  const connectorKeys = getConnectorKeys(connector);

  for (const server of servers) {
    const serverKeys = getServerKeys(server);
    if (serverKeys.some((key) => connectorKeys.includes(key))) {
      return server;
    }
  }

  return null;
}

function findRuntimeConnection(
  server: McpServer,
  runtimeConnections: McpRunConnection[],
): McpRunConnection | null {
  const serverKeys = getServerKeys(server);

  for (const connection of runtimeConnections) {
    if (serverKeys.includes(normalizeConnectorKey(connection.server_name))) {
      return connection;
    }
  }

  return null;
}

function getConnectorKeys(connector: Connector): string[] {
  return uniqueKeys([connector.id, connector.title]);
}

function getServerKeys(server: McpServer): string[] {
  const configKey = extractServerConfigKey(server.server_config);
  return uniqueKeys([server.name, configKey]);
}

function uniqueKeys(values: Array<string | null | undefined>): string[] {
  const keys = values
    .map((value) => normalizeConnectorKey(value))
    .filter(Boolean);
  return [...new Set(keys)];
}

function extractServerConfigKey(
  serverConfig: Record<string, unknown>,
): string | null {
  const mcpServers = serverConfig?.mcpServers;
  if (
    !mcpServers ||
    typeof mcpServers !== "object" ||
    Array.isArray(mcpServers)
  ) {
    return null;
  }

  const keys = Object.keys(mcpServers);
  if (keys.length !== 1) {
    return null;
  }

  return keys[0] ?? null;
}

export function normalizeConnectorKey(
  value: string | null | undefined,
): string {
  return (value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
}
