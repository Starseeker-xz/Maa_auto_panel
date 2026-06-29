import { Card, CardTitle } from "@/components/ui/card";

export function SettingsPage() {
  return (
    <section className="min-h-screen p-4">
      <Card className="grid min-h-[calc(100vh-2rem)] place-items-center bg-card/70">
        <CardTitle className="text-muted-foreground">设置</CardTitle>
      </Card>
    </section>
  );
}
