/**
 * Date/time utilities for consistent timezone-aware formatting.
 *
 * The backend sends ISO 8601 timestamps. When the timestamp has no
 * timezone suffix (naive), we treat it as UTC to avoid the 8-hour
 * discrepancy between UTC and Asia/Shanghai.
 */

/** Parse ISO string, treating naive (no-timezone) strings as UTC. */
export function toDate(s: string): Date {
  if (!s) return new Date(0); // fallback for empty/null
  return /[+-]\d{2}:\d{2}$/.test(s) || s.endsWith("Z")
    ? new Date(s)
    : new Date(s + "Z");
}

/** Format a date string to Beijing time (full datetime). */
export function formatBeijing(s: string): string {
  return toDate(s).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" });
}

/** Format a date string to Beijing time (time only). */
export function formatBeijingTime(s: string): string {
  return toDate(s).toLocaleTimeString("zh-CN", { timeZone: "Asia/Shanghai" });
}
