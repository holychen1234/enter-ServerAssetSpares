import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface Props {
  label: string;
  value: ReactNode;
  delta?: ReactNode;
  icon: LucideIcon;
  tone?: "default" | "success" | "warning" | "danger" | "info";
  className?: string;
}

const TONE: Record<NonNullable<Props["tone"]>, string> = {
  default: "text-primary bg-primary/10",
  success: "text-success bg-success/10",
  warning: "text-warning bg-warning/10",
  danger: "text-danger bg-danger/10",
  info: "text-info bg-info/10",
};

export function StatCard({ label, value, delta, icon: Icon, tone = "default", className }: Props) {
  return (
    <Card className={cn("shadow-card-soft transition-smooth hover:shadow-elevated", className)}>
      <CardContent className="flex items-center justify-between gap-4 p-5">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
          <p className="mt-2 text-3xl font-semibold tracking-tight text-foreground">{value}</p>
          {delta && <p className="mt-1 text-xs text-muted-foreground">{delta}</p>}
        </div>
        <div className={cn("flex h-12 w-12 items-center justify-center rounded-xl", TONE[tone])}>
          <Icon className="h-6 w-6" />
        </div>
      </CardContent>
    </Card>
  );
}
