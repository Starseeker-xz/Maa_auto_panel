import React from "react";
import { Plus } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export type CreatableStringOption = {
  value: string;
  label: string;
};

type CreatableStringPickerProps = {
  label: string;
  options: CreatableStringOption[];
  currentValue?: string;
  disabled?: boolean;
  children: React.ReactElement;
  onSelect: (value: string) => void;
};

export function CreatableStringPicker({ label, options, currentValue, disabled = false, children, onSelect }: CreatableStringPickerProps) {
  const listboxId = React.useId();
  const openedByPointer = React.useRef(false);
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [activeIndex, setActiveIndex] = React.useState(-1);
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const filteredOptions = options.filter((option) => {
    if (!normalizedQuery) return true;
    return option.label.toLocaleLowerCase().includes(normalizedQuery) || option.value.toLocaleLowerCase().includes(normalizedQuery);
  });
  const customValue = query.trim();
  const customMatchesKnownValue = options.some((option) => option.value === customValue);
  const canCreate = customValue.length > 0 && !customMatchesKnownValue;

  function select(value: string) {
    onSelect(value);
    setOpen(false);
  }

  function handleOpenChange(nextOpen: boolean) {
    setOpen(nextOpen);
    if (!nextOpen) return;
    const knownCurrent = currentValue !== undefined && options.some((option) => option.value === currentValue);
    setQuery(knownCurrent ? "" : currentValue || "");
    setActiveIndex(-1);
  }

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger
        asChild
        disabled={disabled}
        aria-label={label}
        onPointerDown={() => {
          openedByPointer.current = true;
        }}
      >
        {children}
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="w-80 p-2"
        onCloseAutoFocus={(event) => {
          if (!openedByPointer.current) return;
          event.preventDefault();
          openedByPointer.current = false;
        }}
      >
        <Input
          role="combobox"
          aria-label={`${label}搜索或输入`}
          aria-expanded={open}
          aria-controls={listboxId}
          placeholder="搜索推荐项或输入自定义关卡名"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setActiveIndex(-1);
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown" && filteredOptions.length > 0) {
              event.preventDefault();
              setActiveIndex((current) => (current + 1) % filteredOptions.length);
            } else if (event.key === "ArrowUp" && filteredOptions.length > 0) {
              event.preventDefault();
              setActiveIndex((current) => (current <= 0 ? filteredOptions.length - 1 : current - 1));
            } else if (event.key === "Enter") {
              event.preventDefault();
              if (activeIndex >= 0 && filteredOptions[activeIndex]) select(filteredOptions[activeIndex].value);
              else if (canCreate) select(customValue);
            }
          }}
          autoFocus
        />
        <div id={listboxId} role="listbox" className="mt-2 grid max-h-64 gap-0.5 overflow-y-auto">
          {canCreate ? (
            <button
              type="button"
              className="flex min-h-9 w-full items-center gap-2 rounded-sm px-2 text-left text-sm hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent focus-visible:outline-hidden"
              onClick={() => select(customValue)}
            >
              <Plus className="size-4 shrink-0" />
              <span className="min-w-0 truncate">将“{customValue}”作为自定义关卡添加</span>
            </button>
          ) : null}
          {filteredOptions.map((option, index) => (
            <button
              key={option.value}
              type="button"
              role="option"
              aria-selected={option.value === currentValue}
              className={cn(
                "min-h-9 w-full rounded-sm px-2 text-left text-sm hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent focus-visible:outline-hidden",
                activeIndex === index && "bg-accent text-accent-foreground"
              )}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => select(option.value)}
            >
              <span className="block truncate">{option.label}</span>
            </button>
          ))}
          {filteredOptions.length === 0 && !canCreate ? <div className="px-2 py-3 text-center text-xs text-muted-foreground">请输入非空关卡名</div> : null}
        </div>
      </PopoverContent>
    </Popover>
  );
}
