import { Wrench } from "lucide-react";

import { Card, CardTitle } from "@/components/ui/card";

export function ToolsPage() {
  return (
    <section className="min-h-screen overflow-auto p-4">
      <Card className="min-h-[calc(100vh-2rem)] gap-3 p-4">
        <div className="flex items-center gap-2">
          <Wrench className="size-4 text-muted-foreground" />
          <CardTitle>小工具</CardTitle>
        </div>
        <div className="grid min-h-40 place-items-center rounded-md border border-dashed bg-background text-sm text-muted-foreground">工具页占位</div>
      </Card>
    </section>
  );
}
