import { cn } from "@/lib/utils";

export function InsertionLine({ active, position }: { active: boolean; position: "first" | "top" | "bottom" }) {
  if (!active) return null;
  const positionClass = position === "first" ? "top-0" : position === "top" ? "-top-1" : "-bottom-1";
  return <div className={cn("pointer-events-none absolute left-1 right-1 z-10 h-0.5 rounded-full bg-primary", positionClass)} />;
}
