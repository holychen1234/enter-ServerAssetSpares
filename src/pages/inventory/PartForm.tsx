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
import type { Part, PartCategory } from "@/types/cmdb";
import { useEffect } from "react";

const schema = z.object({
  category: z.enum(["disk", "memory", "nic", "optical", "other"]),
  brand: z.string().min(1, "必填"),
  model: z.string().min(1, "必填"),
  spec: z.string().min(1, "必填"),
  safetyStock: z.coerce.number().int().min(0),
  unit: z.string().min(1, "必填"),
  location: z.string().min(1, "必填"),
  status: z.enum(["in_stock", "allocated", "in_use", "scrapped"]),
  remark: z.string().optional(),
});

export type PartFormData = z.infer<typeof schema>;

const EMPTY: PartFormData = {
  category: "disk",
  brand: "",
  model: "",
  spec: "",
  safetyStock: 0,
  unit: "块",
  location: "",
  status: "in_stock",
  remark: "",
};

interface Props {
  open: boolean;
  initial?: Part | null;
  onClose: () => void;
  onSubmit: (data: Omit<Part, "id" | "createdAt">) => Promise<void> | void;
}

const CATEGORY_LABEL: Record<PartCategory, string> = {
  disk: "硬盘",
  memory: "内存",
  nic: "网卡",
  optical: "光模块",
  other: "其他",
};

export function PartForm({ open, initial, onClose, onSubmit }: Props) {
  const form = useForm<PartFormData>({ resolver: zodResolver(schema), defaultValues: EMPTY });

  useEffect(() => {
    if (open) {
      if (initial) {
        form.reset({
          category: initial.category,
          brand: initial.brand,
          model: initial.model,
          spec: initial.spec,
          safetyStock: initial.safetyStock,
          unit: initial.unit,
          location: initial.location,
          status: initial.status,
          remark: initial.remark,
        });
      } else {
        form.reset(EMPTY);
      }
    }
  }, [open, initial, form]);

  const handle = form.handleSubmit(async (v) => {
    await onSubmit(v);
  });

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{initial ? "编辑备件" : "新增备件"}</DialogTitle>
          <DialogDescription>登记备件型号、规格、库存与存放位置。</DialogDescription>
        </DialogHeader>
        <form onSubmit={handle} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="类别">
            <Select value={form.watch("category")} onValueChange={(v) => form.setValue("category", v as PartCategory)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.entries(CATEGORY_LABEL).map(([k, v]) => (
                  <SelectItem key={k} value={k}>{v}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="状态">
            <Select value={form.watch("status")} onValueChange={(v) => form.setValue("status", v as PartFormData["status"])}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="in_stock">在库</SelectItem>
                <SelectItem value="allocated">已分配</SelectItem>
                <SelectItem value="in_use">使用中</SelectItem>
                <SelectItem value="scrapped">报废</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="品牌" error={form.formState.errors.brand?.message}>
            <Input {...form.register("brand")} />
          </Field>
          <Field label="型号" error={form.formState.errors.model?.message}>
            <Input {...form.register("model")} />
          </Field>
          <Field label="规格" error={form.formState.errors.spec?.message} className="sm:col-span-2">
            <Input {...form.register("spec")} placeholder="例如 1.92TB U.2 NVMe SSD" />
          </Field>
          <Field label="单位">
            <Input {...form.register("unit")} />
          </Field>
          <Field label="安全库存">
            <Input type="number" min={0} {...form.register("safetyStock")} />
          </Field>
          <Field label="存放位置" className="sm:col-span-2">
            <Input {...form.register("location")} />
          </Field>
          <Field label="备注" className="sm:col-span-2">
            <Textarea rows={2} {...form.register("remark")} />
          </Field>
          <DialogFooter className="sm:col-span-2">
            <Button type="button" variant="outline" onClick={onClose}>取消</Button>
            <Button type="submit">保存</Button>
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
