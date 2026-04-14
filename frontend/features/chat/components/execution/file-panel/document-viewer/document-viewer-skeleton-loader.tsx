"use client";

import { cn } from "@/lib/utils";
import { SkeletonItem } from "@/components/ui/skeleton-shimmer";
import { useT } from "@/lib/i18n/client";
import { VIEW_CLASSNAME } from "./utils";

/**
 * Reusable loading component for next/dynamic imports.
 *
 * Extracting this avoids the eslint-disable-next-line react-hooks/rules-of-hooks
 * anti-pattern that occurs when calling useT() inside inline loading functions
 * passed to next/dynamic().
 */
export function DocumentViewerSkeletonLoader() {
  const { t } = useT("translation");
  return (
    <div
      className={cn(
        VIEW_CLASSNAME,
        "items-center justify-center p-6 text-muted-foreground",
      )}
    >
      <div className="w-full max-w-3xl space-y-3">
        <SkeletonItem className="h-10 min-h-0 w-1/3" />
        <SkeletonItem className="h-56 min-h-0 w-full" />
        <SkeletonItem className="h-10 min-h-0 w-2/3" />
      </div>
      <span className="sr-only">{t("artifacts.viewer.loadingEngine")}</span>
    </div>
  );
}
