import { CheckboxField, NumberField, SelectField, TextField } from "@/components/FormFields";
import { CONNECTION_CONFIGS, CONNECTION_TYPES, TOUCH_MODES } from "@/lib/constants";
import { DELETE_VALUE, booleanAt, optionalNumberAt, setNestedValue, stringAt } from "@/lib/objectPath";

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
