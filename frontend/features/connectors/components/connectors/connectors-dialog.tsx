import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";

import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useT } from "@/lib/i18n/client";
import type { ConnectorType } from "@/features/connectors/constants/connectors";
import { useConnectorsCatalog } from "@/features/connectors/hooks/use-connectors-catalog";
import type { ConnectorCatalogItem } from "@/features/connectors/lib/mcp-connector-state";

import { ConnectorCard } from "./connector-card";
import { ConnectorDetail } from "./connector-detail";

interface ConnectorsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultTab?: ConnectorType;
  initialConnectorId?: string;
  sessionId?: string;
  key?: string;
}

/**
 * Connectors dialog with tabs, search, and a real MCP install/runtime state view.
 */
export function ConnectorsDialog({
  open,
  onOpenChange,
  defaultTab = "app",
  initialConnectorId,
  sessionId,
  key,
}: ConnectorsDialogProps) {
  const { t } = useT("translation");
  const [activeTab, setActiveTab] = useState<ConnectorType>(
    normalizeDialogTab(defaultTab),
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedConnectorId, setSelectedConnectorId] = useState<string | null>(
    null,
  );
  const { connectors, isLoading, pendingConnectorId, toggleConnector } =
    useConnectorsCatalog({
      open,
      sessionId,
    });

  useEffect(() => {
    if (!open) {
      return;
    }

    setActiveTab(normalizeDialogTab(defaultTab));
    setSearchQuery("");
    setSelectedConnectorId(initialConnectorId ?? null);
  }, [defaultTab, initialConnectorId, open]);

  const filteredConnectors = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();

    return connectors.filter((connector) => {
      if (connector.type !== activeTab) {
        return false;
      }

      if (!normalizedQuery) {
        return true;
      }

      const description = t(connector.descriptionKey).toLowerCase();
      const haystack = [connector.title, connector.id, description]
        .join(" ")
        .toLowerCase();
      return haystack.includes(normalizedQuery);
    });
  }, [activeTab, connectors, searchQuery, t]);

  const selectedConnector = useMemo<ConnectorCatalogItem | null>(() => {
    if (!selectedConnectorId) {
      return null;
    }

    return (
      connectors.find((connector) => connector.id === selectedConnectorId) ??
      null
    );
  }, [connectors, selectedConnectorId]);

  const dialogTitle = selectedConnector?.title ?? t("connectors.title");

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          setSelectedConnectorId(null);
        }
        onOpenChange(nextOpen);
      }}
      key={key}
    >
      <DialogContent
        aria-describedby={undefined}
        className="flex h-[600px] max-w-4xl flex-col gap-0 overflow-hidden border-border bg-background p-0 text-foreground"
        ariaTitle={dialogTitle}
      >
        {selectedConnector ? (
          <ConnectorDetail
            connector={selectedConnector}
            isPending={pendingConnectorId === selectedConnector.id}
            onBack={() => setSelectedConnectorId(null)}
            onToggle={toggleConnector}
          />
        ) : (
          <>
            <div className="flex items-center justify-between border-b border-border px-6 py-4">
              <h2 className="text-lg font-semibold leading-none">
                {dialogTitle}
              </h2>
            </div>

            <div className="flex flex-1 flex-col overflow-hidden">
              <div className="px-6 py-4 pb-2">
                <div className="flex items-center justify-between gap-4">
                  <Tabs
                    value={activeTab}
                    onValueChange={(value) =>
                      setActiveTab(value as ConnectorType)
                    }
                    className="w-auto"
                  >
                    <TabsList className="h-auto justify-start gap-2 bg-transparent p-0">
                      <TabsTrigger
                        value="app"
                        className="rounded-lg border border-transparent px-4 py-2 text-sm font-medium text-muted-foreground transition-all hover:text-foreground data-[state=active]:border-primary/20 data-[state=active]:bg-primary/10 data-[state=active]:text-primary"
                      >
                        {t("connectors.apps")}
                      </TabsTrigger>
                      <TabsTrigger
                        value="mcp"
                        className="rounded-lg border border-transparent px-4 py-2 text-sm font-medium text-muted-foreground transition-all hover:text-foreground data-[state=active]:border-primary/20 data-[state=active]:bg-primary/10 data-[state=active]:text-primary"
                      >
                        {t("connectors.mcp")}
                      </TabsTrigger>
                      <TabsTrigger
                        value="skill"
                        className="rounded-lg border border-transparent px-4 py-2 text-sm font-medium text-muted-foreground transition-all hover:text-foreground data-[state=active]:border-primary/20 data-[state=active]:bg-primary/10 data-[state=active]:text-primary"
                      >
                        {t("connectors.skills")}
                      </TabsTrigger>
                    </TabsList>
                  </Tabs>
                  <div className="relative w-64">
                    <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
                    <Input
                      value={searchQuery}
                      onChange={(event) => setSearchQuery(event.target.value)}
                      placeholder={t("connectors.search")}
                      className="h-9 border-border bg-muted/50 pl-9 focus-visible:ring-1 focus-visible:ring-primary"
                    />
                  </div>
                </div>
              </div>
              <Separator className="bg-border" />

              <div className="custom-scrollbar flex-1 overflow-y-auto">
                <div className="grid grid-cols-2 gap-4 p-6 pb-20">
                  {filteredConnectors.map((connector) => (
                    <ConnectorCard
                      key={connector.id}
                      connector={connector}
                      onClick={() => setSelectedConnectorId(connector.id)}
                    />
                  ))}
                  {!isLoading && filteredConnectors.length === 0 ? (
                    <div className="col-span-2 rounded-2xl border border-dashed border-border bg-muted/10 p-6 text-sm text-muted-foreground">
                      {t("connectors.noResults")}
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function normalizeDialogTab(tab: ConnectorType): ConnectorType {
  return tab === "api" ? "app" : tab;
}
