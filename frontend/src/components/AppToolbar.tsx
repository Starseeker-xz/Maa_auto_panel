import { Bell, Camera, MonitorSmartphone } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function AppToolbar({ unreadCount, importantUnread, onNotifications }: { unreadCount: number; importantUnread: boolean; onNotifications: () => void }) {
  return (
    <div className="fixed right-0 top-0 z-40 flex items-center gap-0.5 rounded-bl-xl border-b border-l bg-background/95 p-1.5 shadow-sm backdrop-blur" role="toolbar" aria-label="应用工具">
      <Button variant="ghost" size="icon" aria-label="使用 Scrcpy 连接设备（尚未接入）" title="使用 Scrcpy 连接设备（尚未接入）" disabled>
        <MonitorSmartphone className="size-4" />
      </Button>
      <Button variant="ghost" size="icon" aria-label="查看设备状态（尚未接入）" title="查看设备状态（尚未接入）" disabled>
        <Camera className="size-4" />
      </Button>
      <Button variant="ghost" size="icon" className="relative" aria-label={unreadCount ? `通知，${unreadCount} 条未读` : "通知"} onClick={onNotifications}>
        <Bell className="size-5" />
        {unreadCount ? <span className={cn("absolute right-1 top-1 size-2.5 rounded-full border-2 border-background", importantUnread ? "bg-destructive" : "bg-primary")} aria-hidden="true" /> : null}
      </Button>
    </div>
  );
}
