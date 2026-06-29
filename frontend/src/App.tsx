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
import { MainPage } from "@/pages/MainPage";
import { SchedulePage } from "@/pages/SchedulePage";
import { SettingsPage } from "@/pages/SettingsPage";

export function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const page = location.pathname.startsWith("/schedule")
    ? "schedule"
    : location.pathname.startsWith("/settings")
      ? "settings"
      : "main";

  return (
    <TooltipProvider>
      <SidebarProvider>
        <div className="min-h-screen bg-background text-foreground">
          <Sidebar>
            <SidebarHeader>
              <div className="font-semibold tracking-tight">Linux MAA</div>
            </SidebarHeader>
            <SidebarContent>
              <SidebarMenuButton active={page === "main"} icon={<Home />} onClick={() => navigate("/")}>
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
