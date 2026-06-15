import { AlertCircle, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SlotInfo } from "@/types/cmdb";

interface SlotUsageBarProps {
  slotInfo: SlotInfo;
  label: string;
  icon: React.ReactNode;
  className?: string;
}

/** Choose a color class based on the fill percentage. */
function slotColor(used: number, total: number): string {
  if (total <= 0) return "bg-muted-foreground/30";
  const pct = (used / total) * 100;
  if (pct >= 95) return "bg-destructive";
  if (pct >= 80) return "bg-warning";
  return "bg-success";
}

/** Build a compact label describing the slot count. */
function slotLabel(info: SlotInfo): string {
  if (info.total > 0) {
    const ff = info.formFactor ? ` ${info.formFactor}"` : "";
    return `${info.total} 个${ff}槽位`;
  }
  if (info.used > 0) return "槽位总数未配置";
  return "暂无数据";
}

/** Build the usage summary text. */
function usageText(info: SlotInfo): string {
  if (info.total > 0) {
    if (info.used >= info.total) return `${info.total} / ${info.total} 已满`;
    return `${info.used} / ${info.total} 已占用`;
  }
  if (info.used > 0) return `${info.used} 已安装`;
  return "";
}

export function SlotUsageBar({ slotInfo, label, icon, className }: SlotUsageBarProps) {
  const { total, used } = slotInfo;
  const pct = total > 0 ? Math.min(100, Math.round((used / total) * 100)) : 0;

  return (
    <div className={cn("space-y-1.5", className)}>
      {/* Header row */}
      <div className="flex items-center justify-between text-xs">
        <span className="flex items-center gap-1.5 text-muted-foreground">
          {icon}
          {label}
        </span>
        <span className="font-medium tabular-nums text-foreground">
          {usageText(slotInfo)}
        </span>
      </div>

      {/* Progress bar */}
      {total > 0 ? (
        <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
          <div
            className={cn("h-full rounded-full transition-all", slotColor(used, total))}
            style={{ width: `${pct}%` }}
          />
        </div>
      ) : used > 0 ? (
        /* Unknown total — dashed outline with hint */
        <div className="flex items-center gap-2 rounded border border-dashed border-warning/40 bg-warning/5 px-2.5 py-2 text-[11px] text-warning">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          <span>
            硬盘位总数未配置，请在服务器信息编辑页中手动设置。
          </span>
        </div>
      ) : (
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <CheckCircle2 className="h-3 w-3" />
          暂无槽位数据
        </div>
      )}

      {/* Form factor / backplane detail */}
      {total > 0 && (
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          {slotLabel(slotInfo)}
          {slotInfo.backplanes && slotInfo.backplanes.length > 1 && (
            <>
              {" · "}
              {slotInfo.backplanes
                .map((bp) => `${bp.slots}×${bp.formFactor}"`)
                .join(" + ")}
            </>
          )}
        </p>
      )}
    </div>
  );
}
