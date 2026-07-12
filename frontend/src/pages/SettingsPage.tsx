import React from "react";
import { Download, RefreshCw, Search } from "lucide-react";
import { useLocation } from "react-router-dom";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DirtyActions } from "@/components/DirtyActions";
import { CheckboxField, NumberField, PathLine, ReadOnlyLine, SectionTitle, SelectField, TextField } from "@/components/FormFields";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { currentMaintenanceEventsUrl, getCurrentMaintenanceAction, getSettings, getUpdateInfo, saveSettings, startMaintenanceAction } from "@/lib/api";
import { booleanAt, isRecord, optionalNumberAt, setNestedValue, stringAt, valueAt, type DeleteValue } from "@/lib/objectPath";
import { applyRunStateEvent, normalizeRunState, runEventsUrl } from "@/lib/runStream";
import { formatDateTime } from "@/lib/time";
import type { ConfigValidation, MaintenanceActionState, SaveSettingsPayload, SettingsResponse, UpdateInfoResponse } from "@/lib/types";
import { cn } from "@/lib/utils";
import { LogPane } from "@/pages/main/LogPane";
import { DeviceSettingsPanel, NotificationSettingsPanel, ScrcpySettingsPanel, SettingsPanel } from "@/pages/settings/panels";
import { SettingsNavigation } from "@/pages/settings/SettingsNavigation";

type SettingsDraft = SaveSettingsPayload;
type DraftSection = "framework" | "profile" | "maa_cli";

const CHANNELS = ["Stable", "Beta", "Alpha"];
const TIMEZONE_MODES = [
  ["auto", "自动使用后端时区"],
  ["client", "使用浏览器时区"],
  ["manual", "手动指定时区"]
];
const COMMON_TIMEZONES = ["UTC", "Asia/Shanghai", "Asia/Tokyo", "Europe/London", "Europe/Berlin", "America/Los_Angeles", "America/New_York"];
const MAINTENANCE_EVENTS_ERROR = "维护日志事件流连接中断，正在重连...";

export function SettingsPage() {
  const location = useLocation();
  const section = location.pathname === "/settings/framework" ? "framework" : "basic";
  const [settings, setSettings] = React.useState<SettingsResponse | null>(null);
  const [savedDraft, setSavedDraft] = React.useState<SettingsDraft | null>(null);
  const [draft, setDraft] = React.useState<SettingsDraft | null>(null);
  const [maintenance, setMaintenance] = React.useState<MaintenanceActionState>({ status: "idle", run: { status: "idle" }, retries: [] });
  const [updateInfo, setUpdateInfo] = React.useState<UpdateInfoResponse | null>(null);
  const [updateInfoBusy, setUpdateInfoBusy] = React.useState(false);
  const [maintenanceConfirmKind, setMaintenanceConfirmKind] = React.useState<string>("");
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const browserTimezone = React.useMemo(() => browserTimezoneInfo(), []);
  const maintenanceWasRunning = React.useRef(false);

  React.useEffect(() => {
    let cancelled = false;

    getSettings()
      .then((data) => {
        if (cancelled) return;
        const diskDraft = draftFromSettings(data);
        const nextDraft = normalizeSettingsDraft(diskDraft);
        setSettings(data);
        setSavedDraft(diskDraft);
        setDraft(cloneDraft(nextDraft));
        setMaintenance(normalizeRunState(data.maintenance));
        setError("");
        void handleRefreshUpdateInfo();
      })
      .catch((exc) => {
        if (!cancelled) setError(String(exc));
      });

    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    let events: EventSource | null = null;

    async function connectMaintenanceStream() {
      let snapshot: MaintenanceActionState | null = null;
      try {
        snapshot = await getCurrentMaintenanceAction();
        if (cancelled) return;
        setMaintenance(snapshot);
        setError((current) => (current === MAINTENANCE_EVENTS_ERROR ? "" : current));
      } catch (exc) {
        if (!cancelled) setError((current) => current || String(exc));
      }

      if (cancelled) return;
      events = new EventSource(runEventsUrl(currentMaintenanceEventsUrl, snapshot));
      events.onmessage = (event) => {
        setMaintenance((current) => applyRunStateEvent(current, JSON.parse(event.data)));
        setError((current) => (current === MAINTENANCE_EVENTS_ERROR ? "" : current));
      };
      events.onerror = () => {
        setError((current) => current || MAINTENANCE_EVENTS_ERROR);
      };
    }

    void connectMaintenanceStream();
    return () => {
      cancelled = true;
      events?.close();
    };
  }, []);

  React.useEffect(() => {
    const running = maintenance.status === "running" || maintenance.status === "stopping";
    if (running) {
      maintenanceWasRunning.current = true;
      return;
    }
    if (!maintenanceWasRunning.current) return;
    maintenanceWasRunning.current = false;
    void handleRefreshUpdateInfo();
  }, [maintenance.status]);

  const dirty = Boolean(draft && savedDraft && JSON.stringify(draftSectionForDirty(draft, section)) !== JSON.stringify(draftSectionForDirty(savedDraft, section)));

  function updateDraft(section: DraftSection, path: string[], value: unknown | DeleteValue) {
    setDraft((current) => {
      if (!current) return current;
      return {
        ...current,
        [section]: setNestedValue(current[section], path, value)
      };
    });
  }

  async function handleSave() {
    if (!draft) return;
    setBusy(true);
    setError("");
    try {
      const saved = await saveSettings(normalizeSettingsDraft(draft));
      const diskDraft = draftFromSettings(saved);
      const nextDraft = normalizeSettingsDraft(diskDraft);
      setSettings(saved);
      setSavedDraft(diskDraft);
      setDraft(cloneDraft(nextDraft));
      setMaintenance(normalizeRunState(saved.maintenance));
    } catch (exc) {
      setError(String(exc));
      throw exc;
    } finally {
      setBusy(false);
    }
  }

  async function handleReset() {
    if (!savedDraft) return;
    setBusy(true);
    setError("");
    try {
      setDraft((current) => {
        if (!current) return current;
        return section === "basic"
          ? {
              ...current,
              framework: setNestedValue(current.framework, ["framework", "scrcpy"], cloneValue(valueAt(savedDraft.framework, ["framework", "scrcpy"]))),
              profile: cloneRecord(savedDraft.profile),
              maa_cli: cloneRecord(savedDraft.maa_cli)
            }
          : {
              ...current,
              framework: setNestedValue(
                cloneRecord(savedDraft.framework),
                ["framework", "scrcpy"],
                cloneValue(valueAt(current.framework, ["framework", "scrcpy"]))
              ),
              notifications: cloneNotifications(savedDraft.notifications)
            };
      });
    } catch (exc) {
      setError(String(exc));
      throw exc;
    } finally {
      setBusy(false);
    }
  }

  async function handleMaintenance(kind: string) {
    setError("");
    maintenanceWasRunning.current = true;
    try {
      setMaintenance(await startMaintenanceAction(kind));
      setMaintenanceConfirmKind("");
    } catch (exc) {
      maintenanceWasRunning.current = false;
      setError(String(exc));
    }
  }

  async function handleRefreshUpdateInfo() {
    setUpdateInfoBusy(true);
    setError("");
    try {
      setUpdateInfo(await getUpdateInfo());
    } catch (exc) {
      setError(String(exc));
    } finally {
      setUpdateInfoBusy(false);
    }
  }

  if (!draft) {
    return (
      <section className="min-h-screen p-4">
        <Card className="min-h-[calc(100vh-2rem)] gap-3 p-4">
          <CardTitle>设置</CardTitle>
          <div className="text-sm text-muted-foreground">{error || "正在读取设置..."}</div>
        </Card>
      </section>
    );
  }

  const framework = draft.framework;
  const profile = draft.profile;
  const maaCli = draft.maa_cli;
  const cliValidation = settings?.maa_cli.validation;
  const effectiveTimezone = settings?.framework.effective_timezone;
  const actionRunning = maintenance.status === "running" || maintenance.status === "stopping";
  const maintenanceKind = stringMetadata(maintenance, "maintenance_kind");
  const hasMaintenanceLog = actionRunning || Boolean(maintenance.retries?.some((retry) => retry.log_entries?.length)) || error === MAINTENANCE_EVENTS_ERROR;
  const currentTimezoneMode = stringAt(framework, ["framework", "timezone", "mode"], "auto");
  const serverClientTimezoneMismatch =
    browserTimezone.offsetLabel !== effectiveTimezone?.label || (browserTimezone.name && effectiveTimezone?.name && browserTimezone.name !== effectiveTimezone.name);

  return (
    <section className="min-h-screen overflow-auto p-4">
      <div className="grid min-h-[calc(100vh-2rem)] min-w-0 content-start gap-4">
        <SettingsNavigation />
        <div className="grid min-w-0 gap-4 xl:grid-cols-2">
        {section === "framework" ? (
          <>
        <SettingsPanel title="框架">
          <SelectField
            label="时区来源"
            help="影响之后定时任务按哪一天、哪一个小时计算。通常选浏览器时区；部署到 Docker 后，也可以让容器时区和你本地一致。"
            value={currentTimezoneMode}
            options={TIMEZONE_MODES}
            onChange={(value) => {
              updateDraft("framework", ["framework", "timezone", "mode"], value);
              if (value === "client") updateDraft("framework", ["framework", "timezone", "client_timezone"], browserTimezone.name);
            }}
          />
          {serverClientTimezoneMismatch ? (
            <div className="grid gap-2 rounded-md border border-amber-300/70 bg-amber-50 p-2 text-xs leading-5 text-amber-900">
              <div>
                后端当前为 {effectiveTimezone?.label || "未知"} · {effectiveTimezone?.name || "未知"}，浏览器当前为 {browserTimezone.offsetLabel} · {browserTimezone.name}。
                后续定时执行建议使用用户本地时区或让容器时区与客户端一致。
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  updateDraft("framework", ["framework", "timezone", "mode"], "client");
                  updateDraft("framework", ["framework", "timezone", "client_timezone"], browserTimezone.name);
                }}
              >
                使用浏览器时区
              </Button>
            </div>
          ) : null}
          <TextField
            label="浏览器时区"
            help="由当前浏览器提供。像 Europe/London 这类地区名会自动包含夏令时规则。"
            value={browserTimezone.name}
            disabled
            onChange={() => undefined}
          />
          <TextField
            label="指定时区"
            help="推荐填 Europe/London 这类地区名。UTC+08:00 这种固定偏移不会随夏令时变化。"
            value={stringAt(framework, ["framework", "timezone", "manual_timezone"], "UTC")}
            disabled={currentTimezoneMode !== "manual"}
            list="timezone-options"
            onChange={(value) => updateDraft("framework", ["framework", "timezone", "manual_timezone"], value)}
          />
          <datalist id="timezone-options">
            {timezoneOptions(browserTimezone.name).map((timezone) => (
              <option key={timezone} value={timezone} />
            ))}
          </datalist>
          <ReadOnlyLine
            label="后端解析结果"
            help="保存时会重新解析。这里如果和浏览器时区冲突，后续定时任务可能和你的直觉不一致。"
            value={effectiveTimezone ? `${effectiveTimezone.label} · ${effectiveTimezone.name}` : "未保存"}
          />
          <SectionTitle label="运行资源协调" help="所有手动、定时、工具和维护运行共享。等待超时后运行会记录失败且不会启动实际命令。" />
          <NumberField
            label="资源等待上限（秒）"
            value={optionalNumberAt(framework, ["framework", "run_resources", "wait_timeout_seconds"]) ?? 300}
            min={1}
            onChange={(value) => updateDraft("framework", ["framework", "run_resources", "wait_timeout_seconds"], value === "" ? 300 : value)}
          />
          <SectionTitle label="手动运行时限" help="用于手动任务、小工具和维护动作。0 表示不启用对应自动强停或警告。" />
          <div className="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
            <NumberField
              label="无输出警告"
              value={runTimeoutValue(framework, "no_output_warning_seconds", 1800)}
              min={0}
              onChange={(value) => updateDraft("framework", ["framework", "run_timeouts", "no_output_warning_seconds"], value === "" ? 0 : value)}
            />
            <NumberField
              label="无输出强停"
              value={runTimeoutValue(framework, "no_output_kill_seconds", 0)}
              min={0}
              onChange={(value) => updateDraft("framework", ["framework", "run_timeouts", "no_output_kill_seconds"], value === "" ? 0 : value)}
            />
            <NumberField
              label="运行时长警告"
              value={runTimeoutValue(framework, "runtime_warning_seconds", 0)}
              min={0}
              onChange={(value) => updateDraft("framework", ["framework", "run_timeouts", "runtime_warning_seconds"], value === "" ? 0 : value)}
            />
            <NumberField
              label="运行时长强停"
              value={runTimeoutValue(framework, "runtime_kill_seconds", 0)}
              min={0}
              onChange={(value) => updateDraft("framework", ["framework", "run_timeouts", "runtime_kill_seconds"], value === "" ? 0 : value)}
            />
            <NumberField
              label="停止等待警告"
              value={runTimeoutValue(framework, "stop_warning_seconds", 60)}
              min={0}
              onChange={(value) => updateDraft("framework", ["framework", "run_timeouts", "stop_warning_seconds"], value === "" ? 0 : value)}
            />
            <NumberField
              label="停止等待强停"
              value={runTimeoutValue(framework, "stop_kill_seconds", 0)}
              min={0}
              onChange={(value) => updateDraft("framework", ["framework", "run_timeouts", "stop_kill_seconds"], value === "" ? 0 : value)}
            />
          </div>
          <PathLine label="框架设置文件" value={settings?.framework.file.path || "config/framework/settings.toml"} />
        </SettingsPanel>

        <NotificationSettingsPanel value={draft.notifications} onChange={(notifications) => setDraft((current) => (current ? { ...current, notifications } : current))} />
          </>
        ) : (
          <>

        <DeviceSettingsPanel
          profile={profile}
          validation={settings?.profile.validation}
          path={settings?.profile.file.path || "config/maa/profiles/default.toml"}
          onChange={(path, value) => updateDraft("profile", path, value)}
        />

        <ScrcpySettingsPanel settings={framework} onChange={(path, value) => updateDraft("framework", path, value)} />

        <SettingsPanel title="更新与资源">
          <div className="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
            <SelectField
              label="MaaCore 渠道"
              help="决定更新 Core 和基础资源包时检查哪个版本线。日常使用 Stable。"
              value={stringAt(maaCli, ["core", "channel"], "Stable")}
              options={CHANNELS.map((value) => [value, value])}
              onChange={(value) => updateDraft("maa_cli", ["core", "channel"], value)}
            />
            <SelectField
              label="maa-cli 渠道"
              help="决定更新命令行程序本身时检查哪个版本线。日常使用 Stable。"
              value={stringAt(maaCli, ["cli", "channel"], "Stable")}
              options={CHANNELS.map((value) => [value, value])}
              onChange={(value) => updateDraft("maa_cli", ["cli", "channel"], value)}
            />
            <SelectField
              label="热更资源后端"
              help="热更资源通过 Git 仓库拉取。系统里有 git 时用 git；没有 git 或想减少外部依赖时用 libgit2。"
              value={stringAt(maaCli, ["resource", "backend"], "git")}
              options={[
                ["git", "git"],
                ["libgit2", "libgit2"]
              ]}
              onChange={(value) => updateDraft("maa_cli", ["resource", "backend"], value)}
            />
            <TextField
              label="热更资源分支"
              help="普通用户保持 main。只有测试自定义资源仓库时才需要改。"
              value={stringAt(maaCli, ["resource", "remote", "branch"], "main")}
              onChange={(value) => updateDraft("maa_cli", ["resource", "remote", "branch"], value)}
            />
          </div>
          <TextField
            label="热更资源仓库"
            help="普通用户保持默认。已经安装过热更仓库后，改这里通常还要改本地 git remote 或删除旧仓库。"
            value={stringAt(maaCli, ["resource", "remote", "url"], "")}
            onChange={(value) => updateDraft("maa_cli", ["resource", "remote", "url"], value)}
          />
          <div className="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
            <CheckboxField
              label="运行任务前自动热更资源"
              help="每次开始任务前先拉取活动关卡、掉落识别图标、公招标签等更新；不会更新 Core 程序。"
              checked={booleanAt(maaCli, ["resource", "auto_update"], false)}
              onChange={(value) => updateDraft("maa_cli", ["resource", "auto_update"], value)}
            />
            <CheckboxField
              label="热更失败仅警告"
              help="打开后，资源拉取失败也继续运行任务；关闭后，热更失败会中断任务。"
              checked={booleanAt(maaCli, ["resource", "warn_on_update_failure"], true)}
              onChange={(value) => updateDraft("maa_cli", ["resource", "warn_on_update_failure"], value)}
            />
          </div>
          <UpdateInfoPanel info={updateInfo} busy={updateInfoBusy} onRefresh={() => void handleRefreshUpdateInfo()} />
          <div className="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-2">
            <Button className="min-w-0 whitespace-normal px-3" variant="outline" onClick={() => setMaintenanceConfirmKind("core-update")} disabled={actionRunning}>
              <RefreshCw className={cn("size-4", actionRunning && maintenanceKind === "core-update" && "animate-spin")} />
              更新 Core/基础包
            </Button>
            <Button className="min-w-0 whitespace-normal px-3" variant="outline" onClick={() => setMaintenanceConfirmKind("resource-update")} disabled={actionRunning}>
              <RefreshCw className={cn("size-4", actionRunning && maintenanceKind === "resource-update" && "animate-spin")} />
              热更资源
            </Button>
            <Button className="min-w-0 whitespace-normal px-3" variant="outline" onClick={() => setMaintenanceConfirmKind("cli-update")} disabled={actionRunning}>
              <Download className="size-4" />
              更新 maa-cli
            </Button>
          </div>
          <ValidationList validation={cliValidation} />
          <PathLine label="maa-cli 配置文件" value={settings?.maa_cli.file.path || "config/maa/cli.toml"} />
          {hasMaintenanceLog ? (
            <LogPane
              run={maintenance}
              error={error === MAINTENANCE_EVENTS_ERROR ? error : ""}
              emptyText="等待维护日志..."
              hideHeader
              className="max-h-64 min-h-32 border-dashed"
            />
          ) : null}
        </SettingsPanel>
          </>
        )}
        </div>
      </div>
      {error ? <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 p-2 text-sm text-destructive">{error}</div> : null}

      <DirtyActions
          dirty={dirty}
          busy={busy}
          saveTitle={section === "basic" ? "保存基础设置" : "保存框架设置"}
          saveDescription={section === "basic" ? "保存默认设备 Profile 与 maa-cli 更新配置。" : "保存框架运行设置与通知策略。"}
          resetTitle="复位当前页"
          resetDescription="复位只会丢弃当前设置页里的未保存修改。"
          onSave={handleSave}
          onReset={handleReset}
        />
      <ConfirmDialog
        open={Boolean(maintenanceConfirmKind)}
        title={maintenanceDialogContent(maintenanceConfirmKind, updateInfo).title}
        description={maintenanceDialogContent(maintenanceConfirmKind, updateInfo).description}
        confirmLabel="开始更新"
        busy={actionRunning}
        onCancel={() => setMaintenanceConfirmKind("")}
        onConfirm={() => void handleMaintenance(maintenanceConfirmKind)}
      />
    </section>
  );
}

function UpdateInfoPanel({ info, busy, onRefresh }: { info: UpdateInfoResponse | null; busy: boolean; onRefresh: () => void }) {
  return (
    <div className="grid min-w-0 gap-2 rounded-md border bg-muted/20 p-2">
      <div className="flex items-center justify-between gap-2">
        <SectionTitle
          label="更新信息"
          help="Core/基础包由“更新 Core/基础包”处理；热更资源由 MaaResource 仓库提供，主要包含活动关卡、掉落识别图标和公招标签等可热更数据。"
        />
        <Button className="shrink-0" variant="outline" size="sm" onClick={onRefresh} disabled={busy}>
          <Search className={cn("size-3.5", busy && "animate-pulse")} />
          检查
        </Button>
      </div>
      {info ? (
        <div className="grid gap-1 text-xs leading-5">
          <InfoRow label="MaaCore/基础包" current={stringValue(info.current.maa_core)} latest={info.latest.maa_core?.version} update={info.latest.maa_core?.update_available} />
          <InfoRow label="maa-cli" current={stringValue(info.current.maa_cli)} latest={info.latest.maa_cli?.version} update={info.latest.maa_cli?.update_available} />
          <InfoRow
            label="热更仓库"
            current={shortCommit(info.latest.hot_resource?.local_commit)}
            latest={shortCommit(info.latest.hot_resource?.remote_commit)}
            update={info.latest.hot_resource?.update_available}
          />
          <InfoRow label="基础资源文件" current={resourceLabel(info.current.base_resource)} />
          <InfoRow label="热更资源文件" current={resourceLabel(info.current.hot_resource)} />
          {info.errors.length ? <div className="text-destructive">{info.errors[0]}</div> : null}
        </div>
      ) : (
        <div className="text-xs leading-5 text-muted-foreground">点击检查后显示当前版本、远端版本和是否需要更新。</div>
      )}
    </div>
  );
}

function InfoRow({ label, current, latest, update }: { label: string; current?: string; latest?: string; update?: boolean }) {
  return (
    <div className="grid min-w-0 grid-cols-[7.25rem_minmax(0,1fr)] gap-2 max-sm:grid-cols-1 max-sm:gap-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="break-anywhere min-w-0">
        <span>{current || "未知"}</span>
        {latest ? (
          <>
            <span className="mx-1 text-muted-foreground">-&gt;</span>
            <span className={cn("rounded-sm bg-primary/10 px-1.5 py-0.5 font-semibold", update === true ? "text-amber-700" : "text-foreground")}>{latest}</span>
          </>
        ) : null}
        {update === true ? (
          <span className="ml-1 rounded-sm bg-amber-100 px-1.5 py-0.5 font-medium text-amber-800">可更新</span>
        ) : update === false ? (
          <span className="ml-1 rounded-sm bg-muted px-1.5 py-0.5 text-muted-foreground">已是最新</span>
        ) : null}
      </span>
    </div>
  );
}

function ValidationList({ validation }: { validation?: ConfigValidation }) {
  if (!validation || validation.valid) return null;
  return (
    <div className="grid gap-1 rounded-md border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive">
      {validation.errors.slice(0, 4).map((error) => (
        <div key={`${error.source}-${error.path}-${error.message}`}>
          {error.path}: {error.message}
        </div>
      ))}
    </div>
  );
}

function maintenanceDialogContent(kind: string, info: UpdateInfoResponse | null) {
  if (kind === "core-update") {
    return {
      title: "更新 Core 与基础资源包",
      description: `将运行 maa update。当前 Core ${stringValue(info?.current.maa_core) || "未知"}，远端 ${info?.latest.maa_core?.version || "未知"}。基础资源包随 Core 版本安装；如果 Core 已是最新，命令可能会跳过安装。`
    };
  }
  if (kind === "resource-update") {
    return {
      title: "热更新 MaaResource 资源",
      description: `将运行 maa hot-update，从 MaaResource 仓库拉取活动关卡、掉落图标、公招标签等热更资源。当前 ${shortCommit(info?.latest.hot_resource?.local_commit) || "未知"}，远端 ${shortCommit(info?.latest.hot_resource?.remote_commit) || "未知"}。`
    };
  }
  if (kind === "cli-update") {
    return {
      title: "更新 maa-cli",
      description: `将运行 maa self update。当前 maa-cli ${stringValue(info?.current.maa_cli) || "未知"}，远端 ${info?.latest.maa_cli?.version || "未知"}。`
    };
  }
  return { title: "执行更新", description: "将启动维护动作。" };
}

function browserTimezoneInfo() {
  const date = new Date();
  const name = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  const offsetMinutes = -date.getTimezoneOffset();
  return {
    name,
    offsetMinutes,
    offsetLabel: offsetLabel(offsetMinutes)
  };
}

function timezoneOptions(browserTimezone: string) {
  const intlWithSupportedValues = Intl as typeof Intl & { supportedValuesOf?: (key: string) => string[] };
  const supported = typeof intlWithSupportedValues.supportedValuesOf === "function" ? intlWithSupportedValues.supportedValuesOf("timeZone") : [];
  return Array.from(new Set([browserTimezone, ...COMMON_TIMEZONES, ...supported])).filter(Boolean).sort();
}

function runTimeoutValue(framework: Record<string, unknown>, key: string, fallback: number) {
  return optionalNumberAt(framework, ["framework", "run_timeouts", key]) ?? fallback;
}

function offsetLabel(offsetMinutes: number) {
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const absolute = Math.abs(offsetMinutes);
  return `UTC${sign}${String(Math.floor(absolute / 60)).padStart(2, "0")}:${String(absolute % 60).padStart(2, "0")}`;
}

function draftSectionForDirty(value: SettingsDraft, section: "basic" | "framework") {
  return section === "basic"
    ? { profile: cloneRecord(value.profile), maa_cli: cloneRecord(value.maa_cli), scrcpy: valueAt(value.framework, ["framework", "scrcpy"]) }
    : { framework: frameworkWithoutScrcpy(value.framework), notifications: cloneNotifications(value.notifications) };
}

function frameworkWithoutScrcpy(value: Record<string, unknown>) {
  const framework = cloneRecord(value);
  if (isRecord(framework.framework)) delete framework.framework.scrcpy;
  return framework;
}

function resourceLabel(value: unknown) {
  if (!isRecord(value)) return "";
  const name = typeof value.name === "string" ? value.name : "";
  const updated = typeof value.last_updated === "string" ? formatDateTime(value.last_updated) : "";
  return [name, updated].filter(Boolean).join(" · ");
}

function shortCommit(value: unknown) {
  return typeof value === "string" && value ? value.slice(0, 8) : "";
}

function stringValue(value: unknown) {
  return typeof value === "string" ? value : "";
}

function stringMetadata(run: MaintenanceActionState, key: string): string {
  const value = run.metadata?.[key];
  return typeof value === "string" ? value : "";
}

function draftFromSettings(settings: SettingsResponse): SettingsDraft {
  return normalizeSettingsDraft({
    framework: cloneRecord(settings.framework.data),
    profile: cloneRecord(settings.profile.data || {}),
    maa_cli: cloneRecord(settings.maa_cli.data || {}),
    notifications: cloneNotifications(settings.notifications)
  });
}

function normalizeSettingsDraft(value: SettingsDraft): SettingsDraft {
  const next = cloneDraft(value);
  next.maa_cli = enableHiddenComponent(next.maa_cli, ["core", "components", "library"]);
  next.maa_cli = enableHiddenComponent(next.maa_cli, ["core", "components", "resource"]);
  next.maa_cli = enableHiddenComponent(next.maa_cli, ["cli", "components", "binary"]);
  return next;
}

function enableHiddenComponent(data: Record<string, unknown>, path: string[]) {
  return valueAt(data, path) === false ? setNestedValue(data, path, true) : data;
}

function cloneDraft(value: SettingsDraft): SettingsDraft {
  return {
    framework: cloneRecord(value.framework),
    profile: cloneRecord(value.profile),
    maa_cli: cloneRecord(value.maa_cli),
    notifications: cloneNotifications(value.notifications)
  };
}

function cloneRecord(value: Record<string, unknown>): Record<string, unknown> {
  return JSON.parse(JSON.stringify(value)) as Record<string, unknown>;
}

function cloneValue<T>(value: T): T {
  return value === undefined ? value : JSON.parse(JSON.stringify(value)) as T;
}

function cloneNotifications(value: SettingsDraft["notifications"]): SettingsDraft["notifications"] {
  return JSON.parse(JSON.stringify(value)) as SettingsDraft["notifications"];
}
