import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type SegmentedControlItem<T extends string> = {
  value: T;
  label: string;
  icon?: ReactNode;
};

export function SegmentedControl<T extends string>({ value, items, onChange, className }: { value: T; items: readonly SegmentedControlItem<T>[]; onChange: (value: T) => void; className?: string }) {
  return (
    <div className={cn("inline-flex w-fit max-w-full gap-1 overflow-x-auto rounded-xl border bg-muted p-1", className)} role="tablist">
      {items.map((item) => (
        <button
          key={item.value}
          type="button"
          role="tab"
          aria-selected={item.value === value}
          className={cn(
            "inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-lg px-3 text-sm text-muted-foreground transition-all hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            item.value === value && "bg-background text-foreground shadow-sm"
          )}
          onClick={() => onChange(item.value)}
        >
          {item.icon}
          {item.label}
        </button>
      ))}
    </div>
  );
}
