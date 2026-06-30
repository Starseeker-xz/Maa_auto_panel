import React from "react";
import { CircleHelp, Download, RefreshCw, Search } from "lucide-react";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DirtyActions } from "@/components/DirtyActions";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { getCurrentMaintenanceAction, getSettings, getUpdateInfo, saveSettings, startMaintenanceAction } from "@/lib/api";
import { loadStoredTheme, saveActiveTheme, setActiveTheme, themeColors, themeFromFrameworkSettings, themeModes, type ThemeColor, type ThemeMode } from "@/lib/theme";
import type { ConfigValidation, MaintenanceActionState, SaveSettingsPayload, SettingsResponse, UpdateInfoResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

const DELETE_VALUE = Symbol("delete-value");

type SettingsDraft = SaveSettingsPayload;
type DraftSection = keyof SettingsDraft;
type DeleteValue = typeof DELETE_VALUE;

const CHANNELS = ["Stable", "Beta", "Alpha"];
const CONNECTION_TYPES = ["ADB", "PlayCover", "MuMuPro", "Waydroid"];
const CONNECTION_CONFIGS = ["", "CompatPOSIXShell", "General", "MacPlayTools"];
const TOUCH_MODES = ["ADB", "MiniTouch", "MaaTouch", "MacPlayTools", "MaaFwAdb"];
const TIMEZONE_MODES = [
  ["auto", "自动使用后端时区"],
  ["client", "使用浏览器时区"],
  ["manual", "手动指定时区"]
];
const COMMON_TIMEZONES = ["UTC", "Asia/Shanghai", "Asia/Tokyo", "Europe/London", "Europe/Berlin", "America/Los_Angeles", "America/New_York"];

export function SettingsPage() {
  const [settings, setSettings] = React.useState<SettingsResponse | null>(null);
  const [savedDraft, setSavedDraft] = React.useState<SettingsDraft | null>(null);
  const [draft, setDraft] = React.useState<SettingsDraft | null>(null);
  const [maintenance, setMaintenance] = React.useState<MaintenanceActionState>({ status: "idle", output: [] });
  const [updateInfo, setUpdateInfo] = React.useState<UpdateInfoResponse | null>(null);
  const [updateInfoBusy, setUpdateInfoBusy] = React.useState(false);
  const [maintenanceConfirmKind, setMaintenanceConfirmKind] = React.useState<string>("");
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const browserTimezone = React.useMemo(() => browserTimezoneInfo(), []);

  React.useEffect(() => {
    let cancelled = false;

    getSettings()
      .then((data) => {
        if (cancelled) return;
        const diskDraft = draftFromSettings(data);
        const nextDraft = normalizeSettingsDraft(diskDraft);
        const storedTheme = loadStoredTheme();
        if (storedTheme) {
          nextDraft.framework = setNestedValue(setNestedValue(nextDraft.framework, ["theme", "mode"], storedTheme.mode), ["theme", "color"], storedTheme.color);
        }
        setSettings(data);
        setSavedDraft(diskDraft);
        setDraft(cloneDraft(nextDraft));
        setMaintenance(data.maintenance);
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
    if (!draft) return;
    setActiveTheme(themeFromFrameworkSettings(draft.framework));
  }, [draft]);

  React.useEffect(() => {
    if (maintenance.status !== "running") return;
    const timer = window.setInterval(async () => {
      try {
        setMaintenance(await getCurrentMaintenanceAction());
      } catch (exc) {
        setError(String(exc));
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [maintenance.status]);

  const dirty = Boolean(draft && savedDraft && JSON.stringify(draftForDirty(draft)) !== JSON.stringify(draftForDirty(savedDraft)));

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
      setMaintenance(saved.maintenance);
      setActiveTheme(themeFromFrameworkSettings(nextDraft.framework));
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
      const currentTheme = draft ? themeFromFrameworkSettings(draft.framework) : themeFromFrameworkSettings(savedDraft.framework);
      const nextDraft = cloneDraft(savedDraft);
      nextDraft.framework = setNestedValue(setNestedValue(nextDraft.framework, ["theme", "mode"], currentTheme.mode), ["theme", "color"], currentTheme.color);
      setDraft(nextDraft);
    } catch (exc) {
      setError(String(exc));
      throw exc;
    } finally {
      setBusy(false);
    }
  }

  async function handleMaintenance(kind: string) {
    setError("");
    try {
      setMaintenance(await startMaintenanceAction(kind));
      setMaintenanceConfirmKind("");
    } catch (exc) {
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

  function handleThemeChange(patch: Partial<{ mode: ThemeMode; color: ThemeColor }>) {
    setDraft((current) => {
      if (!current) return current;
      const currentTheme = themeFromFrameworkSettings(current.framework);
      const nextTheme = { ...currentTheme, ...patch };
      const nextFramework = setNestedValue(setNestedValue(current.framework, ["theme", "mode"], nextTheme.mode), ["theme", "color"], nextTheme.color);
      saveActiveTheme(nextTheme);
      return { ...current, framework: nextFramework };
    });
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
  const profileValidation = settings?.profile.validation;
  const cliValidation = settings?.maa_cli.validation;
  const effectiveTimezone = settings?.framework.effective_timezone;
  const actionRunning = maintenance.status === "running";
  const currentTimezoneMode = stringAt(framework, ["framework", "timezone", "mode"], "auto");
  const serverClientTimezoneMismatch =
    browserTimezone.offsetLabel !== effectiveTimezone?.label || (browserTimezone.name && effectiveTimezone?.name && browserTimezone.name !== effectiveTimezone.name);
  const cpuOcrEnabled = booleanAt(profile, ["static_options", "cpu_ocr"], true);

  return (
    <section className="min-h-screen overflow-auto p-4">
      <TooltipProvider delayDuration={120}>
      <div className="grid min-h-[calc(100vh-2rem)] min-w-0 gap-4 2xl:grid-cols-[minmax(320px,0.8fr)_minmax(440px,1fr)_minmax(520px,1.2fr)] xl:grid-cols-[minmax(360px,0.9fr)_minmax(520px,1.1fr)]">
        <SettingsCard title="框架与主题">
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
          <CheckboxField
            label="定时执行"
            help="定时执行还没接入，这里只是预留位置。"
            checked={booleanAt(framework, ["framework", "scheduler", "enabled"], false)}
            disabled
            onChange={(value) => updateDraft("framework", ["framework", "scheduler", "enabled"], value)}
          />
          <SectionTitle label="主题" help="主题会立即应用并保存在浏览器本地，不需要点右下角保存。" />
          <div className="grid grid-cols-3 gap-1">
            {themeModes.map((mode) => {
              const active = stringAt(framework, ["theme", "mode"], "system") === mode.value;
              return (
                <Button key={mode.value} variant={active ? "default" : "outline"} onClick={() => handleThemeChange({ mode: mode.value })}>
                  {mode.label}
                </Button>
              );
            })}
          </div>
          <div className="grid grid-cols-5 gap-2">
            {themeColors.map((color) => {
              const active = stringAt(framework, ["theme", "color"], "cyan") === color.value;
              return (
                <button
                  key={color.value}
                  type="button"
                  className={cn(
                    "grid h-12 min-w-0 place-items-center rounded-md border text-xs font-medium shadow-xs transition-all",
                    active ? "border-primary ring-2 ring-primary/30" : "border-border hover:border-primary/70"
                  )}
                  data-color-swatch={color.value}
                  onClick={() => handleThemeChange({ color: color.value })}
                >
                  <span className="size-5 rounded-full border border-black/10 shadow-xs" />
                  <span className="max-w-full truncate">{color.label}</span>
                </button>
              );
            })}
          </div>
          <PathLine label="框架设置文件" value={settings?.framework.file.path || "config/linux-maa/settings.toml"} />
        </SettingsCard>

        <SettingsCard title="设备配置">
          <div className="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
            <SelectField
              label="连接类型"
              help="常规 Android 设备和模拟器选 ADB。PlayCover、Waydroid、MuMuPro 只有对应环境才需要切换。"
              value={stringAt(profile, ["connection", "type"], "ADB")}
              options={CONNECTION_TYPES.map((value) => [value, value])}
              onChange={(value) => updateDraft("profile", ["connection", "type"], value)}
            />
            <SelectField
              label="连接配置"
              help="处理不同平台的 shell 和输入差异。Linux/redroid 通常用 CompatPOSIXShell；连接命令异常时再改。"
              value={stringAt(profile, ["connection", "config"], "") || "__unset"}
              options={CONNECTION_CONFIGS.map((value) => [value || "__unset", value || "未指定"])}
              onChange={(value) => updateDraft("profile", ["connection", "config"], value === "__unset" ? DELETE_VALUE : value)}
            />
            <TextField
              label="ADB 可执行文件"
              help="找不到设备时才需要改。填 adb 表示使用系统 PATH 里的 adb。"
              value={stringAt(profile, ["connection", "adb_path"], "adb")}
              onChange={(value) => updateDraft("profile", ["connection", "adb_path"], value)}
            />
            <TextField
              label="连接地址"
              help="设备序列号或 IP:端口，例如 127.0.0.1:5555。留空时会尝试自动选一个可用设备。"
              value={stringAt(profile, ["connection", "address"], "")}
              onChange={(value) => updateDraft("profile", ["connection", "address"], value)}
            />
            <SelectField
              label="触控模式"
              help="点击和滑动的输入方式。ADB 最通用；只有当前设备明确支持 MiniTouch、MaaTouch 或 PlayTools 时再切换。"
              value={stringAt(profile, ["instance_options", "touch_mode"], "ADB")}
              options={TOUCH_MODES.map((value) => [value, value])}
              onChange={(value) => updateDraft("profile", ["instance_options", "touch_mode"], value)}
            />
            <NumberField
              label="用于 OCR 的 GPU ID"
              help="只有关闭“使用 CPU 进行 OCR”后才会生效。单显卡通常填 0；不确定就保持空。"
              value={optionalNumberAt(profile, ["static_options", "gpu_ocr"])}
              disabled={cpuOcrEnabled}
              onChange={(value) => updateDraft("profile", ["static_options", "gpu_ocr"], value === "" ? DELETE_VALUE : value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
            <CheckboxField
              label="使用 CPU 进行 OCR"
              help="更稳定，也不依赖显卡运行环境。关闭后可以指定 GPU ID。"
              checked={cpuOcrEnabled}
              onChange={(value) => updateDraft("profile", ["static_options", "cpu_ocr"], value)}
            />
            <CheckboxField
              label="部署时暂停游戏"
              help="部署操作容易误触或失败时再打开。多数设备保持关闭即可。"
              checked={booleanAt(profile, ["instance_options", "deployment_with_pause"], false)}
              onChange={(value) => updateDraft("profile", ["instance_options", "deployment_with_pause"], value)}
            />
            <CheckboxField
              label="启用 adb-lite"
              help="替代的 ADB 连接实现。普通 ADB 连接正常时保持关闭。"
              checked={booleanAt(profile, ["instance_options", "adb_lite_enabled"], false)}
              onChange={(value) => updateDraft("profile", ["instance_options", "adb_lite_enabled"], value)}
            />
            <CheckboxField
              label="退出时关闭 ADB"
              help="如果还有模拟器、调试工具或其他任务要使用 adb，就不要打开。"
              checked={booleanAt(profile, ["instance_options", "kill_adb_on_exit"], false)}
              onChange={(value) => updateDraft("profile", ["instance_options", "kill_adb_on_exit"], value)}
            />
          </div>
          <ValidationList validation={profileValidation} />
          <PathLine label="Profile 配置文件" value={settings?.profile.file.path || "config/maa/profiles/default.toml"} />
        </SettingsCard>

        <SettingsCard title="更新与资源">
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
              <RefreshCw className={cn("size-4", actionRunning && maintenance.kind === "core-update" && "animate-spin")} />
              更新 Core/基础包
            </Button>
            <Button className="min-w-0 whitespace-normal px-3" variant="outline" onClick={() => setMaintenanceConfirmKind("resource-update")} disabled={actionRunning}>
              <RefreshCw className={cn("size-4", actionRunning && maintenance.kind === "resource-update" && "animate-spin")} />
              热更资源
            </Button>
            <Button className="min-w-0 whitespace-normal px-3" variant="outline" onClick={() => setMaintenanceConfirmKind("cli-update")} disabled={actionRunning}>
              <Download className="size-4" />
              更新 maa-cli
            </Button>
          </div>
          <MaintenanceOutput state={maintenance} />
          <ValidationList validation={cliValidation} />
          <PathLine label="maa-cli 配置文件" value={settings?.maa_cli.file.path || "config/maa/cli.toml"} />
        </SettingsCard>
      </div>
      {error ? <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 p-2 text-sm text-destructive">{error}</div> : null}
      </TooltipProvider>

      <DirtyActions
        dirty={dirty}
        busy={busy}
        saveTitle="保存设置"
        saveDescription="保存会写入框架设置、默认设备 Profile 和 maa-cli 配置。"
        resetTitle="复位设置"
        resetDescription="复位会丢弃设置页里的未保存修改，并恢复到当前磁盘内容。"
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

function SettingsCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="min-h-0 min-w-0 gap-4 p-4">
      <CardTitle className="text-sm">{title}</CardTitle>
      <div className="grid min-w-0 gap-3">{children}</div>
    </Card>
  );
}

function SectionTitle({ label, help }: { label: string; help?: string }) {
  return (
    <div className="flex min-w-0 items-center gap-1.5 pt-1 text-xs font-medium text-muted-foreground">
      <span>{label}</span>
      {help ? <HelpTooltip help={help} /> : null}
    </div>
  );
}

function FieldLabel({ label, help }: { label: string; help?: string }) {
  return (
    <div className="flex min-w-0 items-center gap-1.5 text-xs font-medium text-muted-foreground">
      <span className="min-w-0 truncate">{label}</span>
      {help ? <HelpTooltip help={help} /> : null}
    </div>
  );
}

function HelpTooltip({ help }: { help: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="grid size-4 shrink-0 place-items-center rounded-full text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="说明"
        >
          <CircleHelp className="size-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" sideOffset={6} className="max-w-xs leading-5 shadow-md sm:max-w-sm">
        {help}
      </TooltipContent>
    </Tooltip>
  );
}

function TextField({
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

function NumberField({
  label,
  value,
  help,
  disabled = false,
  onChange
}: {
  label: string;
  value: number | "";
  help?: string;
  disabled?: boolean;
  onChange: (value: number | "") => void;
}) {
  return (
    <div className="grid min-w-0 gap-1.5">
      <FieldLabel label={label} help={help} />
      <Input
        className="min-w-0"
        type="number"
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

function SelectField({ label, value, help, options, onChange }: { label: string; value: string; help?: string; options: string[][]; onChange: (value: string) => void }) {
  return (
    <div className="grid min-w-0 gap-1.5">
      <FieldLabel label={label} help={help} />
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="min-w-0">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map(([optionValue, labelText]) => (
            <SelectItem key={optionValue} value={optionValue}>
              {labelText}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function CheckboxField({
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
          {help ? <HelpTooltip help={help} /> : null}
        </span>
      </span>
    </label>
  );
}

function ReadOnlyLine({ label, value, help }: { label: string; value: string; help?: string }) {
  return (
    <div className="grid min-w-0 gap-1.5">
      <FieldLabel label={label} help={help} />
      <div className="break-anywhere min-h-9 rounded-md border bg-muted/30 px-2 py-2 text-sm">{value}</div>
    </div>
  );
}

function PathLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid min-w-0 gap-1 border-t pt-3">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <span className="break-anywhere text-xs text-muted-foreground">{value}</span>
    </div>
  );
}

function MaintenanceOutput({ state }: { state: MaintenanceActionState }) {
  const output = (state.output || []).join("");
  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between gap-2">
        <span className={`status-pill ${state.status}`}>{maintenanceStatusText(state)}</span>
        {state.return_code !== undefined && state.return_code !== null ? <span className="text-xs text-muted-foreground">exit {state.return_code}</span> : null}
      </div>
      {output ? <pre className="max-h-48 overflow-auto rounded-md border bg-background p-2 text-xs leading-5 whitespace-pre-wrap">{output}</pre> : null}
    </div>
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

function maintenanceStatusText(state: MaintenanceActionState) {
  if (state.status === "running") return state.title ? `${state.title}中` : "运行中";
  if (state.status === "succeeded") return "已完成";
  if (state.status === "failed") return "失败";
  return "空闲";
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

function offsetLabel(offsetMinutes: number) {
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const absolute = Math.abs(offsetMinutes);
  return `UTC${sign}${String(Math.floor(absolute / 60)).padStart(2, "0")}:${String(absolute % 60).padStart(2, "0")}`;
}

function draftForDirty(value: SettingsDraft): SettingsDraft {
  const framework = cloneRecord(value.framework);
  delete framework.theme;
  return {
    framework,
    profile: cloneRecord(value.profile),
    maa_cli: cloneRecord(value.maa_cli)
  };
}

function resourceLabel(value: unknown) {
  if (!isRecord(value)) return "";
  const name = typeof value.name === "string" ? value.name : "";
  const updated = typeof value.last_updated === "string" ? value.last_updated : "";
  return [name, updated].filter(Boolean).join(" · ");
}

function shortCommit(value: unknown) {
  return typeof value === "string" && value ? value.slice(0, 8) : "";
}

function stringValue(value: unknown) {
  return typeof value === "string" ? value : "";
}

function draftFromSettings(settings: SettingsResponse): SettingsDraft {
  return normalizeSettingsDraft({
    framework: cloneRecord(settings.framework.data),
    profile: cloneRecord(settings.profile.data || {}),
    maa_cli: cloneRecord(settings.maa_cli.data || {})
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
    maa_cli: cloneRecord(value.maa_cli)
  };
}

function cloneRecord(value: Record<string, unknown>): Record<string, unknown> {
  return JSON.parse(JSON.stringify(value)) as Record<string, unknown>;
}

function stringAt(data: Record<string, unknown>, path: string[], fallback: string) {
  const value = valueAt(data, path);
  return typeof value === "string" ? value : fallback;
}

function optionalNumberAt(data: Record<string, unknown>, path: string[]) {
  const value = valueAt(data, path);
  return typeof value === "number" ? value : "";
}

function booleanAt(data: Record<string, unknown>, path: string[], fallback: boolean) {
  const value = valueAt(data, path);
  return typeof value === "boolean" ? value : fallback;
}

function valueAt(data: Record<string, unknown>, path: string[]) {
  let current: unknown = data;
  for (const key of path) {
    if (!isRecord(current)) return undefined;
    current = current[key];
  }
  return current;
}

function setNestedValue(data: Record<string, unknown>, path: string[], value: unknown | DeleteValue): Record<string, unknown> {
  const next = { ...data };
  let current: Record<string, unknown> = next;
  for (let index = 0; index < path.length - 1; index += 1) {
    const key = path[index];
    const existing = current[key];
    const child = isRecord(existing) ? { ...existing } : {};
    current[key] = child;
    current = child;
  }
  const lastKey = path[path.length - 1];
  if (value === DELETE_VALUE) {
    delete current[lastKey];
  } else {
    current[lastKey] = value;
  }
  return next;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
