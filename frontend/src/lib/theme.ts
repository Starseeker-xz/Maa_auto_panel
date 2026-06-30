export const themeModes = [
  { value: "system", label: "自动" },
  { value: "light", label: "明亮" },
  { value: "dark", label: "暗色" }
] as const;

export const themeColors = [
  { value: "cyan", label: "青色" },
  { value: "blue", label: "蓝色" },
  { value: "emerald", label: "绿色" },
  { value: "rose", label: "玫红" },
  { value: "amber", label: "琥珀" }
] as const;

export type ThemeMode = (typeof themeModes)[number]["value"];
export type ThemeColor = (typeof themeColors)[number]["value"];

export type ThemeSettings = {
  mode: ThemeMode;
  color: ThemeColor;
};

const DEFAULT_THEME: ThemeSettings = {
  mode: "system",
  color: "cyan"
};

const THEME_STORAGE_KEY = "linux-maa:theme";
let activeTheme = DEFAULT_THEME;

export function themeFromFrameworkSettings(data: Record<string, unknown> | undefined): ThemeSettings {
  const theme = objectValue(data?.theme);
  return normalizeTheme({
    mode: theme.mode,
    color: theme.color
  });
}

export function setActiveTheme(settings: Partial<Record<keyof ThemeSettings, unknown>>) {
  activeTheme = normalizeTheme(settings);
  applyTheme(activeTheme);
}

export function saveActiveTheme(settings: Partial<Record<keyof ThemeSettings, unknown>>) {
  setActiveTheme(settings);
  window.localStorage.setItem(THEME_STORAGE_KEY, JSON.stringify(activeTheme));
}

export function loadStoredTheme(): ThemeSettings | null {
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (!raw) return null;
    return normalizeTheme(JSON.parse(raw));
  } catch {
    return null;
  }
}

export function syncSystemTheme() {
  applyTheme(activeTheme);
}

function applyTheme(settings: ThemeSettings) {
  const root = document.documentElement;
  const resolvedMode = settings.mode === "system" ? preferredMode() : settings.mode;
  root.dataset.theme = resolvedMode;
  root.dataset.color = settings.color;
  root.style.colorScheme = resolvedMode;
}

function normalizeTheme(settings: Partial<Record<keyof ThemeSettings, unknown>>): ThemeSettings {
  const mode = themeModes.some((item) => item.value === settings.mode) ? settings.mode : DEFAULT_THEME.mode;
  const color = themeColors.some((item) => item.value === settings.color) ? settings.color : DEFAULT_THEME.color;
  return { mode: mode as ThemeMode, color: color as ThemeColor };
}

function preferredMode(): Exclude<ThemeMode, "system"> {
  if (typeof window === "undefined" || !window.matchMedia) return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}
