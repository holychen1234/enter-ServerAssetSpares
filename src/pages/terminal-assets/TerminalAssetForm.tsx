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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { TerminalAsset } from "@/types/cmdb";
import { useEffect } from "react";

const schema = z.object({
  hostname: z.string().min(1, "必填"),
  sn: z.string().min(1, "必填"),
  assetTag: z.string().min(1, "必填"),
  manufacturer: z.enum(["Dell", "HP", "Lenovo", "Apple", "Huawei", "ASUS", "Acer", "Microsoft", "Other"]),
  model: z.string().min(1, "必填"),
  cpuModel: z.string().min(1, "必填"),
  cpuCount: z.coerce.number().int().min(1),
  memoryGB: z.coerce.number().int().min(1),
  diskType: z.string().min(1, "必填"),
  diskCapacityGB: z.coerce.number().int().min(0),
  macAddress: z.string().optional(),
  os: z.enum(["Windows 10", "Windows 11", "macOS", "Ubuntu", "CentOS", "Other"]),
  osVersion: z.string().optional(),
  bizIp: z.string().optional(),
  userName: z.string().optional(),
  department: z.string().optional(),
  officeBuilding: z.string().optional(),
  floor: z.string().optional(),
  seat: z.string().optional(),
  status: z.enum(["online", "offline", "maintenance", "retired"]),
  purchaseDate: z.string().optional(),
  warrantyEnd: z.string().optional(),
  tags: z.string().optional(),
  remark: z.string().optional(),
});

export type TerminalAssetFormData = z.infer<typeof schema>;

interface Props {
  open: boolean;
  initial?: TerminalAsset | null;
  onClose: () => void;
  onSubmit: (data: Omit<TerminalAsset, "id" | "createdAt" | "updatedAt">) => Promise<void> | void;
}

const EMPTY: TerminalAssetFormData = {
  hostname: "",
  sn: "",
  assetTag: "",
  manufacturer: "Dell",
  model: "",
  cpuModel: "",
  cpuCount: 4,
  memoryGB: 16,
  diskType: "SSD",
  diskCapacityGB: 512,
  macAddress: "",
  os: "Windows 11",
  osVersion: "",
  bizIp: "",
  userName: "",
  department: "",
  officeBuilding: "",
  floor: "",
  seat: "",
  status: "online",
  purchaseDate: "",
  warrantyEnd: "",
  tags: "",
  remark: "",
};

export function TerminalAssetForm({ open, initial, onClose, onSubmit }: Props) {
  const form = useForm<TerminalAssetFormData>({
    resolver: zodResolver(schema),
    defaultValues: EMPTY,
  });

  useEffect(() => {
    if (open) {
      if (initial) {
        form.reset({
          hostname: initial.hostname,
          sn: initial.sn,
          assetTag: initial.assetTag,
          manufacturer: initial.manufacturer,
          model: initial.model,
          cpuModel: initial.cpuModel,
          cpuCount: initial.cpuCount,
          memoryGB: initial.memoryGB,
          diskType: initial.diskType ?? "SSD",
          diskCapacityGB: initial.diskCapacityGB,
          macAddress: initial.macAddress ?? "",
          os: initial.os,
          osVersion: initial.osVersion ?? "",
          bizIp: initial.bizIp ?? "",
          userName: initial.userName ?? "",
          department: initial.department ?? "",
          officeBuilding: initial.officeBuilding ?? "",
          floor: initial.floor ?? "",
          seat: initial.seat ?? "",
          status: initial.status,
          purchaseDate: initial.purchaseDate || "",
          warrantyEnd: initial.warrantyEnd || "",
          tags: initial.tags.join(","),
          remark: initial.remark ?? "",
        });
      } else {
        form.reset(EMPTY);
      }
    }
  }, [open, initial, form]);

  const handleSubmit = form.handleSubmit(async (values) => {
    await onSubmit({
      hostname: values.hostname,
      sn: values.sn,
      assetTag: values.assetTag,
      manufacturer: values.manufacturer,
      model: values.model,
      cpuModel: values.cpuModel,
      cpuCount: values.cpuCount,
      memoryGB: values.memoryGB,
      diskType: values.diskType ?? "SSD",
      diskCapacityGB: values.diskCapacityGB,
      macAddress: values.macAddress ?? "",
      os: values.os,
      osVersion: values.osVersion ?? "",
      bizIp: values.bizIp ?? "",
      userName: values.userName ?? "",
      department: values.department ?? "",
      officeBuilding: values.officeBuilding ?? "",
      floor: values.floor ?? "",
      seat: values.seat ?? "",
      status: values.status,
      purchaseDate: values.purchaseDate ?? "",
      warrantyEnd: values.warrantyEnd ?? "",
      tags: (values.tags ?? "").split(",").map((s) => s.trim()).filter(Boolean),
      remark: values.remark,
    });
  });

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{initial ? "编辑终端资产" : "新增终端资产"}</DialogTitle>
          <DialogDescription>填写终端硬件配置、操作系统、使用者与位置信息。</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="计算机名" error={form.formState.errors.hostname?.message}>
            <Input {...form.register("hostname")} placeholder="BJ-FIN-001" />
          </Field>
          <Field label="序列号 SN" error={form.formState.errors.sn?.message}>
            <Input {...form.register("sn")} />
          </Field>
          <Field label="资产编号" error={form.formState.errors.assetTag?.message}>
            <Input {...form.register("assetTag")} />
          </Field>
          <Field label="厂商">
            <Select value={form.watch("manufacturer")} onValueChange={(v) => form.setValue("manufacturer", v as TerminalAssetFormData["manufacturer"])}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {(["Dell", "HP", "Lenovo", "Apple", "Huawei", "ASUS", "Acer", "Microsoft", "Other"] as const).map((m) => (
                  <SelectItem key={m} value={m}>{m}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="型号" error={form.formState.errors.model?.message}>
            <Input {...form.register("model")} />
          </Field>
          <Field label="CPU 型号" error={form.formState.errors.cpuModel?.message}>
            <Input {...form.register("cpuModel")} />
          </Field>
          <Field label="CPU 核心数">
            <Input type="number" min={1} {...form.register("cpuCount")} />
          </Field>
          <Field label="内存 (GB)">
            <Input type="number" min={1} {...form.register("memoryGB")} />
          </Field>
          <Field label="硬盘类型" error={form.formState.errors.diskType?.message}>
            <Select value={form.watch("diskType")} onValueChange={(v) => form.setValue("diskType", v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="SSD">SSD</SelectItem>
                <SelectItem value="HDD">HDD</SelectItem>
                <SelectItem value="NVMe">NVMe</SelectItem>
                <SelectItem value="混合">混合</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="硬盘容量 (GB)">
            <Input type="number" min={0} {...form.register("diskCapacityGB")} />
          </Field>
          <Field label="MAC 地址">
            <Input {...form.register("macAddress")} placeholder="AA:BB:CC:DD:EE:FF" />
          </Field>
          <Field label="操作系统">
            <Select value={form.watch("os")} onValueChange={(v) => form.setValue("os", v as TerminalAssetFormData["os"])}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {(["Windows 10", "Windows 11", "macOS", "Ubuntu", "CentOS", "Other"] as const).map((o) => (
                  <SelectItem key={o} value={o}>{o}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="操作系统版本">
            <Input {...form.register("osVersion")} placeholder="22H2 / 14.5 / 24.04" />
          </Field>
          <Field label="IP 地址">
            <Input {...form.register("bizIp")} />
          </Field>
          <Field label="使用人">
            <Input {...form.register("userName")} />
          </Field>
          <Field label="部门">
            <Input {...form.register("department")} />
          </Field>
          <Field label="办公楼">
            <Input {...form.register("officeBuilding")} />
          </Field>
          <Field label="楼层">
            <Input {...form.register("floor")} />
          </Field>
          <Field label="工位">
            <Input {...form.register("seat")} />
          </Field>
          <Field label="状态">
            <Select value={form.watch("status")} onValueChange={(v) => form.setValue("status", v as TerminalAssetFormData["status"])}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="online">在线</SelectItem>
                <SelectItem value="offline">离线</SelectItem>
                <SelectItem value="maintenance">维修中</SelectItem>
                <SelectItem value="retired">已报废</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="采购日期">
            <Input type="date" {...form.register("purchaseDate")} />
          </Field>
          <Field label="保修截止">
            <Input type="date" {...form.register("warrantyEnd")} />
          </Field>

          <Field label="标签（逗号分隔）" className="sm:col-span-2">
            <Input {...form.register("tags")} placeholder="财务,办公" />
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
