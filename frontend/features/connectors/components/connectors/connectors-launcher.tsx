"use client";

import { useState } from "react";
import { Plug } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useT } from "@/lib/i18n/client";
import { cn } from "@/lib/utils";
import type { ConnectorType } from "@/features/connectors/constants/connectors";
import { ConnectorsDialog } from "@/features/connectors/components/connectors/connectors-dialog";

interface ConnectorsLauncherProps {
  sessionId?: string;
  defaultTab?: ConnectorType;
  label?: string;
  title?: string;
  variant?: React.ComponentProps<typeof Button>["variant"];
  size?: React.ComponentProps<typeof Button>["size"];
  className?: string;
  iconOnly?: boolean;
}

export function ConnectorsLauncher({
  sessionId,
  defaultTab = "mcp",
  label,
  title,
  variant = "ghost",
  size = "default",
  className,
  iconOnly = false,
}: ConnectorsLauncherProps) {
  const { t } = useT("translation");
  const [open, setOpen] = useState(false);
  const buttonLabel = label ?? t("connectors.title");
  const buttonTitle = title ?? buttonLabel;

  return (
    <>
      <Button
        type="button"
        variant={variant}
        size={size}
        className={cn(className)}
        onClick={() => setOpen(true)}
        aria-label={buttonTitle}
        title={buttonTitle}
      >
        <Plug className="size-4" />
        {iconOnly ? null : <span>{buttonLabel}</span>}
      </Button>
      <ConnectorsDialog
        open={open}
        onOpenChange={setOpen}
        defaultTab={defaultTab}
        sessionId={sessionId}
      />
    </>
  );
}
