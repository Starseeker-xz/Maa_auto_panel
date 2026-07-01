import {
  isBooleanControl,
  isEnumControl,
  isIntegerControl,
  isNumberControl,
  isOneOfEnumControl,
  isPrimitiveArrayControl,
  isStringControl,
  rankWith,
  type JsonSchema,
  type ControlProps
} from "@jsonforms/core";
import { withJsonFormsControlProps } from "@jsonforms/react";
import { vanillaCells, vanillaRenderers } from "@jsonforms/vanilla-renderers";
import type { ReactNode } from "react";

import { HelpTooltip } from "@/components/FormFields";
import { PrimitiveArrayEditor, type PrimitiveArrayItem, type PrimitiveArrayOption, type PrimitiveArrayValue } from "@/components/PrimitiveArrayEditor";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

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
  if (optionsSource(props.schema)) return <DynamicSelectControl {...props} />;
  const enabled = isControlEnabled(props);
  return (
    <FieldFrame props={props}>
      <Input value={typeof data === "string" ? data : ""} disabled={!enabled} onChange={(event) => handleChange(path, event.target.value)} />
    </FieldFrame>
  );
}

function NumberControl(props: ControlProps) {
  const { data, handleChange, path, schema } = props;
  if (optionsSource(schema)) return <DynamicSelectControl {...props} />;
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
      <Select value={data === undefined || data === null ? "" : selectItemValue(data)} disabled={!enabled} onValueChange={(value) => handleChange(path, coerceEnumValue(value, values))}>
        <SelectTrigger>
          <SelectValue placeholder="选择" />
        </SelectTrigger>
        <SelectContent>
          {options.map(({ value, label }) => (
            <SelectItem key={selectItemValue(value)} value={selectItemValue(value)}>
              {label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </FieldFrame>
  );
}

function DynamicSelectControl(props: ControlProps) {
  const { data, handleChange, path, schema } = props;
  const enabled = isControlEnabled(props);
  const dynamic = dynamicOptions(props);
  const options = dynamic.length > 0 ? dynamic : enumOptions(schema);
  const values = options.map((option) => option.value);

  return (
    <FieldFrame props={props}>
      <Select
        value={data === undefined || data === null ? "" : selectItemValue(data)}
        disabled={!enabled}
        onValueChange={(value) => {
          const nextValue = coerceEnumValue(value, values);
          const managedKind = managedParamKind(schema);
          if (managedKind === "runtime-value") {
            const spec = {
              type: "runtime",
              handler: runtimeValueHandler(schema),
              value: nextValue
            };
            if (managedParamValueChange(props, path, nextValue, spec)) return;
            managedParamChange(props, path, spec);
          }
          handleChange(path, nextValue);
        }}
      >
        <SelectTrigger>
          <SelectValue placeholder="选择" />
        </SelectTrigger>
        <SelectContent>
          {options.map(({ value, label }) => (
            <SelectItem key={selectItemValue(value)} value={selectItemValue(value)}>
              {label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </FieldFrame>
  );
}

function PrimitiveArrayControl(props: ControlProps) {
  const { data, enabled, errors, handleChange, label, path, schema, visible } = props;
  if (!visible) return null;

  const itemSchema = arrayItemSchema(schema);
  const values = Array.isArray(data) ? data.filter(isPrimitiveArrayValue) : [];
  const dynamic = dynamicOptions(props);
  const options = (dynamic.length > 0 ? dynamic : enumOptions(itemSchema)).filter((option): option is PrimitiveArrayOption => isPrimitiveArrayValue(option.value));
  const title = label || (typeof schema.title === "string" ? schema.title : path);
  const description = typeof schema.description === "string" ? schema.description : "";
  const managedKind = managedParamKind(schema);
  const checkable = managedKind === "array" || managedKind === "runtime-array";
  const items = checkable ? managedArrayItems(props, path, values) : undefined;

  return (
    <PrimitiveArrayEditor
      title={title}
      description={description}
      values={values}
      items={items}
      options={options}
      unique={schema.uniqueItems === true}
      valueKind={primitiveValueKind(itemSchema)}
      checkable={checkable}
      enabled={enabled}
      errors={errors}
      onChange={(nextValues) => handleChange(path, nextValues)}
      onItemsChange={
        checkable
          ? (nextItems) => {
              managedParamChange(props, path, managedArraySpec(managedKind, nextItems));
            }
          : undefined
      }
    />
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
      <HelpTooltip help={description} label={`${title} 说明`} className="inline-grid" contentClassName="max-w-80" />
    </span>
  );
}

function coerceEnumValue(value: string, enumValues: unknown[]) {
  const match = enumValues.find((item) => selectItemValue(item) === value);
  return match ?? (value === EMPTY_SELECT_VALUE ? "" : value);
}

const EMPTY_SELECT_VALUE = "__linux_maa_empty_select_value__";

function selectItemValue(value: unknown) {
  return String(value) === "" ? EMPTY_SELECT_VALUE : String(value);
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

function arrayItemSchema(schema: ControlProps["schema"]): JsonSchema {
  if (schema.items && typeof schema.items === "object" && !Array.isArray(schema.items)) return schema.items as JsonSchema;
  return {};
}

function primitiveValueKind(schema: ControlProps["schema"]): "string" | "number" | "boolean" {
  if (schema.type === "number" || schema.type === "integer") return "number";
  if (schema.type === "boolean") return "boolean";
  return "string";
}

function isPrimitiveArrayValue(value: unknown): value is PrimitiveArrayValue {
  return value === null || typeof value === "string" || typeof value === "number" || typeof value === "boolean";
}

function dynamicOptions(props: ControlProps): EnumOption[] {
  const source = optionsSource(props.schema);
  if (!source) return [];
  const config = props.config as RendererConfig | undefined;
  const values = config?.dynamicOptions?.[source] || [];
  return values.filter((option): option is EnumOption => Boolean(option) && isPrimitiveArrayValue(option.value) && typeof option.label === "string");
}

function optionsSource(schema: ControlProps["schema"]) {
  const value = (schema as LinuxMaaSchema)["x-optionsSource"];
  return typeof value === "string" ? value : "";
}

function managedParamKind(schema: ControlProps["schema"]) {
  const value = (schema as LinuxMaaSchema)["x-linuxMaaManaged"];
  return typeof value === "string" ? value : "";
}

function managedArrayItems(props: ControlProps, path: string, values: PrimitiveArrayValue[]): PrimitiveArrayItem[] {
  const config = props.config as RendererConfig | undefined;
  const metadata = config?.metadata;
  const managedParams = metadata?.managed_params;
  const spec = managedParams && typeof managedParams === "object" && !Array.isArray(managedParams) ? (managedParams as Record<string, unknown>)[path] : undefined;
  const items = spec && typeof spec === "object" && !Array.isArray(spec) ? (spec as ManagedParamSpec).items : undefined;
  if (!Array.isArray(items)) return values.map((value) => ({ value, enabled: true }));
  return items
    .filter((item): item is ManagedParamItem => Boolean(item) && typeof item === "object" && "value" in item && isPrimitiveArrayValue((item as ManagedParamItem).value))
    .map((item) => ({ value: item.value as PrimitiveArrayValue, enabled: item.enabled !== false }));
}

function managedArraySpec(kind: string, items: PrimitiveArrayItem[]): ManagedParamSpec {
  if (kind === "runtime-array") {
    return {
      type: "runtime",
      handler: "fight_stage",
      items
    };
  }
  return {
    type: "array",
    items
  };
}

function runtimeValueHandler(schema: ControlProps["schema"]) {
  const source = optionsSource(schema);
  if (source === "infrast-plans") return "infrast_plan_index";
  return source || "runtime_value";
}

function managedParamChange(props: ControlProps, path: string, spec: ManagedParamSpec) {
  const config = props.config as RendererConfig | undefined;
  config?.onManagedParamChange?.(path, spec);
}

function managedParamValueChange(props: ControlProps, path: string, value: unknown, spec: ManagedParamSpec) {
  const config = props.config as RendererConfig | undefined;
  if (!config?.onManagedParamValueChange) return false;
  config.onManagedParamValueChange(path, value, spec);
  return true;
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

type LinuxMaaSchema = ConditionalSchema & {
  "x-linuxMaaManaged"?: string;
  "x-optionsSource"?: string;
};

type ManagedParamItem = {
  value: unknown;
  enabled?: boolean;
};

type ManagedParamSpec = {
  type?: string;
  handler?: string;
  value?: unknown;
  items?: ManagedParamItem[];
};

type RendererConfig = {
  rootData?: Record<string, unknown>;
  metadata?: {
    managed_params?: Record<string, ManagedParamSpec>;
    [key: string]: unknown;
  };
  dynamicOptions?: Record<string, EnumOption[]>;
  onManagedParamChange?: (path: string, spec: ManagedParamSpec) => void;
  onManagedParamValueChange?: (path: string, value: unknown, spec: ManagedParamSpec) => void;
};

type FieldCondition = {
  field?: string;
  equals?: unknown;
  notEquals?: unknown;
};

export const linuxMaaRenderers = [
  { tester: rankWith(8, (uischema, schema, context) => Boolean((schema as LinuxMaaSchema)["x-optionsSource"]) && (isStringControl(uischema, schema, context) || isIntegerControl(uischema, schema, context) || isNumberControl(uischema, schema, context))), renderer: withJsonFormsControlProps(DynamicSelectControl) },
  { tester: rankWith(7, isPrimitiveArrayControl), renderer: withJsonFormsControlProps(PrimitiveArrayControl) },
  { tester: rankWith(6, isOneOfEnumControl), renderer: withJsonFormsControlProps(EnumControl) },
  { tester: rankWith(5, isEnumControl), renderer: withJsonFormsControlProps(EnumControl) },
  { tester: rankWith(4, isBooleanControl), renderer: withJsonFormsControlProps(BooleanCheckboxControl) },
  { tester: rankWith(3, isIntegerControl), renderer: withJsonFormsControlProps(NumberControl) },
  { tester: rankWith(3, isNumberControl), renderer: withJsonFormsControlProps(NumberControl) },
  { tester: rankWith(3, isStringControl), renderer: withJsonFormsControlProps(TextControl) },
  ...vanillaRenderers
];

export const linuxMaaCells = vanillaCells;
