import { cn } from "@/lib/utils";
import type { Health, ServerStatus, PartStatus, MovementType } from "@/types/cmdb";

type StatusKind = "health" | "server" | "part" | "movement";

interface Props {
  kind: StatusKind;
  value: Health | ServerStatus | PartStatus | MovementType | string;
  className?: string;
  pulse?: boolean;
}

const HEALTH_LABELS: Record<string, { label: string; cls: string }> = {
  OK: { label: "正常", cls: "text-success bg-success/10 border-success/30" },
  Warning: { label: "警告", cls: "text-warning bg-warning/10 border-warning/30" },
  Critical: { label: "严重", cls: "text-danger bg-danger/10 border-danger/30" },
};

const SERVER_LABELS: Record<string, { label: string; cls: string }> = {
  online: { label: "在线", cls: "text-success bg-success/10 border-success/30" },
  offline: { label: "离线", cls: "text-danger bg-danger/10 border-danger/30" },
  maintenance: { label: "维护中", cls: "text-warning bg-warning/10 border-warning/30" },
  retired: { label: "已下架", cls: "text-muted-foreground bg-muted border-border" },
};

const PART_LABELS: Record<string, { label: string; cls: string }> = {
  in_stock: { label: "在库", cls: "text-success bg-success/10 border-success/30" },
  allocated: { label: "已分配", cls: "text-info bg-info/10 border-info/30" },
  in_use: { label: "使用中", cls: "text-primary bg-primary/10 border-primary/30" },
  scrapped: { label: "报废", cls: "text-muted-foreground bg-muted border-border" },
};

const MOVEMENT_LABELS: Record<string, { label: string; cls: string }> = {
  inbound: { label: "入库", cls: "text-success bg-success/10 border-success/30" },
  outbound: { label: "出库", cls: "text-info bg-info/10 border-info/30" },
  return: { label: "归还", cls: "text-primary bg-primary/10 border-primary/30" },
  scrap: { label: "报废", cls: "text-danger bg-danger/10 border-danger/30" },
};

export function StatusBadge({ kind, value, className, pulse }: Props) {
  const map =
    kind === "health"
      ? HEALTH_LABELS
      : kind === "server"
        ? SERVER_LABELS
        : kind === "part"
          ? PART_LABELS
          : MOVEMENT_LABELS;
  const cfg = map[value] ?? { label: String(value), cls: "text-muted-foreground bg-muted border-border" };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        cfg.cls,
        pulse && "pulse-dot",
        className,
      )}
    >
      {cfg.label}
    </span>
  );
}
