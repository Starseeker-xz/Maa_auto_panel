import React from "react";

import { CheckboxField, NumberField, PathLine, SelectField, TextField } from "@/components/FormFields";
import { Card, CardTitle } from "@/components/ui/card";
import { CONNECTION_CONFIGS, CONNECTION_TYPES, TOUCH_MODES } from "@/lib/constants";
import { DELETE_VALUE, booleanAt, optionalNumberAt, stringAt, type DeleteValue } from "@/lib/objectPath";
import type { ConfigValidation, NotificationSettingsResponse } from "@/lib/types";

export function SettingsPanel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="min-h-0 min-w-0 gap-4 p-4">
      <CardTitle className="text-sm">{title}</CardTitle>
      <div className="grid min-w-0 gap-3">{children}</div>
    </Card>
  );
}

export function NotificationSettingsPanel({
  value,
  onChange
}: {
  value: NotificationSettingsResponse;
  onChange: (value: NotificationSettingsResponse) => void;
}) {
  function updateTag(id: string, field: "toast" | "external", checked: boolean) {
    onChange({
      ...value,
      tags: value.tags.map((tag) => (tag.id === id ? { ...tag, [field]: checked } : tag))
    });
  }

  return (
    <SettingsPanel title="通知">
      <div className="grid gap-3">
        {value.tags.map((tag) => (
          <div key={tag.id} className="grid gap-2 rounded-md border p-3">
            <div>
              <div className="text-sm font-medium">{tag.title}</div>
              <div className="mt-1 text-xs leading-5 text-muted-foreground">{tag.description}</div>
            </div>
            <div className="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
              <CheckboxField label="在线时右上角弹出" checked={tag.toast} onChange={(checked) => updateTag(tag.id, "toast", checked)} />
              <CheckboxField
                label="外部发送"
                help={value.external_channels_available ? "通过已配置的外部渠道发送。" : "策略可预先配置；当前仅保留发送接口，尚无外部渠道实现。"}
                checked={tag.external}
                onChange={(checked) => updateTag(tag.id, "external", checked)}
              />
            </div>
          </div>
        ))}
      </div>
      <PathLine label="通知设置文件" value={value.file.path || "data/config/framework/notifications.toml"} />
    </SettingsPanel>
  );
}

export function DeviceSettingsPanel({
  profile,
  validation,
  path,
  onChange
}: {
  profile: Record<string, unknown>;
  validation?: ConfigValidation;
  path: string;
  onChange: (path: string[], value: unknown | DeleteValue) => void;
}) {
  const cpuOcrEnabled = booleanAt(profile, ["static_options", "cpu_ocr"], true);
  return (
    <SettingsPanel title="设备配置">
      <div className="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
        <SelectField label="连接类型" help="常规 Android 设备和模拟器选 ADB。" value={stringAt(profile, ["connection", "type"], "ADB")} options={CONNECTION_TYPES.map((value) => [value, value])} onChange={(value) => onChange(["connection", "type"], value)} />
        <SelectField
          label="连接配置"
          help="Linux/redroid 通常使用 CompatPOSIXShell。"
          value={stringAt(profile, ["connection", "config"], "") || "__unset"}
          options={CONNECTION_CONFIGS.map((value) => [value || "__unset", value || "未指定"])}
          onChange={(value) => onChange(["connection", "config"], value === "__unset" ? DELETE_VALUE : value)}
        />
        <TextField label="ADB 可执行文件" value={stringAt(profile, ["connection", "adb_path"], "adb")} onChange={(value) => onChange(["connection", "adb_path"], value)} />
        <TextField label="连接地址" help="设备序列号或 IP:端口。" value={stringAt(profile, ["connection", "address"], "")} onChange={(value) => onChange(["connection", "address"], value)} />
        <SelectField label="触控模式" value={stringAt(profile, ["instance_options", "touch_mode"], "ADB")} options={TOUCH_MODES.map((value) => [value, value])} onChange={(value) => onChange(["instance_options", "touch_mode"], value)} />
        <NumberField
          label="用于 OCR 的 GPU ID"
          value={optionalNumberAt(profile, ["static_options", "gpu_ocr"])}
          disabled={cpuOcrEnabled}
          onChange={(value) => onChange(["static_options", "gpu_ocr"], value === "" ? DELETE_VALUE : value)}
        />
      </div>
      <div className="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
        <CheckboxField label="使用 CPU 进行 OCR" checked={cpuOcrEnabled} onChange={(value) => onChange(["static_options", "cpu_ocr"], value)} />
        <CheckboxField label="部署时暂停游戏" checked={booleanAt(profile, ["instance_options", "deployment_with_pause"], false)} onChange={(value) => onChange(["instance_options", "deployment_with_pause"], value)} />
        <CheckboxField label="启用 adb-lite" checked={booleanAt(profile, ["instance_options", "adb_lite_enabled"], false)} onChange={(value) => onChange(["instance_options", "adb_lite_enabled"], value)} />
        <CheckboxField label="退出时关闭 ADB" checked={booleanAt(profile, ["instance_options", "kill_adb_on_exit"], false)} onChange={(value) => onChange(["instance_options", "kill_adb_on_exit"], value)} />
      </div>
      <ValidationList validation={validation} />
      <PathLine label="Profile 配置文件" value={path} />
    </SettingsPanel>
  );
}

export function ScrcpySettingsPanel({
  settings,
  onChange
}: {
  settings: Record<string, unknown>;
  onChange: (path: string[], value: number) => void;
}) {
  return (
    <SettingsPanel title="Scrcpy">
      <div className="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
        <NumberField
          label="视频码率（Mbps）"
          value={optionalNumberAt(settings, ["framework", "scrcpy", "video_bit_rate_mbps"]) ?? 100}
          min={1}
          max={1000}
          onChange={(value) => onChange(["framework", "scrcpy", "video_bit_rate_mbps"], value === "" ? 100 : value)}
        />
        <NumberField
          label="最大帧率"
          value={optionalNumberAt(settings, ["framework", "scrcpy", "max_fps"]) ?? 60}
          min={1}
          max={240}
          onChange={(value) => onChange(["framework", "scrcpy", "max_fps"], value === "" ? 60 : value)}
        />
      </div>
      <div className="text-xs leading-5 text-muted-foreground">所有页面共用；定时执行详情页只替换连接设备。</div>
    </SettingsPanel>
  );
}

function ValidationList({ validation }: { validation?: ConfigValidation }) {
  if (!validation || validation.valid) return null;
  return (
    <div className="grid gap-1 rounded-md border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive">
      {validation.errors.slice(0, 4).map((error) => (
        <div key={`${error.source}-${error.path}-${error.message}`}>{error.path}: {error.message}</div>
      ))}
    </div>
  );
}
