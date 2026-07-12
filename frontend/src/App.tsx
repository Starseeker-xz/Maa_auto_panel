import React from "react";
import { CalendarClock, ChevronDown, ChevronRight, Home, Settings, Wrench } from "lucide-react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { LazyBoundary, LazyFallback } from "@/components/LazyBoundary";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarInset,
  SidebarMenuButton,
  SidebarProvider,
  useSidebar
} from "@/components/ui/sidebar";
import { NotificationCenter } from "@/components/NotificationCenter";
import { TooltipProvider } from "@/components/ui/tooltip";
import { APP_TITLE } from "@/lib/branding";
import { listSchedules } from "@/lib/api";
import { initializeTheme, syncSystemTheme } from "@/lib/theme";
import type { ScheduleConfigFile } from "@/lib/types";

const MainPage = React.lazy(() => import("@/pages/MainPage").then((module) => ({ default: module.MainPage })));
const SchedulePage = React.lazy(() => import("@/pages/SchedulePage").then((module) => ({ default: module.SchedulePage })));
const SettingsPage = React.lazy(() => import("@/pages/SettingsPage").then((module) => ({ default: module.SettingsPage })));
const ThemeSettingsPage = React.lazy(() =>
  import("@/pages/settings/ThemeSettingsPage").then((module) => ({ default: module.ThemeSettingsPage }))
);
const ToolsPage = React.lazy(() => import("@/pages/ToolsPage").then((module) => ({ default: module.ToolsPage })));

const LAST_MAIN_PATH_KEY = "maa-auto-panel:last-main-path";

export function App() {
  return (
    <TooltipProvider>
      <SidebarProvider>
        <AppShell />
      </SidebarProvider>
    </TooltipProvider>
  );
}

function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { expanded } = useSidebar();
  const [scheduleExpanded, setScheduleExpanded] = React.useState(true);
  const [schedules, setSchedules] = React.useState<ScheduleConfigFile[]>([]);
  const [scheduleDevice, setScheduleDevice] = React.useState<{ scheduleId: string; device: string } | null>(null);
  const scheduleDetailId = React.useMemo(() => {
    const match = /^\/schedule\/([^/]+)$/.exec(location.pathname);
    return match ? decodeURIComponent(match[1]) : "";
  }, [location.pathname]);
  const handleScheduleDeviceChange = React.useCallback((value: { scheduleId: string; device: string } | null) => {
    setScheduleDevice(value);
  }, []);
  const page = location.pathname.startsWith("/schedule")
    ? "schedule"
    : location.pathname.startsWith("/tools")
      ? "tools"
    : location.pathname.startsWith("/settings")
      ? "settings"
      : "main";

  React.useEffect(() => {
    initializeTheme();

    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    media?.addEventListener("change", syncSystemTheme);
    return () => {
      media?.removeEventListener("change", syncSystemTheme);
    };
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    listSchedules()
      .then((data) => {
        if (!cancelled) setSchedules(data.schedules);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [location.pathname]);

  return (
    <div className="min-h-screen bg-background text-foreground">
          <Sidebar>
            <SidebarHeader>
              <div className="font-semibold tracking-tight">{APP_TITLE}</div>
            </SidebarHeader>
            <SidebarContent>
              <SidebarMenuButton active={page === "main"} icon={<Home />} onClick={() => navigate(window.localStorage.getItem(LAST_MAIN_PATH_KEY) || "/")}>
                主界面
              </SidebarMenuButton>
              <div className="grid gap-1">
                <SidebarMenuButton
                  active={page === "schedule"}
                  icon={<CalendarClock />}
                  onClick={() => {
                    setScheduleExpanded((value) => !value);
                    navigate("/schedule");
                  }}
                >
                  <span className="flex min-w-0 flex-1 items-center justify-between gap-2">
                    <span className="truncate">定时执行</span>
                    {expanded ? scheduleExpanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" /> : null}
                  </span>
                </SidebarMenuButton>
                {expanded && scheduleExpanded ? (
                  <div className="ml-7 grid gap-1 border-l pl-2">
                    {schedules.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        data-active={location.pathname === `/schedule/${item.id}` ? "true" : undefined}
                        className="h-8 min-w-0 rounded-md px-2 text-left text-xs text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground data-[active=true]:bg-sidebar-primary data-[active=true]:text-sidebar-primary-foreground"
                        onClick={() => navigate(`/schedule/${encodeURIComponent(item.id)}`)}
                      >
                        <span className="block truncate">{item.name}</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
              <SidebarMenuButton active={page === "tools"} icon={<Wrench />} onClick={() => navigate("/tools")}>
                小工具
              </SidebarMenuButton>
            </SidebarContent>
            <SidebarFooter>
              <SidebarMenuButton active={page === "settings"} icon={<Settings />} onClick={() => navigate("/settings")}>
                设置
              </SidebarMenuButton>
            </SidebarFooter>
          </Sidebar>

          <SidebarInset>
            <LazyBoundary
              resetKey={location.pathname}
              fallback={<LazyFallback className="m-4 h-[calc(100vh-2rem)]" />}
              className="m-4 h-[calc(100vh-2rem)]"
            >
              <Routes>
                <Route path="/" element={<MainPage />} />
                <Route path="/tasks/:taskConfig" element={<MainPage />} />
                <Route path="/tasks/:taskConfig/items/:taskItemId" element={<MainPage />} />
                <Route path="/schedule" element={<SchedulePage onScrcpyDeviceChange={handleScheduleDeviceChange} />} />
                <Route path="/schedule/:scheduleId" element={<SchedulePage onScrcpyDeviceChange={handleScheduleDeviceChange} />} />
                <Route path="/tools" element={<ToolsPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/settings/framework" element={<SettingsPage />} />
                <Route path="/settings/theme" element={<ThemeSettingsPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </LazyBoundary>
          </SidebarInset>
          <NotificationCenter
            scheduleDeviceRequired={Boolean(scheduleDetailId)}
            scheduleDevice={scheduleDevice?.scheduleId === scheduleDetailId ? scheduleDevice.device : undefined}
          />
    </div>
  );
}
