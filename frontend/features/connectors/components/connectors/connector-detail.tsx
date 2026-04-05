import { AlertCircle, Loader2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { useT } from "@/lib/i18n/client";
import { cn } from "@/lib/utils";
import type { ConnectorCatalogItem } from "@/features/connectors/lib/mcp-connector-state";

import { CapabilityFeature, DEFAULT_CAPABILITIES } from "./connector-card";

interface ConnectorDetailProps {
  connector: ConnectorCatalogItem;
  isPending?: boolean;
  onBack: () => void;
  onToggle: (connectorId: string) => void;
}

/**
 * Connector detail view
 * Shows connector info, install status, and runtime state for MCP connectors.
 */
export function ConnectorDetail({
  connector,
  isPending = false,
  onBack,
  onToggle,
}: ConnectorDetailProps) {
  const { t } = useT("translation");
  const statusLabel = getConnectorStateLabel(connector.state, t);
  const action = getConnectorAction(connector, t);
  const lastError = connector.runtimeConnection?.last_error?.trim() ?? "";

  return (
    <div className="flex h-full flex-1 animate-in fade-in slide-in-from-right-8 duration-300 flex-col">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-background/50 px-6 py-4 backdrop-blur-md">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={onBack}
            className="h-8 w-8 rounded-full p-0 hover:bg-accent"
          >
            <X className="size-4" />
          </Button>
          <span className="text-sm font-medium text-muted-foreground">
            {t("connectors.details")}
          </span>
        </div>
      </div>

      <ScrollArea className="flex-1">
        <div className="mx-auto max-w-3xl px-8 py-8">
          <div className="mb-8 flex items-center justify-between gap-6">
            <div className="flex items-center gap-5">
              <div
                className={cn(
                  "flex size-16 items-center justify-center rounded-xl border border-border bg-muted/50 shadow-lg transition-all duration-300",
                  connector.state === "connected" && "ring-2 ring-primary/40",
                )}
              >
                <connector.icon
                  className={cn(
                    "size-8 transition-colors duration-300",
                    connector.state === "connected"
                      ? "text-primary"
                      : "text-muted-foreground",
                  )}
                />
              </div>
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-xl font-bold tracking-tight">
                    {connector.title}
                  </h3>
                  <Badge
                    className={cn(
                      "h-5 rounded-full border px-2 py-0 text-[10px] font-semibold uppercase",
                      getConnectorBadgeClassName(connector.state),
                    )}
                  >
                    {statusLabel}
                  </Badge>
                </div>
                <p className="max-w-md text-sm text-muted-foreground">
                  {t(connector.descriptionKey)}
                </p>
              </div>
            </div>

            <Button
              onClick={() => onToggle(connector.id)}
              disabled={action.disabled || isPending}
              className={cn(
                "h-10 min-w-28 rounded-full px-6 text-sm font-semibold transition-all duration-300",
                action.destructive
                  ? "border border-border bg-background hover:bg-accent"
                  : "bg-primary text-primary-foreground hover:bg-primary/90",
              )}
              variant={action.destructive ? "outline" : "default"}
            >
              {isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                action.label
              )}
            </Button>
          </div>

          <div className="rounded-2xl border border-border/70 bg-muted/20 p-4">
            <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              {t("connectors.status")}
            </div>
            <p className="text-sm text-foreground">
              {t("connectors.status")}: {statusLabel}
            </p>
            {lastError ? (
              <div className="mt-3 flex items-start gap-2 rounded-xl border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive">
                <AlertCircle className="mt-0.5 size-4 shrink-0" />
                <div>
                  <div className="font-medium">
                    {t("connectors.latestError")}
                  </div>
                  <div className="break-words">{lastError}</div>
                </div>
              </div>
            ) : null}
          </div>

          <Separator className="mb-8 mt-8 bg-border" />

          <div className="space-y-6">
            <div className="flex items-center gap-2">
              <div className="size-3.5 rounded-full bg-primary/20" />
              <h4 className="text-xs font-bold uppercase tracking-widest text-foreground">
                {t("connectors.coreCapabilities")}
              </h4>
            </div>

            <div className="grid grid-cols-2 gap-3">
              {DEFAULT_CAPABILITIES.map((feature) => (
                <CapabilityFeature
                  key={feature.title}
                  icon={feature.icon}
                  title={feature.title}
                  desc={feature.desc}
                />
              ))}
            </div>
          </div>

          <div className="mt-12 flex items-center justify-between border-t border-border pt-6 text-muted-foreground/50">
            <div className="flex gap-4 text-[9px] font-bold uppercase tracking-widest">
              <a
                href={connector.website}
                target="_blank"
                rel="noreferrer"
                className="hover:text-foreground"
              >
                {t("connectors.officialWebsite")}
              </a>
              <a
                href={connector.privacyPolicy}
                target="_blank"
                rel="noreferrer"
                className="hover:text-foreground"
              >
                {t("connectors.privacyPolicy")}
              </a>
            </div>
            <button className="text-[9px] font-bold uppercase tracking-widest hover:text-foreground">
              {t("connectors.reportIssue")}
            </button>
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}

function getConnectorStateLabel(
  state: ConnectorCatalogItem["state"],
  t: (key: string) => string,
): string {
  switch (state) {
    case "connected":
      return t("connectors.connected");
    case "launching":
      return t("connectors.launching");
    case "failed":
      return t("connectors.failed");
    case "enabled":
      return t("connectors.enabled");
    case "disabled":
      return t("connectors.disabled");
    case "available":
      return t("connectors.available");
    case "unavailable":
      return t("connectors.unavailable");
    case "coming-soon":
    default:
      return t("connectors.inDevelopment");
  }
}

function getConnectorBadgeClassName(
  state: ConnectorCatalogItem["state"],
): string {
  switch (state) {
    case "connected":
      return "border-primary/20 bg-primary/10 text-primary";
    case "launching":
      return "border-amber-500/20 bg-amber-500/10 text-amber-700";
    case "failed":
      return "border-destructive/20 bg-destructive/10 text-destructive";
    case "enabled":
      return "border-emerald-500/20 bg-emerald-500/10 text-emerald-700";
    case "disabled":
    case "available":
      return "border-border bg-background text-muted-foreground";
    case "unavailable":
    case "coming-soon":
    default:
      return "border-border/70 bg-muted/30 text-muted-foreground";
  }
}

function getConnectorAction(
  connector: ConnectorCatalogItem,
  t: (key: string) => string,
): {
  label: string;
  destructive: boolean;
  disabled: boolean;
} {
  if (connector.type !== "mcp") {
    return {
      label: t("connectors.inDevelopment"),
      destructive: false,
      disabled: true,
    };
  }

  if (!connector.isConnectable) {
    return {
      label: t("connectors.unavailable"),
      destructive: false,
      disabled: true,
    };
  }

  if (connector.install?.enabled) {
    return {
      label: t("library.mcpLibrary.actions.disable"),
      destructive: true,
      disabled: false,
    };
  }

  return {
    label: t("library.mcpLibrary.actions.enable"),
    destructive: false,
    disabled: false,
  };
}
