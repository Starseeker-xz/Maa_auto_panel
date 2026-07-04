import { Eye } from "lucide-react";

import { Button } from "@/components/ui/button";
import { CardContent, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { STATUS_LABELS } from "@/lib/logs";
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
        <div className="grid grid-cols-3 gap-2 max-lg:grid-cols-2 max-sm:grid-cols-1">
          <NumberInput label="子任务警报" value={schedule.timeouts.child_warning_seconds} onChange={(value) => updateTimeout(schedule, onChange, "child_warning_seconds", value)} />
          <NumberInput label="子任务危险警报" value={schedule.timeouts.child_danger_seconds} onChange={(value) => updateTimeout(schedule, onChange, "child_danger_seconds", value)} />
          <NumberInput label="子任务硬停止" value={schedule.timeouts.child_kill_seconds} onChange={(value) => updateTimeout(schedule, onChange, "child_kill_seconds", value)} />
          <NumberInput label="整组警报" value={schedule.timeouts.run_warning_seconds} onChange={(value) => updateTimeout(schedule, onChange, "run_warning_seconds", value)} />
          <NumberInput label="整组危险警报" value={schedule.timeouts.run_danger_seconds} onChange={(value) => updateTimeout(schedule, onChange, "run_danger_seconds", value)} />
          <NumberInput label="整组硬停止" value={schedule.timeouts.run_kill_seconds} onChange={(value) => updateTimeout(schedule, onChange, "run_kill_seconds", value)} />
          <NumberInput label="单组重试上限" value={schedule.retry.max_attempts_per_group} onChange={(value) => onChange({ ...schedule, retry: { ...schedule.retry, max_attempts_per_group: value } })} />
          <NumberInput label="重试组缓冲" value={schedule.retry.group_buffer_seconds} onChange={(value) => onChange({ ...schedule, retry: { ...schedule.retry, group_buffer_seconds: value } })} />
          <NumberInput label="重试组上限" value={schedule.retry.max_groups} onChange={(value) => onChange({ ...schedule, retry: { ...schedule.retry, max_groups: value } })} />
        </div>
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
              <SelectItem value="before_retry_group">重试组前重启</SelectItem>
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
  onViewHistory
}: {
  detail: ScheduleResponse;
  selectedHistoryRunId?: string;
  loadingHistoryRunId?: string;
  onViewHistory?: (run: ScheduledRunSummary) => void;
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
              <div className="grid grid-cols-[auto_minmax(0,1fr)_28px] items-center gap-2">
                <span className={`status-pill ${item.status}`}>{STATUS_LABELS[item.status] || item.status}</span>
                <span className="min-w-0 truncate text-right text-muted-foreground">{item.created_at}</span>
                {onViewHistory ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-6 text-muted-foreground/70 opacity-0 transition-opacity hover:text-foreground hover:opacity-100 focus-visible:opacity-100 group-hover:opacity-70"
                    aria-label={`查看 ${item.entry_name} 历史日志`}
                    disabled={loadingHistoryRunId === item.id}
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      onViewHistory(item);
                    }}
                  >
                    <Eye className="size-3.5" />
                  </Button>
                ) : (
                  <span aria-hidden="true" />
                )}
              </div>
              <div className="text-muted-foreground">{item.entry_name} · 尝试 {item.attempt_count} · 重试组 {item.retry_group_count}</div>
            </div>
          ))}
          {detail.recent_runs.length === 0 ? <CardContent className="p-0 text-xs text-muted-foreground">暂无运行记录</CardContent> : null}
        </div>
      </section>
    </div>
  );
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
