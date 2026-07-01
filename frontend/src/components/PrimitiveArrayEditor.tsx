import React from "react";
import * as SelectPrimitive from "@radix-ui/react-select";
import { GripVertical, PencilLine, Plus, Trash2 } from "lucide-react";

import { HelpTooltip } from "@/components/FormFields";
import { InsertionLine } from "@/components/InsertionLine";
import { Button, buttonVariants } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem } from "@/components/ui/select";
import { cn } from "@/lib/utils";

export type PrimitiveArrayValue = string | number | boolean | null;

export type PrimitiveArrayOption = {
  value: PrimitiveArrayValue;
  label: string;
};

export type PrimitiveArrayItem = {
  value: PrimitiveArrayValue;
  enabled?: boolean;
};

type PrimitiveArrayEditorProps = {
  title: string;
  description?: string;
  values: PrimitiveArrayValue[];
  items?: PrimitiveArrayItem[];
  options?: PrimitiveArrayOption[];
  unique?: boolean;
  valueKind?: "string" | "number" | "boolean";
  checkable?: boolean;
  enabled?: boolean;
  errors?: string;
  onChange: (values: PrimitiveArrayValue[]) => void;
  onItemsChange?: (items: PrimitiveArrayItem[]) => void;
};

export function PrimitiveArrayEditor({
  title,
  description = "",
  values,
  items,
  options = [],
  unique = false,
  valueKind = "string",
  checkable = false,
  enabled = true,
  errors = "",
  onChange,
  onItemsChange
}: PrimitiveArrayEditorProps) {
  const constrained = options.length > 0;
  const rows = React.useMemo<PrimitiveArrayItem[]>(() => items ?? values.map((value) => ({ value, enabled: true })), [items, values]);
  const [draggingIndex, setDraggingIndex] = React.useState<number | null>(null);
  const [dropIndex, setDropIndex] = React.useState<number | null>(null);
  const [renamingIndex, setRenamingIndex] = React.useState<number | null>(null);
  const [renameDraft, setRenameDraft] = React.useState("");
  const skipRenameBlurCommit = React.useRef(false);
  const selectedKeys = React.useMemo(() => rows.map((row) => valueKey(row.value)), [rows]);
  const availableAddOptions = constrained && unique ? options.filter((option) => !selectedKeys.includes(valueKey(option.value))) : options;

  function emitRows(nextRows: PrimitiveArrayItem[]) {
    onItemsChange?.(nextRows);
    onChange(nextRows.map((row) => row.value));
  }

  function updateDropIndex(event: React.DragEvent<HTMLElement>, index: number) {
    if (!enabled) return;
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    const nextIndex = event.clientY < rect.top + rect.height / 2 ? index : index + 1;
    setDropIndex(nextIndex);
    event.dataTransfer.dropEffect = "move";
  }

  function handleDrop(event: React.DragEvent<HTMLElement>) {
    event.preventDefault();
    if (!enabled || draggingIndex === null || dropIndex === null) {
      setDraggingIndex(null);
      setDropIndex(null);
      return;
    }

    const adjustedTargetIndex = dropIndex > draggingIndex ? dropIndex - 1 : dropIndex;
    if (adjustedTargetIndex !== draggingIndex) {
      const next = [...rows];
      const [moved] = next.splice(draggingIndex, 1);
      next.splice(adjustedTargetIndex, 0, moved);
      emitRows(next);
    }
    setDraggingIndex(null);
    setDropIndex(null);
  }

  function appendFreeItem() {
    if (!enabled) return;
    const nextValue = nextFreeValue(rows.map((row) => row.value), valueKind, unique);
    emitRows([...rows, { value: nextValue, enabled: true }]);
    setRenamingIndex(rows.length);
    setRenameDraft(displayValue(nextValue));
  }

  function appendOption(rawValue: string) {
    const option = options.find((item) => selectValueKey(item.value) === rawValue);
    if (!option || !enabled) return;
    emitRows([...rows, { value: option.value, enabled: true }]);
  }

  function removeAt(index: number) {
    if (!enabled) return;
    if (renamingIndex === index) cancelRename();
    emitRows(rows.filter((_, itemIndex) => itemIndex !== index));
  }

  function startRename(index: number) {
    skipRenameBlurCommit.current = false;
    setRenamingIndex(index);
    setRenameDraft(displayValue(rows[index]?.value ?? ""));
  }

  function commitRename() {
    if (skipRenameBlurCommit.current) {
      skipRenameBlurCommit.current = false;
      return;
    }
    if (renamingIndex === null || !enabled) return;
    const nextValue = parseEditedValue(renameDraft, valueKind);
    if (unique && rows.some((row, index) => index !== renamingIndex && valueKey(row.value) === valueKey(nextValue))) {
      cancelRename();
      return;
    }
    const next = [...rows];
    next[renamingIndex] = { ...next[renamingIndex], value: nextValue };
    emitRows(next);
    setRenamingIndex(null);
    setRenameDraft("");
  }

  function cancelRename() {
    skipRenameBlurCommit.current = true;
    setRenamingIndex(null);
    setRenameDraft("");
  }

  function changeOption(index: number, rawValue: string) {
    const option = options.find((item) => selectValueKey(item.value) === rawValue);
    if (!option || !enabled) return;
    const next = [...rows];
    const existingIndex = unique ? next.findIndex((row) => valueKey(row.value) === valueKey(option.value)) : -1;
    if (existingIndex >= 0 && existingIndex !== index) {
      next[existingIndex] = next[index];
      next[index] = { ...next[index], value: option.value };
      emitRows(next);
      return;
    }
    next[index] = { ...next[index], value: option.value };
    emitRows(next);
  }

  function setItemEnabled(index: number, nextEnabled: boolean) {
    if (!enabled) return;
    const next = [...rows];
    next[index] = { ...next[index], enabled: nextEnabled };
    emitRows(next);
  }

  return (
    <section className={cn("grid min-w-0 gap-2 rounded-md border bg-background p-2", !enabled && "opacity-60")}>
      <div className="flex min-w-0 items-center justify-between gap-2">
        <ArrayTitle title={title} description={description} />
        {constrained ? (
          <Select value="" disabled={!enabled} onValueChange={appendOption}>
            <IconSelectTrigger label={`新增${title}`} variant="outline" className="size-8 active:scale-95">
              <Plus className="size-4" />
            </IconSelectTrigger>
            <SelectContent align="end">
              {availableAddOptions.length > 0 ? (
                availableAddOptions.map((option) => (
                  <SelectItem key={selectValueKey(option.value)} value={selectValueKey(option.value)}>
                    {option.label}
                  </SelectItem>
                ))
              ) : (
                <SelectItem value="__linux_maa_no_available_options" disabled>
                  已全部添加
                </SelectItem>
              )}
            </SelectContent>
          </Select>
        ) : (
          <Button type="button" variant="outline" size="icon" className="size-8 shrink-0 active:scale-95" disabled={!enabled} aria-label={`新增${title}`} onClick={appendFreeItem}>
            <Plus className="size-4" />
          </Button>
        )}
      </div>

      <div
        className="grid min-w-0 gap-1.5"
        onDragLeave={(event) => {
          const nextTarget = event.relatedTarget as Node | null;
          if (nextTarget && event.currentTarget.contains(nextTarget)) return;
          setDropIndex(null);
        }}
      >
        {rows.length === 0 ? <div className="rounded-md border border-dashed bg-muted/20 px-2 py-3 text-center text-xs text-muted-foreground">暂无项目</div> : null}
        {rows.map((row, index) => {
          const value = row.value;
          const label = optionLabel(options, value);
          return (
            <div key={`${index}-${valueKey(value)}`} className="relative" onDragOver={(event) => updateDropIndex(event, index)} onDrop={handleDrop}>
              <InsertionLine active={draggingIndex !== null && dropIndex === index && draggingIndex !== index} position={index === 0 ? "first" : "top"} />
              <div
                data-array-row
                data-dragging={draggingIndex === index ? "true" : undefined}
                className={cn(
                  "group grid h-10 min-w-0 items-center gap-1.5 rounded-md border bg-card px-2 shadow-xs transition-all hover:-translate-y-px hover:border-border/80 hover:shadow-md data-[dragging=true]:scale-[0.98] data-[dragging=true]:opacity-45",
                  checkable ? "grid-cols-[22px_minmax(0,1fr)_74px]" : "grid-cols-[minmax(0,1fr)_74px]"
                )}
              >
                {checkable ? (
                  <Checkbox checked={row.enabled !== false} disabled={!enabled} aria-label={`${label} 启用`} onCheckedChange={(checked) => setItemEnabled(index, checked === true)} />
                ) : null}
                {renamingIndex === index && !constrained ? (
                  <Input
                    className="h-7 min-w-0 px-2"
                    value={renameDraft}
                    onChange={(event) => setRenameDraft(event.target.value)}
                    onBlur={commitRename}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") commitRename();
                      if (event.key === "Escape") cancelRename();
                    }}
                    autoFocus
                  />
                ) : (
                  <div className="grid min-w-0 gap-0.5">
                    <span className="truncate text-sm">{label || "未命名"}</span>
                  </div>
                )}
                <div className="flex items-center justify-end gap-0.5">
                  {constrained ? (
                    <Select value={selectValueKey(value)} disabled={!enabled} onValueChange={(nextValue) => changeOption(index, nextValue)}>
                      <IconSelectTrigger label={`${label} 选择`} variant="ghost" className="size-7 text-muted-foreground/70 opacity-0 hover:text-foreground hover:opacity-100 focus-visible:opacity-100 group-hover:opacity-70">
                        <PencilLine className="size-3.5" />
                      </IconSelectTrigger>
                      <SelectContent align="end">
                        {options.map((option) => (
                          <SelectItem key={selectValueKey(option.value)} value={selectValueKey(option.value)}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-7 text-muted-foreground/70 opacity-0 transition-opacity hover:text-foreground hover:opacity-100 focus-visible:opacity-100 group-hover:opacity-70"
                      aria-label={`${label} 重命名`}
                      disabled={!enabled}
                      onClick={() => startRename(index)}
                    >
                      <PencilLine className="size-3.5" />
                    </Button>
                  )}
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-7 text-muted-foreground/70 opacity-0 transition-opacity hover:text-destructive hover:opacity-100 focus-visible:opacity-100 group-hover:opacity-70"
                    aria-label={`${label} 删除`}
                    disabled={!enabled}
                    onClick={() => removeAt(index)}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                  <div
                    className={buttonVariants({ variant: "ghost", size: "icon", className: "size-7 cursor-grab active:cursor-grabbing" })}
                    role="button"
                    tabIndex={0}
                    aria-label={`${label} 拖动排序`}
                    draggable={enabled}
                    onDragStart={(event) => {
                      if (!enabled) return;
                      setDraggingIndex(index);
                      setDropIndex(index);
                      event.dataTransfer.effectAllowed = "move";
                      event.dataTransfer.setData("text/array-index", String(index));
                      const row = event.currentTarget.closest("[data-array-row]");
                      if (row instanceof HTMLElement) event.dataTransfer.setDragImage(row, 16, 20);
                    }}
                    onDragEnd={() => {
                      setDraggingIndex(null);
                      setDropIndex(null);
                    }}
                  >
                    <GripVertical className="size-4 text-muted-foreground" />
                  </div>
                </div>
              </div>
              <InsertionLine active={draggingIndex !== null && dropIndex === rows.length && index === rows.length - 1} position="bottom" />
            </div>
          );
        })}
      </div>
      {errors ? <div className="text-xs text-destructive">{errors}</div> : null}
    </section>
  );
}

function ArrayTitle({ title, description }: { title: string; description: string }) {
  return (
    <div className="inline-flex min-w-0 items-center gap-1.5 text-sm font-medium">
      <span className="truncate">{title}</span>
      {description ? <HelpTooltip help={description} label={`${title} 说明`} contentClassName="max-w-80" /> : null}
    </div>
  );
}

function IconSelectTrigger({
  label,
  variant,
  className,
  children
}: {
  label: string;
  variant: "ghost" | "outline";
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <SelectPrimitive.Trigger asChild aria-label={label}>
      <Button type="button" variant={variant} size="icon" className={cn("shrink-0", className)}>
        {children}
      </Button>
    </SelectPrimitive.Trigger>
  );
}

function optionLabel(options: PrimitiveArrayOption[], value: PrimitiveArrayValue) {
  return options.find((option) => valueKey(option.value) === valueKey(value))?.label || displayValue(value);
}

function valueKey(value: PrimitiveArrayValue) {
  return String(value);
}

const EMPTY_SELECT_VALUE = "__linux_maa_empty_select_value__";

function selectValueKey(value: PrimitiveArrayValue) {
  const key = valueKey(value);
  return key === "" ? EMPTY_SELECT_VALUE : key;
}

function displayValue(value: PrimitiveArrayValue) {
  return value === null || value === undefined ? "" : String(value);
}

function parseEditedValue(value: string, valueKind: PrimitiveArrayEditorProps["valueKind"]) {
  if (valueKind === "number") {
    const numberValue = Number(value);
    return Number.isFinite(numberValue) ? numberValue : 0;
  }
  if (valueKind === "boolean") return value === "true";
  return value;
}

function nextFreeValue(values: PrimitiveArrayValue[], valueKind: PrimitiveArrayEditorProps["valueKind"], unique: boolean) {
  if (valueKind === "number") return unique ? nextFreeNumber(values) : 0;
  if (valueKind === "boolean") return false;

  let index = 1;
  let candidate = "新项目";
  const used = new Set(values.map(valueKey));
  while (unique && used.has(candidate)) {
    index += 1;
    candidate = `新项目 ${index}`;
  }
  return candidate;
}

function nextFreeNumber(values: PrimitiveArrayValue[]) {
  const used = new Set(values.map(valueKey));
  let candidate = 0;
  while (used.has(String(candidate))) candidate += 1;
  return candidate;
}
