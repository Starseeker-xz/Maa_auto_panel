import React from "react";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";

import { AppToolbar } from "@/components/AppToolbar";
import { NotificationItem } from "@/components/NotificationItem";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Toaster } from "@/components/ui/sonner";
import { notificationEventsUrl } from "@/lib/api";
import type { NotificationEvent } from "@/lib/types";

const MAX_RECENT = 100;
const READ_IDS_KEY = "maa-auto-panel:notifications:read-ids";
const DELETED_IDS_KEY = "maa-auto-panel:notifications:deleted-ids";

export function NotificationCenter() {
  const [recent, setRecent] = React.useState<NotificationEvent[]>([]);
  const [open, setOpen] = React.useState(false);
  const [readIds, setReadIds] = React.useState(() => readStoredIds(READ_IDS_KEY));
  const [deletedIds, setDeletedIds] = React.useState(() => readStoredIds(DELETED_IDS_KEY));
  const deletedIdsRef = React.useRef(deletedIds);
  const toastedIds = React.useRef(new Set<string>());

  React.useEffect(() => {
    deletedIdsRef.current = deletedIds;
  }, [deletedIds]);

  React.useEffect(() => {
    const source = new EventSource(notificationEventsUrl);
    source.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as NotificationEvent;
        if (deletedIdsRef.current.has(event.id)) return;
        setRecent((current) => upsertRecent(current, event));
        const shouldToast = event.toast && (!event.delivery.replayed || event.replay_toast);
        if (!shouldToast || toastedIds.current.has(event.id)) return;
        toastedIds.current.add(event.id);
        showToast(event);
      } catch {
        // Ignore one malformed event and keep the stream alive for later notifications.
      }
    };
    return () => source.close();
  }, []);

  React.useEffect(() => {
    if (open) markRead(recent.map((event) => event.id));
  }, [open, recent]);

  const unread = recent.filter((event) => !readIds.has(event.id));
  const importantUnread = unread.some((event) => event.important);

  function markRead(ids: string[]) {
    if (!ids.length) return;
    setReadIds((current) => {
      const next = new Set([...current, ...ids]);
      writeStoredIds(READ_IDS_KEY, next);
      return next;
    });
  }

  function showPanel() {
    setOpen(true);
    markRead(recent.map((event) => event.id));
  }

  function deleteEvent(event: NotificationEvent) {
    setRecent((current) => current.filter((item) => item.id !== event.id));
    toast.dismiss(event.id);
    setDeletedIds((current) => {
      const next = new Set([...current, event.id]);
      writeStoredIds(DELETED_IDS_KEY, next);
      return next;
    });
  }

  function clearAll() {
    const ids = recent.map((event) => event.id);
    setRecent([]);
    toast.dismiss();
    setDeletedIds((current) => {
      const next = new Set([...current, ...ids]);
      writeStoredIds(DELETED_IDS_KEY, next);
      return next;
    });
  }

  return (
    <>
      <AppToolbar unreadCount={unread.length} importantUnread={importantUnread} onNotifications={showPanel} />
      <Toaster position="top-right" duration={8000} visibleToasts={4} />

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="w-[min(22.5rem,calc(100vw-1rem))] gap-0 sm:max-w-[22.5rem]" side="right">
          <SheetHeader className="border-b">
            <SheetTitle>通知</SheetTitle>
            <SheetDescription className="sr-only">近期通知列表</SheetDescription>
          </SheetHeader>
          <ScrollArea className="min-h-0 flex-1">
            <div className="grid gap-2 p-3">
              {recent.length ? (
                recent.slice().reverse().map((event) => (
                  <NotificationItem key={event.id} event={event} unread={!readIds.has(event.id)} onDelete={() => deleteEvent(event)} />
                ))
              ) : (
                <div className="py-12 text-center text-sm text-muted-foreground">暂无通知</div>
              )}
            </div>
          </ScrollArea>
          <SheetFooter className="items-end border-t p-3">
            <Button variant="ghost" size="sm" className="text-muted-foreground hover:text-destructive" disabled={!recent.length} onClick={clearAll}>
              <Trash2 className="size-3.5" />
              清空通知
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </>
  );
}

function upsertRecent(current: NotificationEvent[], event: NotificationEvent) {
  return [...current.filter((item) => item.id !== event.id), event].sort((left, right) => left.sequence - right.sequence).slice(-MAX_RECENT);
}

function showToast(event: NotificationEvent) {
  const options = { id: event.id, description: event.message };
  if (event.severity === "success") toast.success(event.title, options);
  else if (event.severity === "error") toast.error(event.title, options);
  else if (event.severity === "warning") toast.warning(event.title, options);
  else toast.info(event.title, options);
}

function readStoredIds(key: string) {
  try {
    const value = JSON.parse(window.localStorage.getItem(key) || "[]");
    return new Set(Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : []);
  } catch {
    return new Set<string>();
  }
}

function writeStoredIds(key: string, ids: Set<string>) {
  window.localStorage.setItem(key, JSON.stringify([...ids].slice(-500)));
}
