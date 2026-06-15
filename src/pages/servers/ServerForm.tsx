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
import type { Server } from "@/types/cmdb";
import { useEffect } from "react";

const schema = z.object({
  hostname: z.string().min(1, "必填"),
  sn: z.string().min(1, "必填"),
  assetTag: z.string().min(1, "必填"),
  manufacturer: z.enum(["Dell", "HPE", "Lenovo", "Inspur", "Supermicro", "Huawei", "XFusion", "Other"]),
  model: z.string().min(1, "必填"),
  cpuModel: z.string().min(1, "必填"),
  cpuCount: z.coerce.number().int().min(1).max(8),
  memoryGB: z.coerce.number().int().min(1),
  diskSlotCount: z.coerce.number().int().min(0).optional(),
  idc: z.string().min(1, "必填"),
  rack: z.string().min(1, "必填"),
  uPosition: z.string().min(1, "必填"),
  mgmtIp: z.string().min(1, "必填"),
  bizIp: z.string().min(1, "必填"),
  bmcProtocol: z.enum(["redfish", "ipmi"]),
  bmcUser: z.string().min(1, "必填"),
  bmcPassword: z.string().optional(),
  status: z.enum(["online", "offline", "maintenance", "retired"]),
  owner: z.string().min(1, "必填"),
  purchaseDate: z.string().min(1, "必填"),
  warrantyEnd: z.string().min(1, "必填"),
  tags: z.string().optional(),
  remark: z.string().optional(),
});

export type ServerFormData = z.infer<typeof schema>;

interface Props {
  open: boolean;
  initial?: Server | null;
  onClose: () => void;
  onSubmit: (data: Omit<Server, "id" | "createdAt" | "updatedAt">) => Promise<void> | void;
}

const EMPTY: ServerFormData = {
  hostname: "",
  sn: "",
  assetTag: "",
  manufacturer: "Dell",
  model: "",
  cpuModel: "",
  cpuCount: 2,
  memoryGB: 64,
  diskSlotCount: 0,
  idc: "",
  rack: "",
  uPosition: "",
  mgmtIp: "",
  bizIp: "",
  bmcProtocol: "redfish",
  bmcUser: "admin",
  bmcPassword: "",
  status: "online",
  owner: "",
  purchaseDate: "",
  warrantyEnd: "",
  tags: "",
  remark: "",
};

export function ServerForm({ open, initial, onClose, onSubmit }: Props) {
  const form = useForm<ServerFormData>({
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
          diskSlotCount: initial.diskSlotCount ?? 0,
          idc: initial.location.idc,
          rack: initial.location.rack,
          uPosition: initial.location.uPosition,
          mgmtIp: initial.mgmtIp,
          bizIp: initial.bizIp,
          bmcProtocol: initial.bmcProtocol,
          bmcUser: initial.bmcUser,
          bmcPassword: "",
          status: initial.status,
          owner: initial.owner,
          purchaseDate: initial.purchaseDate,
          warrantyEnd: initial.warrantyEnd,
          tags: initial.tags.join(","),
          remark: initial.remark ?? "",
        });
      } else {
        form.reset(EMPTY);
      }
    }
  }, [open, initial, form]);

  const handleSubmit = form.handleSubmit(async (values) => {
    // Empty password = "do not change". Only forward when the user actually typed something.
    const bmcPassword = values.bmcPassword?.trim() ? values.bmcPassword : undefined;
    await onSubmit({
      hostname: values.hostname,
      sn: values.sn,
      assetTag: values.assetTag,
      manufacturer: values.manufacturer,
      model: values.model,
      cpuModel: values.cpuModel,
      cpuCount: values.cpuCount,
      memoryGB: values.memoryGB,
      diskCount: (initial?.diskCount ?? 0),
      diskSlotCount: values.diskSlotCount ?? 0,
      location: { idc: values.idc, rack: values.rack, uPosition: values.uPosition },
      mgmtIp: values.mgmtIp,
      bizIp: values.bizIp,
      bmcProtocol: values.bmcProtocol,
      bmcUser: values.bmcUser,
      bmcPassword,
      status: values.status,
      owner: values.owner,
      purchaseDate: values.purchaseDate,
      warrantyEnd: values.warrantyEnd,
      tags: (values.tags ?? "").split(",").map((s) => s.trim()).filter(Boolean),
      remark: values.remark,
    });
  });

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{initial ? "编辑主机" : "新增主机"}</DialogTitle>
          <DialogDescription>填写服务器基本信息、机房位置与 BMC 接入参数。</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="主机名" error={form.formState.errors.hostname?.message}>
            <Input {...form.register("hostname")} placeholder="bj-prod-app-01" />
          </Field>
          <Field label="序列号 SN" error={form.formState.errors.sn?.message}>
            <Input {...form.register("sn")} />
          </Field>
          <Field label="资产编号" error={form.formState.errors.assetTag?.message}>
            <Input {...form.register("assetTag")} />
          </Field>
          <Field label="厂商">
            <Select value={form.watch("manufacturer")} onValueChange={(v) => form.setValue("manufacturer", v as ServerFormData["manufacturer"])}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {(["Dell", "HPE", "Lenovo", "Inspur", "Supermicro", "Huawei", "XFusion", "Other"] as const).map((m) => (
                  <SelectItem key={m} value={m}>{m === "XFusion" ? "超聚变" : m}</SelectItem>
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
          <Field label="CPU 数量">
            <Input type="number" min={1} {...form.register("cpuCount")} />
          </Field>
          <Field label="内存 (GB)">
            <Input type="number" min={1} {...form.register("memoryGB")} />
          </Field>
          <Field label="硬盘位数量" className="sm:col-span-2">
            <Input
              type="number"
              min={0}
              placeholder="0 表示未知（Inspur 等机型需手动填写）"
              {...form.register("diskSlotCount")}
            />
            <p className="mt-1 text-[11px] text-warning">
              部分机型（如 Inspur 浪潮）无法通过 Redfish 自动检测硬盘位数量，请在此手动填写。留空或填 0 表示未知。
            </p>
          </Field>
          <Field label="IDC">
            <Input {...form.register("idc")} placeholder="BJ-IDC-A" />
          </Field>
          <Field label="机柜">
            <Input {...form.register("rack")} placeholder="A03" />
          </Field>
          <Field label="U 位">
            <Input {...form.register("uPosition")} placeholder="U12-U13" />
          </Field>
          <Field label="业务 IP" error={form.formState.errors.bizIp?.message}>
            <Input {...form.register("bizIp")} placeholder="172.16.10.11" />
          </Field>
          <Field label="BMC IP">
            <Input {...form.register("mgmtIp")} placeholder="10.10.20.11" />
          </Field>
          <Field label="BMC 协议">
            <Select value={form.watch("bmcProtocol")} onValueChange={(v) => form.setValue("bmcProtocol", v as "redfish" | "ipmi")}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="redfish">Redfish (HTTPS)</SelectItem>
                <SelectItem value="ipmi">IPMI</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="BMC 用户名">
            <Input {...form.register("bmcUser")} />
          </Field>
          <Field
            label={initial ? "BMC 密码（留空保持不变）" : "BMC 密码"}
            className="sm:col-span-2"
          >
            <Input
              type="password"
              autoComplete="new-password"
              placeholder={
                initial
                  ? "如需修改请输入新密码，否则保持空白"
                  : "用于 Redfish/IPMI 实时采集"
              }
              {...form.register("bmcPassword")}
            />
          </Field>
          <Field label="状态">
            <Select value={form.watch("status")} onValueChange={(v) => form.setValue("status", v as ServerFormData["status"])}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="online">在线</SelectItem>
                <SelectItem value="offline">离线</SelectItem>
                <SelectItem value="maintenance">维护中</SelectItem>
                <SelectItem value="retired">已下架</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="负责人">
            <Input {...form.register("owner")} />
          </Field>
          <Field label="采购日期">
            <Input type="date" {...form.register("purchaseDate")} />
          </Field>
          <Field label="保修截止">
            <Input type="date" {...form.register("warrantyEnd")} />
          </Field>
          <Field label="标签（逗号分隔）" className="sm:col-span-2">
            <Input {...form.register("tags")} placeholder="prod,web" />
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
