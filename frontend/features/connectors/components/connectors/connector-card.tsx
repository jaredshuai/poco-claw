import { Shield, Globe, Info, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n/client";
import type { ConnectorCatalogItem } from "@/features/connectors/lib/mcp-connector-state";

interface ConnectorCardProps {
  connector: ConnectorCatalogItem;
  isComingSoon?: boolean;
  onClick: () => void;
}

/**
 * Individual connector card for the grid
 */
export function ConnectorCard({
  connector,
  isComingSoon = connector.state === "coming-soon",
  onClick,
}: ConnectorCardProps) {
  const { t } = useT("translation");

  const stateLabel = getConnectorStateLabel(connector.state, t);

  return (
    <button
      type="button"
      className={cn(
        "group flex w-full items-start gap-4 rounded-2xl border p-5 text-left transition-all duration-300",
        isComingSoon
          ? "border-border/70 bg-muted/20 hover:bg-muted/30"
          : "border-border bg-card shadow-lg hover:scale-[1.02] hover:border-border hover:bg-accent/50",
      )}
      onClick={onClick}
    >
      <div className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-muted/50 border border-border group-hover:bg-muted group-hover:border-border transition-colors">
        <connector.icon className="size-6 text-muted-foreground group-hover:text-foreground transition-colors" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1.5">
          <div className="font-semibold text-base truncate">
            {connector.title}
          </div>
          {isComingSoon && (
            <Badge
              variant="outline"
              className="h-4 bg-muted/30 px-1.5 text-[9px] text-muted-foreground/70"
            >
              {t("connectors.inDevelopment")}
            </Badge>
          )}
          {!isComingSoon && (
            <Badge
              variant="outline"
              className="h-4 border-primary/20 bg-primary/5 px-1.5 text-[9px] text-primary"
            >
              {stateLabel}
            </Badge>
          )}
        </div>
        <div className="text-sm text-muted-foreground/70 line-clamp-2 leading-relaxed">
          {t(connector.descriptionKey)}
        </div>
      </div>
    </button>
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

/**
 * Feature item for connector capabilities
 */
interface CapabilityFeatureProps {
  icon: React.ElementType;
  title: string;
  desc: string;
}

export function CapabilityFeature({
  icon: Icon,
  title,
  desc,
}: CapabilityFeatureProps) {
  const { t } = useT("translation");
  return (
    <div className="group p-4 rounded-xl border border-border bg-card hover:bg-accent/50 transition-all flex items-start gap-3">
      <div className="size-8 rounded-lg bg-muted/50 flex items-center justify-center shrink-0 group-hover:bg-muted transition-colors">
        <Icon className="size-4 text-muted-foreground/60 group-hover:text-muted-foreground transition-colors" />
      </div>
      <div className="min-w-0">
        <div className="font-bold text-sm mb-0.5 truncate">{t(title)}</div>
        <div className="text-[11px] text-muted-foreground/50 leading-snug line-clamp-2">
          {t(desc)}
        </div>
      </div>
    </div>
  );
}

/**
 * Default capabilities for all connectors
 */
export const DEFAULT_CAPABILITIES = [
  {
    title: "connectorCapabilities.automation.title",
    desc: "connectorCapabilities.automation.desc",
    icon: Globe,
  },
  {
    title: "connectorCapabilities.aiAssistant.title",
    desc: "connectorCapabilities.aiAssistant.desc",
    icon: Info,
  },
  {
    title: "connectorCapabilities.security.title",
    desc: "connectorCapabilities.security.desc",
    icon: Shield,
  },
  {
    title: "connectorCapabilities.search.title",
    desc: "connectorCapabilities.search.desc",
    icon: Search,
  },
];
