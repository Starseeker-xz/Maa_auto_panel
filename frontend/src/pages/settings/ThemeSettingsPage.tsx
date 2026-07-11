import React from "react";

import { Button } from "@/components/ui/button";
import { loadStoredTheme, saveActiveTheme, themeColors, themeModes, type ThemeColor, type ThemeMode } from "@/lib/theme";
import { cn } from "@/lib/utils";
import { SettingsNavigation } from "@/pages/settings/SettingsNavigation";
import { SettingsPanel } from "@/pages/settings/panels";

export function ThemeSettingsPage() {
  const [theme, setTheme] = React.useState(loadStoredTheme);

  function updateTheme(patch: Partial<{ mode: ThemeMode; color: ThemeColor }>) {
    const next = { ...theme, ...patch };
    setTheme(next);
    saveActiveTheme(next);
  }

  return (
    <section className="min-h-screen overflow-auto p-4">
      <div className="grid min-h-[calc(100vh-2rem)] content-start gap-4">
        <SettingsNavigation />
        <div className="mx-auto grid w-full max-w-3xl gap-4">
          <SettingsPanel title="主题">
            <p className="text-xs leading-5 text-muted-foreground">主题只保存在当前浏览器中，修改后立即生效，不需要保存到后端。</p>
            <div className="grid grid-cols-3 gap-2">
              {themeModes.map((mode) => (
                <Button key={mode.value} variant={theme.mode === mode.value ? "default" : "outline"} onClick={() => updateTheme({ mode: mode.value })}>
                  {mode.label}
                </Button>
              ))}
            </div>
            <div className="grid grid-cols-5 gap-2 max-sm:grid-cols-2">
              {themeColors.map((color) => (
                <button
                  key={color.value}
                  type="button"
                  className={cn(
                    "grid h-16 min-w-0 place-items-center rounded-md border text-xs font-medium shadow-xs transition-all",
                    theme.color === color.value ? "border-primary ring-2 ring-primary/30" : "border-border hover:border-primary/70"
                  )}
                  data-color-swatch={color.value}
                  onClick={() => updateTheme({ color: color.value })}
                >
                  <span className="size-6 rounded-full border border-black/10 shadow-xs" />
                  <span className="max-w-full truncate">{color.label}</span>
                </button>
              ))}
            </div>
          </SettingsPanel>
        </div>
      </div>
    </section>
  );
}
