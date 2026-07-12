import { isRecord } from "@/lib/objectPath";

export type ScrcpyOptions = {
  videoBitRateMbps: number;
  maxFps: number;
};

export const SCRCPY_DEFAULT_OPTIONS: ScrcpyOptions = { videoBitRateMbps: 100, maxFps: 60 };

export function connectionAddress(profile: Record<string, unknown>): string {
  const connection = profile.connection;
  if (!isRecord(connection)) return "";
  return typeof connection.address === "string" ? connection.address.trim() : "";
}

export function scrcpyOptions(settings: Record<string, unknown>): ScrcpyOptions {
  const framework = settings.framework;
  const scrcpy = isRecord(framework) ? framework.scrcpy : undefined;
  return {
    videoBitRateMbps: boundedNumber(isRecord(scrcpy) ? scrcpy.video_bit_rate_mbps : undefined, SCRCPY_DEFAULT_OPTIONS.videoBitRateMbps, 1, 1000),
    maxFps: boundedNumber(isRecord(scrcpy) ? scrcpy.max_fps : undefined, SCRCPY_DEFAULT_OPTIONS.maxFps, 1, 240)
  };
}

export function buildScrcpyUrl(device: string, options: ScrcpyOptions, requestId = createRequestId()): string {
  const address = device.trim();
  if (!address) throw new Error("未配置设备连接地址");

  const url = new URL("scrcpy-tool://launch/v1");
  url.searchParams.set("device", address);
  url.searchParams.append("arg", `--video-bit-rate=${options.videoBitRateMbps}M`);
  url.searchParams.append("arg", `--max-fps=${options.maxFps}`);
  url.searchParams.set("request_id", requestId);
  return url.toString();
}

function boundedNumber(value: unknown, fallback: number, minimum: number, maximum: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return fallback;
  return Math.min(maximum, Math.max(minimum, Math.round(value)));
}

function createRequestId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") return globalThis.crypto.randomUUID();

  const bytes = new Uint8Array(16);
  if (typeof globalThis.crypto?.getRandomValues === "function") {
    globalThis.crypto.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }

  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  return formatUuid(bytes);
}

function formatUuid(bytes: Uint8Array): string {
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0"));
  return [
    hex.slice(0, 4).join(""),
    hex.slice(4, 6).join(""),
    hex.slice(6, 8).join(""),
    hex.slice(8, 10).join(""),
    hex.slice(10, 16).join("")
  ].join("-");
}
