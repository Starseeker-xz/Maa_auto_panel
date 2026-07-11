import { BellRing, MonitorCog, Palette } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

import { SegmentedControl } from "@/components/SegmentedControl";

const ITEMS = [
  { path: "/settings", label: "基础设置", icon: MonitorCog },
  { path: "/settings/framework", label: "框架设置", icon: BellRing },
  { path: "/settings/theme", label: "主题", icon: Palette }
] as const;

export function SettingsNavigation() {
  const location = useLocation();
  const navigate = useNavigate();
  const current = ITEMS.some((item) => item.path === location.pathname) ? location.pathname : "/settings";
  return (
    <nav aria-label="设置分类">
      <SegmentedControl
        value={current}
        items={ITEMS.map((item) => ({ value: item.path, label: item.label, icon: <item.icon className="size-4" /> }))}
        onChange={navigate}
      />
    </nav>
  );
}
