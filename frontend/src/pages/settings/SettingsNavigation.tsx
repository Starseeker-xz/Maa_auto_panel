import { BellRing, MonitorCog, Palette } from "lucide-react";
import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";

const ITEMS = [
  { path: "/settings", label: "基础设置", icon: MonitorCog },
  { path: "/settings/framework", label: "框架设置", icon: BellRing },
  { path: "/settings/theme", label: "主题", icon: Palette }
] as const;

export function SettingsNavigation() {
  return (
    <nav className="inline-flex w-fit max-w-full gap-1 overflow-x-auto rounded-xl border bg-muted p-1" aria-label="设置分类">
      {ITEMS.map((item) => (
        <NavLink
          key={item.path}
          to={item.path}
          end
          className={({ isActive }) =>
            cn(
              "inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-lg px-3 text-sm text-muted-foreground transition-all hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              isActive && "bg-background text-foreground shadow-sm"
            )
          }
        >
          <item.icon className="size-4" />
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
