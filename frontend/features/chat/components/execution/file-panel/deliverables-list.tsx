"use client";

import React from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import {
  FileText,
  Table,
  Presentation,
  FileIcon,
  ChevronRight,
  Download,
  Eye,
  Clock,
  FolderInput,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n/client";
import type {
  DeliverableResponse,
  DeliverableVersionResponse,
  FileChange,
} from "@/features/chat/types";

interface DeliverablesListProps {
  deliverables: DeliverableResponse[];
  versionMap: Record<string, DeliverableVersionResponse>;
  selectedDeliverableId?: string | null;
  onSelectDeliverable?: (deliverableId: string, versionId: string | null) => void;
  onFileClick?: (filePath: string) => void;
  onViewProcess?: (deliverableId: string, versionId: string) => void;
  onDownloadVersion?: (version: DeliverableVersionResponse) => void;
  fileChanges?: FileChange[];
}

function getKindIcon(kind: string, className?: string) {
  switch (kind.toLowerCase()) {
    case "docx":
    case "doc":
      return <FileText className={cn("size-4", className)} />;
    case "xlsx":
    case "xls":
      return <Table className={cn("size-4", className)} />;
    case "pptx":
    case "ppt":
      return <Presentation className={cn("size-4", className)} />;
    default:
      return <FileIcon className={cn("size-4", className)} />;
  }
}

interface DeliverableCardProps {
  deliverable: DeliverableResponse;
  latestVersion?: DeliverableVersionResponse | null;
  isSelected: boolean;
  onSelect: () => void;
  onViewProcess?: () => void;
  onDownload?: () => void;
  onFileClick?: (filePath: string) => void;
  t: (key: string) => string;
}

function DeliverableCard({
  deliverable,
  latestVersion,
  isSelected,
  onSelect,
  onViewProcess,
  onDownload,
  t,
}: DeliverableCardProps) {
  const [isExpanded, setIsExpanded] = React.useState(false);

  const handleHeaderClick = () => {
    setIsExpanded(!isExpanded);
    onSelect();
  };

  const fileName = latestVersion?.file_name || latestVersion?.file_path?.split("/").pop() || deliverable.logical_name;

  return (
    <div
      className={cn(
        "rounded-lg border bg-card overflow-hidden transition-all",
        isSelected && "ring-2 ring-primary/50",
      )}
    >
      <div
        className={cn(
          "flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-muted/50 transition-colors",
          isSelected && "bg-muted/30",
        )}
        onClick={handleHeaderClick}
      >
        <div className="shrink-0">{getKindIcon(deliverable.kind, "text-primary")}</div>
        <div className="flex-1 min-w-0 overflow-hidden">
          <p className="font-medium text-sm truncate" title={deliverable.logical_name}>
            {deliverable.logical_name}
          </p>
          <p className="text-xs text-muted-foreground truncate" title={fileName}>
            {fileName}
          </p>
        </div>
        <ChevronRight
          className={cn(
            "size-4 text-muted-foreground shrink-0 transition-transform duration-200",
            isExpanded && "rotate-90",
          )}
        />
      </div>

      {isExpanded && latestVersion && (
        <div className="border-t bg-muted/20 px-4 py-2">
          <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
            <Clock className="size-3" />
            <span>{t("deliverables.latestVersion")}</span>
          </div>
          <div className="flex gap-2">
            {onViewProcess && (
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs"
                onClick={(e) => {
                  e.stopPropagation();
                  onViewProcess();
                }}
              >
                <Eye className="size-3 mr-1" />
                {t("deliverables.viewProcess")}
              </Button>
            )}
            {onDownload && (
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs"
                onClick={(e) => {
                  e.stopPropagation();
                  onDownload();
                }}
              >
                <Download className="size-3 mr-1" />
                {t("deliverables.download")}
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

interface ReferenceInputsSectionProps {
  fileChanges: FileChange[];
  onFileClick?: (filePath: string) => void;
  t: (key: string) => string;
}

function ReferenceInputsSection({
  fileChanges,
  onFileClick,
  t,
}: ReferenceInputsSectionProps) {
  if (fileChanges.length === 0) return null;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 px-1">
        <FolderInput className="size-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold text-muted-foreground">
          {t("deliverables.referenceInputs")}
        </h3>
      </div>
      <div className="space-y-1">
        {fileChanges.map((change, index) => (
          <button
            key={`${change.path}-${index}`}
            type="button"
            className="w-full text-left px-3 py-2 rounded-md text-sm hover:bg-muted/50 transition-colors truncate"
            title={change.path}
            onClick={() => onFileClick?.(change.path)}
          >
            {change.path}
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * Deliverables list component for the file panel.
 * Shows deliverables in a card-based layout with actions.
 */
export function DeliverablesList({
  deliverables,
  versionMap,
  selectedDeliverableId,
  onSelectDeliverable,
  onFileClick,
  onViewProcess,
  onDownloadVersion,
  fileChanges = [],
}: DeliverablesListProps) {
  const { t } = useT("translation");

  if (deliverables.length === 0 && fileChanges.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-muted-foreground">
          <p className="text-sm">{t("artifacts.empty.noChanges")}</p>
        </div>
      </div>
    );
  }

  // Separate deliverables from reference inputs
  const deliverableVersions = deliverables
    .map((d) => ({
      deliverable: d,
      latestVersion: d.latest_version_id ? versionMap[d.latest_version_id] ?? null : null,
    }))
    .filter((item) => item.latestVersion);

  // Files that are reference inputs (not deliverables)
  const referenceInputFiles = fileChanges.filter(
    (change) =>
      change.status === "added" &&
      !deliverableVersions.some(
        (dv) => dv.latestVersion?.file_path === change.path,
      ),
  );

  return (
    <div className="flex flex-col h-full min-w-0 max-w-full overflow-hidden">
      <ScrollArea className="flex-1 min-w-0 max-w-full overflow-hidden [&_[data-slot=scroll-area-viewport]]:overflow-x-hidden">
        <div className="w-full min-w-0 max-w-full px-4 py-4 space-y-6">
          {/* Deliverables Section */}
          {deliverableVersions.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 px-1">
                <FileIcon className="size-4 text-primary" />
                <h3 className="text-sm font-semibold text-muted-foreground">
                  {t("deliverables.title")}
                </h3>
                <span className="text-xs text-muted-foreground/60">
                  ({deliverableVersions.length})
                </span>
              </div>
              <div className="space-y-2">
                {deliverableVersions.map(({ deliverable, latestVersion }) => (
                  <DeliverableCard
                    key={deliverable.id}
                    deliverable={deliverable}
                    latestVersion={latestVersion}
                    isSelected={selectedDeliverableId === deliverable.id}
                    onSelect={() =>
                      onSelectDeliverable?.(deliverable.id, latestVersion?.id ?? null)
                    }
                    onViewProcess={
                      latestVersion && onViewProcess
                        ? () => onViewProcess(deliverable.id, latestVersion.id)
                        : undefined
                    }
                    onDownload={
                      latestVersion && onDownloadVersion
                        ? () => onDownloadVersion(latestVersion)
                        : undefined
                    }
                    onFileClick={onFileClick}
                    t={t}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Reference Inputs Section */}
          {referenceInputFiles.length > 0 && (
            <ReferenceInputsSection
              fileChanges={referenceInputFiles}
              onFileClick={onFileClick}
              t={t}
            />
          )}

          {/* Empty state when no deliverables but files exist */}
          {deliverableVersions.length === 0 && fileChanges.length > 0 && (
            <div className="text-center text-muted-foreground py-8">
              <p className="text-sm">{t("deliverables.noDeliverables")}</p>
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
