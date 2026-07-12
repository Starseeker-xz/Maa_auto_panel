import { Bell, Camera, MonitorSmartphone } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export function AppToolbar({
  unreadCount,
  importantUnread,
  scrcpyBusy,
  scrcpyDisabledReason,
  onScrcpy,
  onNotifications
}: {
  unreadCount: number;
  importantUnread: boolean;
  scrcpyBusy: boolean;
  scrcpyDisabledReason?: string;
  onScrcpy: () => void;
  onNotifications: () => void;
}) {
  const scrcpyLabel = scrcpyDisabledReason || (scrcpyBusy ? "正在启动 Scrcpy…" : "使用 Scrcpy 连接设备");
  return (
    <div className="fixed right-0 top-0 z-40 flex items-center gap-0.5 rounded-bl-lg border-b border-l bg-background/95 p-1 shadow-sm backdrop-blur" role="toolbar" aria-label="应用工具">
      <ToolbarButtonTooltip label={scrcpyLabel}>
        <Button variant="ghost" size="icon" className="size-8" aria-label={scrcpyLabel} onClick={onScrcpy} disabled={scrcpyBusy || Boolean(scrcpyDisabledReason)}>
          <MonitorSmartphone className="size-4" />
        </Button>
      </ToolbarButtonTooltip>
      <ToolbarButtonTooltip label="查看设备状态（尚未接入）">
        <Button variant="ghost" size="icon" className="size-8" aria-label="查看设备状态（尚未接入）" disabled>
          <Camera className="size-4" />
        </Button>
      </ToolbarButtonTooltip>
      <span className="mx-1 h-5 border-l" aria-hidden="true" />
      <ToolbarButtonTooltip label={unreadCount ? `通知，${unreadCount} 条未读` : "通知"}>
        <Button variant="ghost" size="icon" className="relative size-8" aria-label={unreadCount ? `通知，${unreadCount} 条未读` : "通知"} onClick={onNotifications}>
          <Bell className="size-5" />
          {unreadCount ? <span className={cn("absolute right-0.5 top-0.5 size-2.5 rounded-full border-2 border-background", importantUnread ? "bg-destructive" : "bg-primary")} aria-hidden="true" /> : null}
        </Button>
      </ToolbarButtonTooltip>
    </div>
  );
}

function ToolbarButtonTooltip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex">{children}</span>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
