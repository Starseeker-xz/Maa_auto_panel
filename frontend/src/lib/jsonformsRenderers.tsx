import {
  isBooleanControl,
  isEnumControl,
  isIntegerControl,
  isNumberControl,
  isOneOfEnumControl,
  isStringControl,
  rankWith,
  type ControlProps
} from "@jsonforms/core";
import { withJsonFormsControlProps } from "@jsonforms/react";
import { vanillaCells, vanillaRenderers } from "@jsonforms/vanilla-renderers";
import { HelpCircle } from "lucide-react";
import type { ReactNode } from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

function BooleanCheckboxControl(props: ControlProps) {
  const { data, handleChange, path } = props;
  const enabled = isControlEnabled(props);
  return (
    <FieldFrame props={props} inline>
      <Checkbox checked={Boolean(data)} disabled={!enabled} onCheckedChange={(checked) => handleChange(path, checked === true)} />
    </FieldFrame>
  );
}

function TextControl(props: ControlProps) {
  const { data, handleChange, path } = props;
  const enabled = isControlEnabled(props);
  return (
    <FieldFrame props={props}>
      <Input value={typeof data === "string" ? data : ""} disabled={!enabled} onChange={(event) => handleChange(path, event.target.value)} />
    </FieldFrame>
  );
}

function NumberControl(props: ControlProps) {
  const { data, handleChange, path, schema } = props;
  const enabled = isControlEnabled(props);
  return (
    <FieldFrame props={props}>
      <Input
        type="number"
        min={typeof schema.minimum === "number" ? schema.minimum : undefined}
        max={typeof schema.maximum === "number" ? schema.maximum : undefined}
        value={typeof data === "number" ? data : ""}
        disabled={!enabled}
        onChange={(event) => {
          const value = event.target.value;
          handleChange(path, value === "" ? undefined : Number(value));
        }}
      />
    </FieldFrame>
  );
}

function EnumControl(props: ControlProps) {
  const { data, handleChange, path, schema } = props;
  const enabled = isControlEnabled(props);
  const options = enumOptions(schema);
  const values = options.map((option) => option.value);

  return (
    <FieldFrame props={props}>
      <Select value={data === undefined || data === null ? "" : String(data)} disabled={!enabled} onValueChange={(value) => handleChange(path, coerceEnumValue(value, values))}>
        <SelectTrigger>
          <SelectValue placeholder="选择" />
        </SelectTrigger>
        <SelectContent>
          {options.map(({ value, label }) => (
            <SelectItem key={String(value)} value={String(value)}>
              {label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </FieldFrame>
  );
}

function FieldFrame({ props, children, inline = false }: { props: ControlProps; children: ReactNode; inline?: boolean }) {
  const title = props.label || (typeof props.schema.title === "string" ? props.schema.title : props.path);
  const description = typeof props.schema.description === "string" ? props.schema.description : "";
  const enabled = isControlEnabled(props);

  if (inline) {
    return (
      <label className={`flex min-h-9 items-center gap-2 rounded-md border bg-background px-2.5 py-2 ${enabled ? "cursor-pointer" : "opacity-60"}`}>
        {children}
        <FieldLabel title={title} description={description} />
      </label>
    );
  }

  return (
    <div className="grid gap-1.5">
      <FieldLabel title={title} description={description} />
      {children}
      {props.errors ? <div className="text-xs text-destructive">{props.errors}</div> : null}
    </div>
  );
}

function FieldLabel({ title, description }: { title: string; description: string }) {
  if (!description) return <span className="text-sm text-foreground">{title}</span>;

  return (
    <span className="inline-flex w-fit items-center gap-1.5 text-sm text-foreground">
      <span>{title}</span>
      <Tooltip>
      <TooltipTrigger asChild>
          <button
            type="button"
            data-tooltip-help
            className="inline-grid size-4 place-items-center rounded-full text-muted-foreground hover:text-foreground"
            aria-label={`${title} 说明`}
          >
            <HelpCircle className="size-3.5" />
          </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-80">{description}</TooltipContent>
      </Tooltip>
    </span>
  );
}

function coerceEnumValue(value: string, enumValues: unknown[]) {
  const match = enumValues.find((item) => String(item) === value);
  return match ?? value;
}

type EnumOption = {
  value: unknown;
  label: string;
};

function enumOptions(schema: ControlProps["schema"]): EnumOption[] {
  if (Array.isArray(schema.oneOf)) {
    const options = schema.oneOf
      .map((item) => {
        if (!item || typeof item !== "object" || !("const" in item)) return undefined;
        const value = item.const;
        const label = typeof item.title === "string" ? item.title : String(value);
        return { value, label };
      })
      .filter((item): item is EnumOption => Boolean(item));
    if (options.length > 0) return options;
  }

  const values = Array.isArray(schema.enum) ? schema.enum : [];
  return values.map((value) => ({ value, label: String(value) }));
}

function isControlEnabled(props: ControlProps) {
  if (!props.enabled) return false;
  const schema = props.schema as ConditionalSchema;
  const enabledWhen = schema["x-enabledWhen"];
  if (Array.isArray(enabledWhen) && !enabledWhen.every((condition) => matchesCondition(props, condition))) return false;

  const disabledWhen = schema["x-disabledWhen"];
  if (!Array.isArray(disabledWhen)) return true;
  return !disabledWhen.some((condition) => {
    return matchesCondition(props, condition);
  });
}

function matchesCondition(props: ControlProps, condition: FieldCondition) {
  if (!condition || typeof condition !== "object") return false;
  const field = typeof condition.field === "string" ? condition.field : "";
  if (!field) return false;

  const actual = rootValue(props, field);
  if ("equals" in condition) return actual === condition.equals;
  if ("notEquals" in condition) return actual !== condition.notEquals;
  return false;
}

function rootValue(props: ControlProps, field: string) {
  const rootData = props.config?.rootData;
  if (rootData && rootData[field] !== undefined) return rootData[field];

  const rootProperties = props.rootSchema.properties;
  if (rootProperties && typeof rootProperties === "object") {
    const fieldSchema = rootProperties[field];
    if (fieldSchema && typeof fieldSchema === "object" && "default" in fieldSchema) return fieldSchema.default;
  }
  return undefined;
}

type ConditionalSchema = ControlProps["schema"] & {
  "x-enabledWhen"?: FieldCondition[];
  "x-disabledWhen"?: FieldCondition[];
};

type FieldCondition = {
  field?: string;
  equals?: unknown;
  notEquals?: unknown;
};

export const linuxMaaRenderers = [
  { tester: rankWith(6, isOneOfEnumControl), renderer: withJsonFormsControlProps(EnumControl) },
  { tester: rankWith(5, isEnumControl), renderer: withJsonFormsControlProps(EnumControl) },
  { tester: rankWith(4, isBooleanControl), renderer: withJsonFormsControlProps(BooleanCheckboxControl) },
  { tester: rankWith(3, isIntegerControl), renderer: withJsonFormsControlProps(NumberControl) },
  { tester: rankWith(3, isNumberControl), renderer: withJsonFormsControlProps(NumberControl) },
  { tester: rankWith(3, isStringControl), renderer: withJsonFormsControlProps(TextControl) },
  ...vanillaRenderers
];

export const linuxMaaCells = vanillaCells;
