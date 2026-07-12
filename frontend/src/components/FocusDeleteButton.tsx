import type { ComponentProps } from "react";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function FocusDeleteButton({ className, floating = false, ...props }: Omit<ComponentProps<typeof Button>, "variant" | "size"> & { floating?: boolean }) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className={cn(
        "size-7 text-muted-foreground/70 opacity-0 transition-all hover:bg-accent hover:text-destructive hover:opacity-100 focus:opacity-100 focus-visible:bg-accent focus-visible:text-destructive focus-visible:opacity-100 group-hover:opacity-70",
        floating && "absolute bottom-1.5 right-1.5 z-10",
        className
      )}
      {...props}
    >
      <Trash2 className="size-3.5" />
    </Button>
  );
}
