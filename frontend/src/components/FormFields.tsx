import { CircleHelp } from "lucide-react";

import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

type SelectFieldOption = ReadonlyArray<string>;

export function HelpTooltip({
  help,
  label = "说明",
  className,
  contentClassName
}: {
  help: string;
  label?: string;
  className?: string;
  contentClassName?: string;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          data-tooltip-help
          className={cn(
            "grid size-4 shrink-0 place-items-center rounded-full text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            className
          )}
          aria-label={label}
        >
          <CircleHelp className="size-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" sideOffset={6} className={cn("max-w-xs leading-5 shadow-md sm:max-w-sm", contentClassName)}>
        {help}
      </TooltipContent>
    </Tooltip>
  );
}

function FieldLabel({ label, help, className }: { label: string; help?: string; className?: string }) {
  return (
    <div className={cn("flex min-w-0 items-center gap-1.5 text-xs font-medium text-muted-foreground", className)}>
      <span className="min-w-0 truncate">{label}</span>
      {help ? <HelpTooltip help={help} label={`${label} 说明`} /> : null}
    </div>
  );
}

export function SectionTitle({ label, help }: { label: string; help?: string }) {
  return <FieldLabel label={label} help={help} className="pt-1" />;
}

export function TextField({
  label,
  value,
  help,
  disabled = false,
  list,
  onChange
}: {
  label: string;
  value: string;
  help?: string;
  disabled?: boolean;
  list?: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="grid min-w-0 gap-1.5">
      <FieldLabel label={label} help={help} />
      <Input className="min-w-0" value={value} disabled={disabled} list={list} onChange={(event) => onChange(event.target.value)} />
    </div>
  );
}

export function NumberField({
  label,
  value,
  help,
  disabled = false,
  min,
  max,
  onChange
}: {
  label: string;
  value: number | "";
  help?: string;
  disabled?: boolean;
  min?: number;
  max?: number;
  onChange: (value: number | "") => void;
}) {
  return (
    <div className="grid min-w-0 gap-1.5">
      <FieldLabel label={label} help={help} />
      <Input
        className="min-w-0"
        type="number"
        min={min}
        max={max}
        value={value}
        disabled={disabled}
        onChange={(event) => {
          const next = event.target.value;
          onChange(next === "" ? "" : Number(next));
        }}
      />
    </div>
  );
}

export function SelectField({
  label,
  value,
  help,
  options,
  disabled = false,
  placeholder,
  onChange
}: {
  label: string;
  value: string;
  help?: string;
  options: ReadonlyArray<SelectFieldOption>;
  disabled?: boolean;
  placeholder?: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="grid min-w-0 gap-1.5">
      <FieldLabel label={label} help={help} />
      <Select value={value} disabled={disabled} onValueChange={onChange}>
        <SelectTrigger className="min-w-0">
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => {
            const optionValue = option[0] || "";
            const labelText = option[1] || optionValue;
            return (
              <SelectItem key={optionValue} value={optionValue}>
                {labelText}
              </SelectItem>
            );
          })}
        </SelectContent>
      </Select>
    </div>
  );
}

export function CheckboxField({
  label,
  checked,
  help,
  disabled = false,
  onChange
}: {
  label: string;
  checked: boolean;
  help?: string;
  disabled?: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className={cn("min-w-0 rounded-md border bg-background p-2 text-sm", disabled && "opacity-55")}>
      <span className="flex min-h-5 min-w-0 items-start gap-2">
        <Checkbox checked={checked} disabled={disabled} onCheckedChange={(value) => onChange(value === true)} />
        <span className="flex min-w-0 flex-1 items-center gap-1.5 leading-5">
          <span className="min-w-0 break-words">{label}</span>
          {help ? <HelpTooltip help={help} label={`${label} 说明`} /> : null}
        </span>
      </span>
    </label>
  );
}

export function ReadOnlyLine({ label, value, help }: { label: string; value: string; help?: string }) {
  return (
    <div className="grid min-w-0 gap-1.5">
      <FieldLabel label={label} help={help} />
      <div className="break-anywhere min-h-9 rounded-md border bg-muted/30 px-2 py-2 text-sm">{value}</div>
    </div>
  );
}

export function PathLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid min-w-0 gap-1 border-t pt-3">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <span className="break-anywhere text-xs text-muted-foreground">{value}</span>
    </div>
  );
}
