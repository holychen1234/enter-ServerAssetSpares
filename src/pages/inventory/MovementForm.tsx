import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Part, Server, MovementType } from "@/types/cmdb";
import { useEffect } from "react";
import { useAuth } from "@/hooks/use-auth";

const schema = z.object({
  partId: z.string().min(1, "请选择备件"),
  type: z.enum(["inbound", "outbound", "return", "scrap"]),
  quantity: z.coerce.number().int().min(1, "数量必须大于 0"),
  operator: z.string().min(1, "必填"),
  relatedServerId: z.string().optional(),
  reason: z.string().min(1, "必填"),
});

export type MovementFormData = z.infer<typeof schema>;

interface Props {
  open: boolean;
  defaultType: MovementType;
  parts: Part[];
  servers: Server[];
  onClose: () => void;
  onSubmit: (data: MovementFormData) => Promise<void> | void;
}

export function MovementForm({ open, defaultType, parts, servers, onClose, onSubmit }: Props) {
  const { user } = useAuth();
  const form = useForm<MovementFormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      partId: "",
      type: defaultType,
      quantity: 1,
      operator: user?.username ?? "",
      relatedServerId: "",
      reason: "",
    },
  });

  useEffect(() => {
    if (open) {
      form.reset({
        partId: "",
        type: defaultType,
        quantity: 1,
        operator: user?.username ?? "",
        relatedServerId: "",
        reason: "",
      });
    }
  }, [open, defaultType, user, form]);

  const type = form.watch("type");
  const showServer = type === "outbound" || type === "return";

  const handle = form.handleSubmit(async (v) => {
    await onSubmit({
      ...v,
      relatedServerId: showServer && v.relatedServerId ? v.relatedServerId : undefined,
    });
  });

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>新建出入库记录</DialogTitle>
          <DialogDescription>记录备件的入库、出库、归还或报废动作。</DialogDescription>
        </DialogHeader>
        <form onSubmit={handle} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="动作类型">
            <Select value={form.watch("type")} onValueChange={(v) => form.setValue("type", v as MovementType)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="inbound">入库</SelectItem>
                <SelectItem value="outbound">出库 / 领用</SelectItem>
                <SelectItem value="return">归还</SelectItem>
                <SelectItem value="scrap">报废</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="数量" error={form.formState.errors.quantity?.message}>
            <Input type="number" min={1} {...form.register("quantity")} />
          </Field>
          <Field label="备件" error={form.formState.errors.partId?.message} className="sm:col-span-2">
            <Select value={form.watch("partId")} onValueChange={(v) => form.setValue("partId", v)}>
              <SelectTrigger><SelectValue placeholder="选择备件" /></SelectTrigger>
              <SelectContent>
                {parts.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    [{p.category}] {p.brand} {p.model} · 库存 {p.stock}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          {showServer && (
            <Field label="关联服务器" className="sm:col-span-2">
              <Select value={form.watch("relatedServerId") || ""} onValueChange={(v) => form.setValue("relatedServerId", v)}>
                <SelectTrigger><SelectValue placeholder="选择服务器（可选）" /></SelectTrigger>
                <SelectContent>
                  {servers.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.hostname} · {s.location.idc} {s.location.rack}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          )}
          <Field label="操作人" error={form.formState.errors.operator?.message}>
            <Input {...form.register("operator")} />
          </Field>
          <Field label="原因 / 备注" error={form.formState.errors.reason?.message} className="sm:col-span-2">
            <Textarea rows={2} {...form.register("reason")} />
          </Field>

          <DialogFooter className="sm:col-span-2">
            <Button type="button" variant="outline" onClick={onClose}>取消</Button>
            <Button type="submit">提交</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  error,
  children,
  className,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <Label className="text-xs font-medium text-muted-foreground">{label}</Label>
      <div className="mt-1.5">{children}</div>
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
    </div>
  );
}
