import React from "react";
import { JsonForms } from "@jsonforms/react";
import { AlertTriangle } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { frameworkCells, frameworkRenderers } from "@/lib/jsonformsRenderers";
import type { ConfigValidation, ManagedParamSpec, TaskItem } from "@/lib/types";
import { schemaForTaskType } from "@/lib/taskSchemas";
import { cn } from "@/lib/utils";
import { useTaskDynamicOptions } from "@/pages/main/useTaskDynamicOptions";

type EditorMode = "general" | "advanced";

type ConfigEditorPaneProps = {
  taskConfig: string;
  selectedTaskItem?: TaskItem;
  validation?: ConfigValidation;
  onTaskItemUpdate: (itemId: string, patch: Partial<Pick<TaskItem, "params" | "framework">>) => void;
};

export function ConfigEditorPane({ taskConfig, selectedTaskItem, validation, onTaskItemUpdate }: ConfigEditorPaneProps) {
  const [mode, setMode] = React.useState<EditorMode>("general");
  const [params, setParams] = React.useState<Record<string, unknown>>({});
  const [metadata, setMetadata] = React.useState<Record<string, unknown>>({});
  const dynamicOptions = useTaskDynamicOptions(selectedTaskItem, params);

  React.useEffect(() => {
    setMode("general");
  }, [selectedTaskItem?.id]);

  React.useEffect(() => {
    setParams({ ...(selectedTaskItem?.params || {}) });
    setMetadata({ ...(selectedTaskItem?.framework || {}) });
  }, [selectedTaskItem]);

  const editorSchema = selectedTaskItem ? schemaForTaskType(selectedTaskItem.type) : undefined;
  const currentUiSchema = mode === "general" ? editorSchema?.general : editorSchema?.advanced;
  const hasAdvanced = Boolean(editorSchema?.advanced);
  const validationErrors = validation?.errors || [];

  if (!selectedTaskItem) {
    return (
      <Card className="grid h-full min-h-0 grid-rows-[auto_minmax(240px,1fr)] gap-3 p-3">
        <ModeTabs hasAdvanced={false} />
        <div className="grid place-items-center rounded-md border border-dashed bg-muted/20">
          <div className="grid gap-1 text-center">
            <div className="font-semibold">{taskConfig || "未选择任务配置"}</div>
            <div className="text-sm text-muted-foreground">从左侧选择一个子任务进入配置编辑</div>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Tabs value={mode} onValueChange={(value) => setMode(value as EditorMode)} className="h-full min-h-0">
      <Card className="grid h-full min-h-0 grid-rows-[auto_minmax(240px,1fr)] gap-3 overflow-hidden p-3">
        <div className="flex items-center justify-between gap-3">
          <ModeTabs hasAdvanced={hasAdvanced} />
          <div className="min-w-0 text-right">
            <div className="truncate text-sm font-medium">{selectedTaskItem.name}</div>
            <div className="text-xs text-muted-foreground">
              {selectedTaskItem.type}
              {typeof metadata.id === "string" && metadata.id ? <span className="ml-2 font-mono opacity-60">#{metadata.id}</span> : null}
            </div>
          </div>
        </div>

        <TabsContent value={mode} className="min-h-0">
          <ScrollArea className="h-full min-h-0">
            <div className="grid gap-3 pr-3">
              {validationErrors.length > 0 ? <ValidationPanel validation={validation} /> : null}

              <section className="grid gap-2 rounded-md border bg-background p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium">定时执行配置</div>
                  <span className="rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">单次运行不受该配置影响</span>
                </div>
                <MetadataEditor
                  metadata={metadata}
                  onChange={(nextMetadata) => {
                    setMetadata(nextMetadata);
                    onTaskItemUpdate(selectedTaskItem.id, { framework: nextMetadata });
                  }}
                />
              </section>

              <section className="jsonforms-surface grid gap-2 rounded-md border bg-background p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium">{mode === "general" ? "常规设置" : "高级设置"}</div>
                  {!editorSchema ? <span className="rounded-md bg-amber-50 px-2 py-0.5 text-xs text-amber-700">未知任务类型</span> : null}
                </div>

                {editorSchema && currentUiSchema ? (
                  <JsonForms
                    schema={editorSchema.schema}
                    uischema={currentUiSchema}
                    data={params}
                    renderers={frameworkRenderers}
                    cells={frameworkCells}
                    config={{
                      rootData: params,
                      metadata,
                      dynamicOptions,
                      onManagedParamChange: (path: string, spec: ManagedParamSpec) => {
                        const nextMetadata = withManagedParam(metadata, path, spec);
                        setMetadata(nextMetadata);
                        onTaskItemUpdate(selectedTaskItem.id, { framework: nextMetadata });
                      },
                      onManagedParamValueChange: (path: string, value: unknown, spec: ManagedParamSpec) => {
                        const nextParams = { ...params, [path]: value };
                        const nextMetadata = withManagedParam(metadata, path, spec);
                        setParams(nextParams);
                        setMetadata(nextMetadata);
                        onTaskItemUpdate(selectedTaskItem.id, { params: nextParams, framework: nextMetadata });
                      }
                    }}
                    onChange={({ data }) => {
                      const nextParams = data || {};
                      if (jsonEqual(nextParams, params)) return;
                      setParams(nextParams);
                      onTaskItemUpdate(selectedTaskItem.id, { params: nextParams });
                    }}
                  />
                ) : editorSchema && mode === "advanced" && !currentUiSchema ? (
                  <div className="rounded-md border border-dashed bg-muted/20 p-3 text-sm text-muted-foreground">该任务没有高级设置。</div>
                ) : (
                  <div className="rounded-md border border-dashed bg-muted/20 p-3 text-sm text-muted-foreground">
                    当前任务类型还没有接入可视化编辑模板。
                  </div>
                )}
              </section>
            </div>
          </ScrollArea>
        </TabsContent>
      </Card>
    </Tabs>
  );
}

function jsonEqual(left: unknown, right: unknown) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function withManagedParam(metadata: Record<string, unknown>, path: string, spec: ManagedParamSpec) {
  const managedParams = metadata.managed_params && typeof metadata.managed_params === "object" && !Array.isArray(metadata.managed_params)
    ? (metadata.managed_params as Record<string, ManagedParamSpec>)
    : {};
  return {
    ...metadata,
    managed_params: {
      ...managedParams,
      [path]: spec
    }
  };
}

function ModeTabs({ hasAdvanced }: { hasAdvanced: boolean }) {
  if (!hasAdvanced) {
    return <div className="rounded-md border bg-background px-3 py-1.5 text-sm font-medium">常规设置</div>;
  }

  return (
    <TabsList aria-label="配置模式">
      <TabsTrigger value="general">常规设置</TabsTrigger>
      <TabsTrigger value="advanced">高级设置</TabsTrigger>
    </TabsList>
  );
}

function ValidationPanel({ validation }: { validation?: ConfigValidation }) {
  const errors = validation?.errors || [];
  return (
    <section className="grid gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-red-800">
      <div className="flex items-center gap-2 font-medium">
        <AlertTriangle className="size-4" />
        配置校验未通过
      </div>
      <div className="grid gap-1 text-xs">
        {errors.slice(0, 6).map((error, index) => (
          <div key={`${error.path}-${index}`} className="break-anywhere">
            [{error.source}] {error.path}: {error.message}
          </div>
        ))}
        {errors.length > 6 ? <div>另有 {errors.length - 6} 条错误</div> : null}
      </div>
    </section>
  );
}

function MetadataEditor({
  metadata,
  onChange
}: {
  metadata: Record<string, unknown>;
  onChange: (metadata: Record<string, unknown>) => void;
}) {
  const unlimitedRuns = metadata.unlimited_runs !== false;
  const minimum = typeof metadata.min_daily_successes === "number" ? metadata.min_daily_successes : 1;
  const nonImportant = metadata.important === false;
  const retryEvenSuccess = metadata.retry_even_success === true;

  return (
    <div className="grid gap-2">
      <label className="flex min-h-9 items-center gap-2 rounded-md border px-2.5 py-2">
        <Checkbox
          checked={nonImportant}
          onCheckedChange={(checked) =>
            onChange(
              checked === true
                ? { ...metadata, important: false, unlimited_runs: true, retry_even_success: false }
                : { ...metadata, important: true }
            )
          }
        />
        <span className="text-sm">非重要任务</span>
      </label>
      <label className="flex min-h-9 items-center gap-2 rounded-md border px-2.5 py-2">
        <Checkbox
          checked={unlimitedRuns}
          onCheckedChange={(checked) => onChange({ ...metadata, unlimited_runs: checked === true })}
        />
        <span className="text-sm">无限次运行</span>
      </label>
      <label className={cn("flex min-h-9 items-center gap-2 rounded-md border px-2.5 py-2", nonImportant && "opacity-60")}>
        <Checkbox
          checked={retryEvenSuccess}
          disabled={nonImportant}
          onCheckedChange={(checked) => onChange({ ...metadata, retry_even_success: checked === true })}
        />
        <span className="text-sm">成功也参与重试</span>
      </label>
      <label
        className={cn("grid grid-cols-[minmax(0,1fr)_110px] items-center gap-3 rounded-md border px-2.5 py-2", unlimitedRuns && "opacity-60")}
        title={nonImportant ? "非重要任务中这里按每日最低运行次数计算，且不会进入重试。" : "重要任务中这里按每日最低成功次数计算。"}
      >
        <span className="text-sm">每日最低成功次数</span>
        <input
          className="h-8 rounded-md border bg-background px-2 text-sm disabled:bg-muted"
          type="number"
          min={0}
          disabled={unlimitedRuns}
          value={minimum}
          onChange={(event) => onChange({ ...metadata, min_daily_successes: Number(event.target.value) })}
        />
      </label>
    </div>
  );
}
