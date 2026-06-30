import React from "react";
import { CalendarClock, Home, Settings } from "lucide-react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarInset,
  SidebarMenuButton,
  SidebarProvider
} from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { getSettings } from "@/lib/api";
import { loadStoredTheme, setActiveTheme, syncSystemTheme, themeFromFrameworkSettings } from "@/lib/theme";
import { MainPage } from "@/pages/MainPage";
import { SchedulePage } from "@/pages/SchedulePage";
import { SettingsPage } from "@/pages/SettingsPage";

const LAST_MAIN_PATH_KEY = "linux-maa:last-main-path";

export function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const page = location.pathname.startsWith("/schedule")
    ? "schedule"
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

  return (
    <TooltipProvider>
      <SidebarProvider>
        <div className="min-h-screen bg-background text-foreground">
          <Sidebar>
            <SidebarHeader>
              <div className="font-semibold tracking-tight">Linux MAA</div>
            </SidebarHeader>
            <SidebarContent>
              <SidebarMenuButton active={page === "main"} icon={<Home />} onClick={() => navigate(window.localStorage.getItem(LAST_MAIN_PATH_KEY) || "/")}>
                主界面
              </SidebarMenuButton>
              <SidebarMenuButton active={page === "schedule"} icon={<CalendarClock />} onClick={() => navigate("/schedule")}>
                定时执行
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
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </SidebarInset>
        </div>
      </SidebarProvider>
    </TooltipProvider>
  );
}
