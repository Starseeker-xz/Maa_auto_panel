import { CircleHelp } from "lucide-react";

import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { DELETE_VALUE, booleanAt, optionalNumberAt, setNestedValue, stringAt } from "@/lib/objectPath";
import { cn } from "@/lib/utils";

const CONNECTION_TYPES = ["ADB", "PlayCover", "MuMuPro", "Waydroid"];
const CONNECTION_CONFIGS = ["", "CompatPOSIXShell", "General", "MacPlayTools"];
const TOUCH_MODES = ["ADB", "MiniTouch", "MaaTouch", "MacPlayTools", "MaaFwAdb"];

type ProfileEditorProps = {
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
};

export function ProfileEditor({ value, onChange }: ProfileEditorProps) {
  const cpuOcrEnabled = booleanAt(value, ["static_options", "cpu_ocr"], true);

  function update(path: string[], nextValue: unknown) {
    onChange(setNestedValue(value, path, nextValue));
  }

  return (
    <div className="grid gap-3">
      <div className="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
        <SelectField
          label="连接类型"
          help="常规 Android 设备和模拟器选 ADB。"
          value={stringAt(value, ["connection", "type"], "ADB")}
          options={CONNECTION_TYPES.map((item) => [item, item])}
          onChange={(item) => update(["connection", "type"], item)}
        />
        <SelectField
          label="连接配置"
          help="Linux/redroid 通常用 CompatPOSIXShell。"
          value={stringAt(value, ["connection", "config"], "") || "__unset"}
          options={CONNECTION_CONFIGS.map((item) => [item || "__unset", item || "未指定"])}
          onChange={(item) => update(["connection", "config"], item === "__unset" ? DELETE_VALUE : item)}
        />
        <TextField
          label="ADB 可执行文件"
          value={stringAt(value, ["connection", "adb_path"], "adb")}
          onChange={(item) => update(["connection", "adb_path"], item)}
        />
        <TextField
          label="连接地址"
          value={stringAt(value, ["connection", "address"], "")}
          onChange={(item) => update(["connection", "address"], item)}
        />
        <SelectField
          label="触控模式"
          value={stringAt(value, ["instance_options", "touch_mode"], "ADB")}
          options={TOUCH_MODES.map((item) => [item, item])}
          onChange={(item) => update(["instance_options", "touch_mode"], item)}
        />
        <NumberField
          label="用于 OCR 的 GPU ID"
          disabled={cpuOcrEnabled}
          value={optionalNumberAt(value, ["static_options", "gpu_ocr"])}
          onChange={(item) => update(["static_options", "gpu_ocr"], item === "" ? DELETE_VALUE : item)}
        />
      </div>
      <div className="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
        <CheckboxField
          label="使用 CPU 进行 OCR"
          checked={cpuOcrEnabled}
          onChange={(item) => update(["static_options", "cpu_ocr"], item)}
        />
        <CheckboxField
          label="部署时暂停游戏"
          checked={booleanAt(value, ["instance_options", "deployment_with_pause"], false)}
          onChange={(item) => update(["instance_options", "deployment_with_pause"], item)}
        />
        <CheckboxField
          label="启用 adb-lite"
          checked={booleanAt(value, ["instance_options", "adb_lite_enabled"], false)}
          onChange={(item) => update(["instance_options", "adb_lite_enabled"], item)}
        />
        <CheckboxField
          label="退出时关闭 ADB"
          checked={booleanAt(value, ["instance_options", "kill_adb_on_exit"], false)}
          onChange={(item) => update(["instance_options", "kill_adb_on_exit"], item)}
        />
      </div>
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

function TextField({ label, value, help, onChange }: { label: string; value: string; help?: string; onChange: (value: string) => void }) {
  return (
    <div className="grid min-w-0 gap-1.5">
      <FieldLabel label={label} help={help} />
      <Input className="min-w-0" value={value} onChange={(event) => onChange(event.target.value)} />
    </div>
  );
}

function NumberField({
  label,
  value,
  disabled,
  onChange
}: {
  label: string;
  value: number | "";
  disabled?: boolean;
  onChange: (value: number | "") => void;
}) {
  return (
    <div className="grid min-w-0 gap-1.5">
      <FieldLabel label={label} />
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

function CheckboxField({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className={cn("min-w-0 rounded-md border bg-background p-2 text-sm")}>
      <span className="flex min-h-5 min-w-0 items-start gap-2">
        <Checkbox checked={checked} onCheckedChange={(value) => onChange(value === true)} />
        <span className="min-w-0 break-words leading-5">{label}</span>
      </span>
    </label>
  );
}
