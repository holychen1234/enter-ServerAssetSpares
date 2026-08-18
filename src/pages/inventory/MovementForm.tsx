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
import { Checkbox } from "@/components/ui/checkbox";
import type { Part, PartItem, Server, MovementType } from "@/types/cmdb";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/use-auth";
import { listPartItems } from "@/lib/api/cmdb";

const schema = z.object({
  partId: z.string().min(1, "请选择备件"),
  type: z.enum(["inbound", "outbound", "return", "scrap"]),
  quantity: z.coerce.number().int().min(1, "数量必须大于 0"),
  operator: z.string().min(1, "必填"),
  relatedServerId: z.string().optional(),
  partItemId: z.string().optional(),
  partItemIds: z.array(z.string()),
  itemSns: z.string().optional(),
  items: z.array(z.object({ sn: z.string().optional(), location: z.string().optional() })).optional(),
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
      partItemIds: [],
      itemSns: "",
      reason: "",
    },
  });

  const [availItems, setAvailItems] = useState<PartItem[]>([]);
  const [loadingItems, setLoadingItems] = useState(false);
  const watchPartId = form.watch("partId");
  const watchType = form.watch("type");

  useEffect(() => {
    if (open) {
      form.reset({
        partId: "",
        type: defaultType,
        quantity: 1,
        operator: user?.username ?? "",
        relatedServerId: "",
        partItemIds: [],
        itemSns: "",
        reason: "",
      });
      setAvailItems([]);
    }
  }, [open, defaultType, user, form]);

  useEffect(() => {
    if (!watchPartId || watchType === "inbound") {
      setAvailItems([]);
      form.setValue("partItemIds", []);
      return;
    }
    setLoadingItems(true);
    listPartItems(watchPartId)
      .then((items) => {
        if (watchType === "outbound") {
          setAvailItems(items.filter((it) => it.status === "in_stock"));
        } else if (watchType === "return") {
          setAvailItems(items.filter((it) => it.status === "in_use" || it.status === "allocated"));
        } else {
          setAvailItems(items.filter((it) => it.status !== "scrapped"));
        }
      })
      .catch(() => setAvailItems([]))
      .finally(() => setLoadingItems(false));
  }, [watchPartId, watchType, form]);

  const isPerItem = watchType !== "inbound";
  const showServer = watchType === "outbound" || watchType === "return";
  const selectedIds = form.watch("partItemIds");

  const toggleItem = (id: string) => {
    const current = form.getValues("partItemIds");
    if (current.includes(id)) {
      form.setValue("partItemIds", current.filter((x) => x !== id));
    } else {
      form.setValue("partItemIds", [...current, id]);
    }
  };

  const toggleAll = () => {
    if (selectedIds.length === availItems.length) {
      form.setValue("partItemIds", []);
    } else {
      form.setValue("partItemIds", availItems.map((it) => it.id));
    }
  };

  const handle = form.handleSubmit(async (v) => {
    if (isPerItem && v.partItemIds.length === 0) {
      return;
    }

   if (isPerItem) {
      let ok = 0;
      const failed: string[] = [];
      for (const itemId of v.partItemIds) {
        try {
          await onSubmit({
            partId: v.partId,
            type: v.type,
            quantity: 1,
            operator: v.operator,
            relatedServerId: showServer && v.relatedServerId ? v.relatedServerId : undefined,
            partItemId: itemId,
            partItemIds: [],
            reason: v.reason,
          });
          ok++;
        } catch {
          failed.push(itemId);
        }
      }
      if (failed.length > 0) {
        throw new Error(
          `${ok} 件成功，${failed.length} 件失败（单件 ID: ${failed.join(", ").slice(0, 80)}…）`,
        );
      }
    } else {
      // Inbound: parse SN paste into items array
      const sns = (v.itemSns || "")
        .split(/[\n,]/)
        .map((s) => s.trim())
        .filter(Boolean);
      await onSubmit({
        partId: v.partId,
        type: v.type,
        // When SNs are pasted, the actual item count wins — the quantity
        // field must not desync from the items being created.
        quantity: sns.length > 0 ? sns.length : v.quantity,
        operator: v.operator,
        partItemId: undefined,
        partItemIds: [],
        itemSns: v.itemSns,
        items: sns.length > 0 ? sns.map((sn) => ({ sn })) : undefined,
        reason: v.reason,
      });
    }
  });

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>新建出入库记录</DialogTitle>
          <DialogDescription>
            记录备件的入库、出库、归还或报废动作。
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handle} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="动作类型">
            <Select
              value={form.watch("type")}
              onValueChange={(v) => {
                form.setValue("type", v as MovementType);
                form.setValue("partItemIds", []);
              }}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="inbound">入库</SelectItem>
                <SelectItem value="outbound">出库 / 领用</SelectItem>
                <SelectItem value="return">归还</SelectItem>
                <SelectItem value="scrap">报废</SelectItem>
              </SelectContent>
            </Select>
          </Field>

          {!isPerItem && (
            <Field label="数量" error={form.formState.errors.quantity?.message}>
              <Input type="number" min={1} {...form.register("quantity")} />
            </Field>
          )}

          {isPerItem && selectedIds.length > 0 && (
            <Field label="已选数量">
              <div className="mt-1.5 font-mono text-lg font-semibold text-foreground">
                {selectedIds.length} 件
              </div>
            </Field>
          )}

          <Field label="备件" error={form.formState.errors.partId?.message} className="sm:col-span-2">
            <Select
              value={form.watch("partId")}
              onValueChange={(v) => {
                form.setValue("partId", v);
                form.setValue("partItemIds", []);
              }}
            >
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

          {/* Per-item multi-select for outbound/return/scrap */}
          {isPerItem && watchPartId && (
            <Field
              label="选择单件（SN）"
              error={form.formState.errors.partItemIds?.message}
              className="sm:col-span-2"
            >
              {loadingItems ? (
                <p className="text-xs text-muted-foreground">加载中…</p>
              ) : availItems.length === 0 ? (
                <p className="text-xs text-amber-500">没有可用的单件</p>
              ) : (
                <div className="rounded-lg border border-border">
                  <div className="flex items-center gap-2 border-b border-border px-3 py-2">
                    <Checkbox
                      id="toggle-all"
                      checked={selectedIds.length === availItems.length}
                      onCheckedChange={toggleAll}
                    />
                    <label htmlFor="toggle-all" className="text-xs text-muted-foreground cursor-pointer">
                      全选 / 取消 ({availItems.length} 件可用)
                    </label>
                  </div>
                  <div className="max-h-48 overflow-y-auto">
                    {availItems.map((it) => (
                      <div
                        key={it.id}
                        className="flex items-center gap-2 border-b border-border/50 px-3 py-2 last:border-b-0 hover:bg-muted/20"
                      >
                        <Checkbox
                          id={`item-${it.id}`}
                          checked={selectedIds.includes(it.id)}
                          onCheckedChange={() => toggleItem(it.id)}
                        />
                        <label
                          htmlFor={`item-${it.id}`}
                          className="flex-1 cursor-pointer text-xs"
                        >
                          <span className="font-mono text-foreground">
                            {it.sn || `(未录入 SN) ${it.id.slice(0, 8)}`}
                          </span>
                          <span className="ml-2 text-muted-foreground">
                            {it.location || "—"}
                          </span>
                        </label>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Field>
          )}

          {/* Inbound: SN paste area */}
          {!isPerItem && (
            <Field label="SN 序列号（可选，每行一个）" className="sm:col-span-2">
              <Textarea
                rows={4}
                placeholder="WD-abc123&#10;WD-def456&#10;WD-ghi789"
                {...form.register("itemSns")}
              />
              <p className="mt-1 text-[11px] text-muted-foreground">
                录入的 SN 数量应与上方「数量」一致。留空则仅增加库存计数。
              </p>
            </Field>
          )}

          {showServer && (
            <Field label="关联主机" className="sm:col-span-2">
              <Select
                value={form.watch("relatedServerId") || ""}
                onValueChange={(v) => form.setValue("relatedServerId", v)}
              >
                <SelectTrigger><SelectValue placeholder="选择主机（可选）" /></SelectTrigger>
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
          <Field
            label="原因 / 备注"
            error={form.formState.errors.reason?.message}
            className="sm:col-span-2"
          >
            <Textarea rows={2} {...form.register("reason")} />
          </Field>

          <DialogFooter className="sm:col-span-2">
            <Button type="button" variant="outline" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={isPerItem && selectedIds.length === 0}>
              提交
            </Button>
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
