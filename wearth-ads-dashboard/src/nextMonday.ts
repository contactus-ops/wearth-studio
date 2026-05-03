import { DateTime } from "luxon";

/** Next Monday 07:00 Asia/Kolkata as a JS Date (UTC instant). */
export function nextMonday7amIST(): Date {
  const dt = DateTime.now().setZone("Asia/Kolkata");
  let target = dt.set({
    weekday: 1,
    hour: 7,
    minute: 0,
    second: 0,
    millisecond: 0,
  });
  if (target <= dt) target = target.plus({ weeks: 1 });
  return target.toJSDate();
}

export function msUntilNextMonday7amIST(): number {
  return Math.max(0, nextMonday7amIST().getTime() - Date.now());
}

export function formatDuration(ms: number): string {
  if (ms <= 0) return "0h 0m 0s";
  const s = Math.floor(ms / 1000);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (d > 0) return `${d}d ${h}h ${m}m`;
  return `${h}h ${m}m ${sec}s`;
}
