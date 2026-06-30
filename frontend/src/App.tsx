import React from "react";
import { CalendarClock, ChevronDown, ChevronRight, Home, Settings, Wrench } from "lucide-react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";

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
import { TooltipProvider } from "@/components/ui/tooltip";
import { getSettings, listSchedules } from "@/lib/api";
import { loadStoredTheme, setActiveTheme, syncSystemTheme, themeFromFrameworkSettings } from "@/lib/theme";
import type { ScheduleConfigFile } from "@/lib/types";
import { MainPage } from "@/pages/MainPage";
import { SchedulePage } from "@/pages/SchedulePage";
import { SettingsPage } from "@/pages/SettingsPage";
import { ToolsPage } from "@/pages/ToolsPage";

const LAST_MAIN_PATH_KEY = "linux-maa:last-main-path";

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
  const page = location.pathname.startsWith("/schedule")
    ? "schedule"
    : location.pathname.startsWith("/tools")
      ? "tools"
    : location.pathname.startsWith("/settings")
      ? "settings"
      : "main";

  React.useEffect(() => {
    let cancelled = false;
    const storedTheme = loadStoredTheme();
    if (storedTheme) setActiveTheme(storedTheme);

    getSettings()
      .then((settings) => {
        if (!cancelled && !storedTheme) setActiveTheme(themeFromFrameworkSettings(settings.framework.data));
      })
      .catch(() => undefined);

    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    media?.addEventListener("change", syncSystemTheme);
    return () => {
      cancelled = true;
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
              <div className="font-semibold tracking-tight">Linux MAA</div>
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
            <Routes>
              <Route path="/" element={<MainPage />} />
              <Route path="/tasks/:taskConfig" element={<MainPage />} />
              <Route path="/tasks/:taskConfig/items/:taskItemId" element={<MainPage />} />
              <Route path="/schedule" element={<SchedulePage />} />
              <Route path="/schedule/:scheduleId" element={<SchedulePage />} />
              <Route path="/tools" element={<ToolsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </SidebarInset>
    </div>
  );
}
