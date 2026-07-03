import { ChevronRight, LoaderCircle, Wrench } from "lucide-react";

import { Card, CardTitle } from "@/components/ui/card";
import type { ToolDefinition } from "@/lib/types";
import { cn } from "@/lib/utils";

type ToolListPaneProps = {
  tools: ToolDefinition[];
  selectedToolId: string;
  activeToolId: string;
  onSelect: (toolId: string) => void;
};

export function ToolListPane({ tools, selectedToolId, activeToolId, onSelect }: ToolListPaneProps) {
  return (
    <Card className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-3 overflow-hidden p-3 max-md:p-2">
      <div className="flex items-center gap-2">
        <Wrench className="size-4 text-muted-foreground" />
        <CardTitle>小工具</CardTitle>
      </div>
      <div className="min-h-0 overflow-auto">
        <div className="grid gap-2">
          {tools.map((tool) => {
            const selected = tool.id === selectedToolId;
            const running = tool.id === activeToolId;
            return (
              <button
                key={tool.id}
                type="button"
                className={cn(
                  "grid min-h-12 grid-cols-[1fr_auto] items-center gap-3 rounded-md border bg-background px-3 py-2 text-left transition-colors hover:border-primary/60",
                  selected && "border-primary/70 bg-accent/45"
                )}
                onClick={() => onSelect(tool.id)}
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">{tool.title}</span>
                </span>
                {running ? <LoaderCircle className="size-4 animate-spin text-primary" /> : <ChevronRight className="size-4 text-muted-foreground" />}
              </button>
            );
          })}
          {tools.length === 0 ? (
            <div className="rounded-md border border-dashed bg-background px-3 py-8 text-center text-sm text-muted-foreground">暂无工具</div>
          ) : null}
        </div>
      </div>
    </Card>
  );
}
