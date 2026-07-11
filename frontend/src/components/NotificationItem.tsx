import { Bell, CheckCircle2, CircleAlert, Info } from "lucide-react";

import { FocusDeleteButton } from "@/components/FocusDeleteButton";
import type { NotificationEvent } from "@/lib/types";
import { cn } from "@/lib/utils";

export function NotificationItem({ event, unread, onDelete }: { event: NotificationEvent; unread: boolean; onDelete: () => void }) {
  const Icon = notificationIcon(event);
  return (
    <article className={cn("group relative grid grid-cols-[auto_minmax(0,1fr)] gap-3 rounded-lg border p-3", event.important && "border-primary/25 bg-muted/30")}>
      <Icon className={cn("mt-0.5 size-5", severityColor(event))} />
      <div className="min-w-0">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2 text-sm font-medium">
            {unread ? <span className={cn("size-1.5 shrink-0 rounded-full", event.important ? "bg-destructive" : "bg-primary")} aria-label="未读" /> : null}
            <span className="truncate">{event.title}</span>
          </div>
          <time className="shrink-0 text-[11px] text-muted-foreground" dateTime={event.created_at}>{formatCreatedAt(event.created_at)}</time>
        </div>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{event.message}</p>
      </div>
      <FocusDeleteButton floating aria-label={`删除通知：${event.title}`} onClick={onDelete} />
    </article>
  );
}

export function notificationIcon(event: NotificationEvent) {
  return event.severity === "success" ? CheckCircle2 : event.severity === "error" ? CircleAlert : event.severity === "warning" ? Bell : Info;
}

export function severityColor(event: NotificationEvent) {
  return event.severity === "error" ? "text-destructive" : event.severity === "success" ? "text-emerald-600" : event.severity === "warning" ? "text-amber-600" : "text-primary";
}

export function severityBorder(event: NotificationEvent) {
  return event.severity === "error" ? "border-destructive/40" : event.severity === "success" ? "border-emerald-500/40" : event.severity === "warning" ? "border-amber-500/40" : undefined;
}

function formatCreatedAt(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString([], { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}
