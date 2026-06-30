import * as React from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

type SidebarContextValue = {
  expanded: boolean;
  setExpanded: React.Dispatch<React.SetStateAction<boolean>>;
};

const SidebarContext = React.createContext<SidebarContextValue | null>(null);

function useSidebar() {
  const context = React.useContext(SidebarContext);
  if (!context) {
    throw new Error("useSidebar must be used within SidebarProvider");
  }
  return context;
}

function SidebarProvider({
  defaultExpanded = true,
  children
}: {
  defaultExpanded?: boolean;
  children: React.ReactNode;
}) {
  const [expanded, setExpanded] = React.useState(defaultExpanded);
  return <SidebarContext.Provider value={{ expanded, setExpanded }}>{children}</SidebarContext.Provider>;
}

function Sidebar({ className, ...props }: React.ComponentProps<"aside">) {
  const { expanded } = useSidebar();
  return (
    <aside
      data-state={expanded ? "expanded" : "collapsed"}
      className={cn(
        "bg-sidebar text-sidebar-foreground fixed inset-y-0 left-0 z-20 flex flex-col border-r transition-[width] duration-200 ease-out",
        expanded ? "w-56" : "w-16",
        className
      )}
      {...props}
    />
  );
}

function SidebarInset({ className, ...props }: React.ComponentProps<"main">) {
  const { expanded } = useSidebar();
  return <main className={cn("min-h-screen transition-[padding-left] duration-200 ease-out", expanded ? "pl-56" : "pl-16", className)} {...props} />;
}

function SidebarHeader({ className, children, ...props }: React.ComponentProps<"div">) {
  const { expanded, setExpanded } = useSidebar();
  return (
    <div className={cn("flex h-14 items-center gap-2 px-3", expanded ? "justify-between" : "justify-center", className)} {...props}>
      {expanded ? children : null}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon" onClick={() => setExpanded((value) => !value)} aria-label={expanded ? "收起侧边栏" : "展开侧边栏"}>
            {expanded ? <PanelLeftClose className="size-4" /> : <PanelLeftOpen className="size-4" />}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="right">{expanded ? "收起侧边栏" : "展开侧边栏"}</TooltipContent>
      </Tooltip>
    </div>
  );
}

function SidebarContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex flex-1 flex-col gap-1 px-2", className)} {...props} />;
}

function SidebarFooter({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("border-t p-2", className)} {...props} />;
}

function SidebarMenuButton({
  active,
  icon,
  children,
  className,
  ...props
}: React.ComponentProps<"button"> & {
  active?: boolean;
  icon: React.ReactNode;
}) {
  const { expanded } = useSidebar();
  const button = (
    <button
      data-active={active ? "true" : undefined}
      type="button"
      className={cn(
        "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground data-[active=true]:bg-sidebar-primary data-[active=true]:text-sidebar-primary-foreground flex h-10 w-full items-center rounded-md px-3 text-left text-sm transition-colors",
        expanded ? "justify-start gap-3" : "justify-center",
        className
      )}
      {...props}
    >
      <span className="[&_svg]:size-4">{icon}</span>
      {expanded ? <span className="flex min-w-0 flex-1 items-center truncate text-left">{children}</span> : null}
    </button>
  );

  if (expanded) {
    return button;
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent side="right">{children}</TooltipContent>
    </Tooltip>
  );
}

export { Sidebar, SidebarContent, SidebarFooter, SidebarHeader, SidebarInset, SidebarMenuButton, SidebarProvider, useSidebar };
