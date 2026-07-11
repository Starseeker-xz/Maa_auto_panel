import { Eye } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { FocusDeleteButton } from "@/components/FocusDeleteButton";
import { CardContent, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { STATUS_LABELS } from "@/lib/logs";
import { formatDateTime } from "@/lib/time";
import type { ScheduleConfig, ScheduleResponse, ScheduledRunSummary } from "@/lib/types";
import { ProfileEditor } from "@/components/ProfileEditor";

export function ScheduleSettings({ schedule, detail, onChange }: { schedule: ScheduleConfig; detail: ScheduleResponse; onChange: (schedule: ScheduleConfig) => void }) {
  const selectedScript = detail.scripts.find((script) => script.name === schedule.restart.script);

  return (
    <div className="grid gap-3 pr-3">
      <section className="grid gap-3 rounded-md border bg-background p-3">
        <CardTitle className="text-sm">设备配置</CardTitle>
        <ProfileEditor value={schedule.profile} onChange={(profile) => onChange({ ...schedule, profile })} />
      </section>

      <section className="grid gap-3 rounded-md border bg-background p-3">
        <CardTitle className="text-sm">超时与重试</CardTitle>
        <ConfigGroup title="重试配置">
          <NumberInput label="最大重试次数" value={schedule.retry.max_retries} onChange={(value) => onChange({ ...schedule, retry: { ...schedule.retry, max_retries: value } })} />
          <NumberInput label="间隔重试次数" value={schedule.retry.buffer_every_retries} onChange={(value) => onChange({ ...schedule, retry: { ...schedule.retry, buffer_every_retries: value } })} />
          <NumberInput label="缓冲时间" value={schedule.retry.buffer_seconds} onChange={(value) => onChange({ ...schedule, retry: { ...schedule.retry, buffer_seconds: value } })} />
        </ConfigGroup>
        <ConfigGroup title="警告时限">
          <NumberInput label="无输出警告" value={schedule.timeouts.no_output_warning_seconds} onChange={(value) => updateTimeout(schedule, onChange, "no_output_warning_seconds", value)} />
          <NumberInput label="运行时长警告" value={schedule.timeouts.runtime_warning_seconds} onChange={(value) => updateTimeout(schedule, onChange, "runtime_warning_seconds", value)} />
          <NumberInput label="停止等待警告" value={schedule.timeouts.stop_warning_seconds} onChange={(value) => updateTimeout(schedule, onChange, "stop_warning_seconds", value)} />
        </ConfigGroup>
        <ConfigGroup title="强制停止时限">
          <NumberInput label="无输出强停" value={schedule.timeouts.no_output_kill_seconds} onChange={(value) => updateTimeout(schedule, onChange, "no_output_kill_seconds", value)} />
          <NumberInput label="运行时长强停" value={schedule.timeouts.runtime_kill_seconds} onChange={(value) => updateTimeout(schedule, onChange, "runtime_kill_seconds", value)} />
          <NumberInput label="停止等待强停" value={schedule.timeouts.stop_kill_seconds} onChange={(value) => updateTimeout(schedule, onChange, "stop_kill_seconds", value)} />
        </ConfigGroup>
      </section>

      <section className="grid gap-3 rounded-md border bg-background p-3">
        <CardTitle className="text-sm">脚本</CardTitle>
        <div className="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
          <Select value={schedule.restart.mode} onValueChange={(mode) => onChange({ ...schedule, restart: { ...schedule.restart, mode: mode as ScheduleConfig["restart"]["mode"] } })}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">不重启</SelectItem>
              <SelectItem value="before_run">运行前重启</SelectItem>
              <SelectItem value="before_retry">每次重试前重启</SelectItem>
            </SelectContent>
          </Select>
          <Select value={schedule.restart.script || "__none"} onValueChange={(script) => onChange({ ...schedule, restart: { ...schedule.restart, script: script === "__none" ? "" : script } })}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none">未选择脚本</SelectItem>
              {detail.scripts.map((script) => (
                <SelectItem key={script.name} value={script.name}>
                  {script.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {selectedScript?.variables.length ? (
          <div className="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
            {selectedScript.variables.map((variable) => (
              <label key={variable.name} className="grid gap-1.5">
                <span className="text-xs font-medium text-muted-foreground">{variable.label}</span>
                <Input
                  value={schedule.restart.variables[variable.name] ?? variable.default}
                  onChange={(event) =>
                    onChange({
                      ...schedule,
                      restart: {
                        ...schedule.restart,
                        variables: { ...schedule.restart.variables, [variable.name]: event.target.value }
                      }
                    })
                  }
                />
              </label>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
}

export function ScheduleStats({
  detail,
  selectedHistoryRunId,
  loadingHistoryRunId,
  onViewHistory,
  onDeleteHistory
}: {
  detail: ScheduleResponse;
  selectedHistoryRunId?: string;
  loadingHistoryRunId?: string;
  onViewHistory?: (run: ScheduledRunSummary) => void;
  onDeleteHistory?: (run: ScheduledRunSummary) => void;
}) {
  return (
    <div className="grid gap-3 pr-3">
      <section className="grid gap-2 rounded-md border bg-background p-3">
        <CardTitle className="text-sm">今日计数</CardTitle>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-2">
          {detail.task_policies.map((policy) => {
            const stats = detail.daily_stats[policy.id];
            return (
              <div key={policy.id} className="rounded-md border bg-card p-2 text-xs">
                <div className="truncate font-medium">{policy.name}</div>
                <div className="mt-1 text-muted-foreground">成功 {stats?.successes || 0} · 运行 {stats?.runs || 0}</div>
              </div>
            );
          })}
        </div>
      </section>
      <section className="grid gap-2 rounded-md border bg-background p-3">
        <CardTitle className="text-sm">近期运行</CardTitle>
        <div className="grid gap-2">
          {detail.recent_runs.map((item) => (
            <div key={item.id} data-active={item.id === selectedHistoryRunId ? "true" : undefined} className="group grid gap-1 rounded-md border bg-card p-2 text-xs transition-all hover:-translate-y-px hover:border-border/80 hover:shadow-md data-[active=true]:border-primary data-[active=true]:bg-accent/70">
              <div className="flex min-w-0 items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <span className={`status-pill ${item.status}`}>{STATUS_LABELS[item.status] || item.status}</span>
                  <span className="rounded-sm border bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">{stringMetadata(item, "trigger") === "manual" ? "手动" : "定时"}</span>
                </div>
                <div className="ml-auto flex h-6 shrink-0 items-center gap-1">
                  {onViewHistory ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-6 text-muted-foreground/70 opacity-0 transition-opacity hover:text-foreground hover:opacity-100 focus-visible:opacity-100 group-hover:opacity-70"
                      aria-label={`查看 ${stringMetadata(item, "entry_name")} 历史日志`}
                      disabled={loadingHistoryRunId === item.id}
                      onClick={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        onViewHistory(item);
                      }}
                    >
                      <Eye className="size-3.5" />
                    </Button>
                  ) : null}
                  {onDeleteHistory ? (
                    <FocusDeleteButton
                      type="button"
                      className="size-6"
                      aria-label={`删除 ${stringMetadata(item, "entry_name")} 运行记录`}
                      disabled={loadingHistoryRunId === item.id}
                      onClick={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        onDeleteHistory(item);
                      }}
                    />
                  ) : null}
                </div>
              </div>
              <div className="truncate text-muted-foreground">{formatDateTime(item.started_at)} · {stringMetadata(item, "entry_name")} · 重试 {item.retry_count}</div>
            </div>
          ))}
          {detail.recent_runs.length === 0 ? <CardContent className="p-0 text-xs text-muted-foreground">暂无运行记录</CardContent> : null}
        </div>
      </section>
    </div>
  );
}

function ConfigGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="grid gap-2">
      <div className="text-[11px] font-medium text-muted-foreground">{title}</div>
      <div className="grid grid-cols-3 gap-2 max-lg:grid-cols-2 max-sm:grid-cols-1">{children}</div>
    </div>
  );
}

function stringMetadata(run: { metadata?: Record<string, unknown> }, key: string): string {
  const value = run.metadata?.[key];
  return typeof value === "string" ? value : "";
}

function NumberInput({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="grid min-w-0 gap-1.5">
      <span className="truncate text-xs font-medium text-muted-foreground">{label}</span>
      <Input className="min-w-0" type="number" min={0} value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}

function updateTimeout(schedule: ScheduleConfig, onChange: (schedule: ScheduleConfig) => void, key: keyof ScheduleConfig["timeouts"], value: number) {
  onChange({ ...schedule, timeouts: { ...schedule.timeouts, [key]: value } });
}
