"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { FileText, Folder, MessageSquare, Loader2 } from "lucide-react";
import { useT } from "@/lib/i18n/client";
import { useLanguage } from "@/hooks/use-language";
import { useSearchData } from "@/features/search/hooks/use-search-data";
import { canLeaveDocumentViewer } from "@/lib/document-viewer-leave-guard";

interface GlobalSearchDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Global search dialog (Spotlight-like)
 * Search across tasks, projects, and messages
 */
export function GlobalSearchDialog({
  open,
  onOpenChange,
}: GlobalSearchDialogProps) {
  const { t } = useT("translation");
  const router = useRouter();
  const lng = useLanguage();
  const [searchQuery, setSearchQuery] = React.useState("");
  const [isComposing, setIsComposing] = React.useState(false);
  const { tasks, projects, messages, isLoading } = useSearchData(searchQuery, {
    enabled: open,
  });
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  React.useEffect(() => {
    if (!open) {
      setSearchQuery("");
      setIsComposing(false);
    }
  }, [open]);

  const handleInputKeyDown = React.useCallback(
    (event: React.KeyboardEvent<HTMLInputElement>) => {
      if (event.key !== "Enter") return;
      // Keep search behavior predictable: Enter in the input should not trigger
      // result navigation implicitly (especially with IME composition).
      if (isComposing || event.nativeEvent.isComposing) {
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      event.preventDefault();
      event.stopPropagation();
    },
    [isComposing],
  );

  const hasResults =
    tasks.length > 0 || projects.length > 0 || messages.length > 0;

  const handleSelect = (type: string, id: string) => {
    void (async () => {
      if (!(await canLeaveDocumentViewer())) return;

      onOpenChange(false);

      switch (type) {
        case "task":
          router.push(lng ? `/${lng}/chat/${id}` : `/chat/${id}`);
          break;
        case "project":
          router.push(lng ? `/${lng}/projects/${id}` : `/projects/${id}`);
          break;
        case "message":
          // Navigate to chat page and scroll to message
          router.push(lng ? `/${lng}/chat/${id}` : `/chat/${id}`);
          break;
      }
    })();
  };

  if (!mounted) return null;

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      className="top-[20%] translate-y-0"
      commandProps={{ shouldFilter: false }}
    >
      <CommandInput
        placeholder={t("search.placeholder")}
        value={searchQuery}
        onValueChange={setSearchQuery}
        onKeyDown={handleInputKeyDown}
        onCompositionStart={() => setIsComposing(true)}
        onCompositionEnd={() => setIsComposing(false)}
      />
      <CommandList>
        {isLoading ? (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="size-4 animate-spin text-muted-foreground" />
          </div>
        ) : !hasResults && searchQuery !== "" ? (
          <CommandEmpty>{t("search.noResults")}</CommandEmpty>
        ) : null}

        {tasks.length > 0 && (
          <CommandGroup heading={t("search.tasks")}>
            {tasks.map((task) => (
              <CommandItem
                key={task.id}
                value={`task:${task.id}`}
                onSelect={() => handleSelect("task", task.id)}
              >
                <FileText className="size-4 text-muted-foreground" />
                <span className="flex-1">
                  {task.title || t("chat.newChat")}
                </span>
                <span className="text-xs text-muted-foreground">
                  {new Date(task.timestamp).toLocaleDateString()}
                </span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        {projects.length > 0 && (
          <CommandGroup heading={t("search.projects")}>
            {projects.map((project) => (
              <CommandItem
                key={project.id}
                value={`project:${project.id}`}
                onSelect={() => handleSelect("project", project.id)}
              >
                <Folder className="size-4 text-muted-foreground" />
                <span className="flex-1">{project.name}</span>
                {project.taskCount !== undefined && (
                  <span className="text-xs text-muted-foreground">
                    {project.taskCount} tasks
                  </span>
                )}
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        {messages.length > 0 && (
          <CommandGroup heading={t("search.messages")}>
            {messages.slice(0, 5).map((message) => (
              <CommandItem
                key={message.id}
                value={`message:${message.id}`}
                onSelect={() => handleSelect("message", message.chatId)}
              >
                <MessageSquare className="size-4 text-muted-foreground" />
                <span className="line-clamp-1 flex-1">{message.content}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  );
}
