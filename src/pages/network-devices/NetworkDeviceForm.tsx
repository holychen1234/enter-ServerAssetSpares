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
import type { NetworkDevice } from "@/types/cmdb";
import { useEffect } from "react";

const schema = z.object({
  hostname: z.string().min(1, "必填"),
  sn: z.string().min(1, "必填"),
  assetTag: z.string().min(1, "必填"),
  deviceType: z.enum(["switch", "router", "firewall", "load_balancer"]),
  manufacturer: z.enum(["Cisco", "Huawei", "H3C", "Arista", "Juniper", "Ruijie", "Other"]),
  model: z.string().min(1, "必填"),
  firmwareVersion: z.string().optional(),
  mgmtIp: z.string().min(1, "必填"),
  mgmtProtocol: z.enum(["ssh", "snmp", "telnet"]),
  mgmtPort: z.coerce.number().int().min(1).max(65535),
  snmpCommunity: z.string().optional(),
  sshUsername: z.string().optional(),
  sshPassword: z.string().optional(),
  bizIp: z.string().optional(),
  vlan: z.string().optional(),
  portCount: z.coerce.number().int().min(0),
  idc: z.string().min(1, "必填"),
  rack: z.string().min(1, "必填"),
  uPosition: z.string().min(1, "必填"),
  status: z.enum(["online", "offline", "maintenance", "retired"]),
  owner: z.string().optional(),
  purchaseDate: z.string().optional(),
  warrantyEnd: z.string().optional(),
  tags: z.string().optional(),
  remark: z.string().optional(),
});

export type NetworkDeviceFormData = z.infer<typeof schema>;

interface Props {
  open: boolean;
  initial?: NetworkDevice | null;
  onClose: () => void;
  onSubmit: (data: Omit<NetworkDevice, "id" | "createdAt" | "updatedAt">) => Promise<void> | void;
}

const EMPTY: NetworkDeviceFormData = {
  hostname: "",
  sn: "",
  assetTag: "",
  deviceType: "switch",
  manufacturer: "Cisco",
  model: "",
  firmwareVersion: "",
  mgmtIp: "",
  mgmtProtocol: "ssh",
  mgmtPort: 22,
  snmpCommunity: "",
  sshUsername: "",
  sshPassword: "",
  bizIp: "",
  vlan: "",
  portCount: 0,
  idc: "",
  rack: "",
  uPosition: "",
  status: "online",
  owner: "",
  purchaseDate: "",
  warrantyEnd: "",
  tags: "",
  remark: "",
};

export function NetworkDeviceForm({ open, initial, onClose, onSubmit }: Props) {
  const form = useForm<NetworkDeviceFormData>({
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
          deviceType: initial.deviceType,
          manufacturer: initial.manufacturer,
          model: initial.model,
          firmwareVersion: initial.firmwareVersion ?? "",
          mgmtIp: initial.mgmtIp,
          mgmtProtocol: initial.mgmtProtocol,
          mgmtPort: initial.mgmtPort,
          snmpCommunity: initial.snmpCommunity ?? "",
          sshUsername: initial.sshUsername ?? "",
          sshPassword: "",
          bizIp: initial.bizIp ?? "",
          vlan: initial.vlan ?? "",
          portCount: initial.portCount,
          idc: initial.idc,
          rack: initial.rack,
          uPosition: initial.uPosition,
          status: initial.status,
          owner: initial.owner ?? "",
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
    const sshPassword = values.sshPassword?.trim() ? values.sshPassword : undefined;
    await onSubmit({
      hostname: values.hostname,
      sn: values.sn,
      assetTag: values.assetTag,
      deviceType: values.deviceType,
      manufacturer: values.manufacturer,
      model: values.model,
      firmwareVersion: values.firmwareVersion ?? "",
      cpuModel: initial?.cpuModel ?? "",
      cpuCount: initial?.cpuCount ?? 1,
      memoryGB: initial?.memoryGB ?? 0,
      flashGB: initial?.flashGB ?? 0,
      mgmtIp: values.mgmtIp,
      mgmtProtocol: values.mgmtProtocol,
      mgmtPort: values.mgmtPort,
      snmpCommunity: values.snmpCommunity ?? "",
      sshUsername: values.sshUsername ?? "",
      sshPassword,
      bizIp: values.bizIp ?? "",
      vlan: values.vlan ?? "",
      portCount: values.portCount,
      portSpec: initial?.portSpec ?? [],
      idc: values.idc,
      rack: values.rack,
      uPosition: values.uPosition,
      status: values.status,
      owner: values.owner ?? "",
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
          <DialogTitle>{initial ? "编辑网络设备" : "新增网络设备"}</DialogTitle>
          <DialogDescription>填写网络设备基本信息、管理接入参数与机房位置。</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="设备名" error={form.formState.errors.hostname?.message}>
            <Input {...form.register("hostname")} placeholder="bj-core-sw-01" />
          </Field>
          <Field label="序列号 SN" error={form.formState.errors.sn?.message}>
            <Input {...form.register("sn")} />
          </Field>
          <Field label="资产编号" error={form.formState.errors.assetTag?.message}>
            <Input {...form.register("assetTag")} />
          </Field>
          <Field label="设备类型">
            <Select value={form.watch("deviceType")} onValueChange={(v) => form.setValue("deviceType", v as NetworkDeviceFormData["deviceType"])}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="switch">交换机</SelectItem>
                <SelectItem value="router">路由器</SelectItem>
                <SelectItem value="firewall">防火墙</SelectItem>
                <SelectItem value="load_balancer">负载均衡</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="厂商">
            <Select value={form.watch("manufacturer")} onValueChange={(v) => form.setValue("manufacturer", v as NetworkDeviceFormData["manufacturer"])}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {(["Cisco", "Huawei", "H3C", "Arista", "Juniper", "Ruijie", "Other"] as const).map((m) => (
                  <SelectItem key={m} value={m}>{m}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="型号" error={form.formState.errors.model?.message}>
            <Input {...form.register("model")} />
          </Field>
          <Field label="固件版本">
            <Input {...form.register("firmwareVersion")} />
          </Field>
          <Field label="端口数量">
            <Input type="number" min={0} {...form.register("portCount")} />
          </Field>
          <Field label="管理 IP" error={form.formState.errors.mgmtIp?.message}>
            <Input {...form.register("mgmtIp")} />
          </Field>
          <Field label="管理协议">
            <Select value={form.watch("mgmtProtocol")} onValueChange={(v) => form.setValue("mgmtProtocol", v as "ssh" | "snmp" | "telnet")}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="ssh">SSH</SelectItem>
                <SelectItem value="snmp">SNMP</SelectItem>
                <SelectItem value="telnet">Telnet</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="管理端口">
            <Input type="number" min={1} max={65535} {...form.register("mgmtPort")} />
          </Field>
          <Field label="SNMP 团体字">
            <Input {...form.register("snmpCommunity")} />
          </Field>
          <Field label="SSH 用户名">
            <Input {...form.register("sshUsername")} />
          </Field>
          <Field
            label={initial ? "SSH 密码（留空保持不变）" : "SSH 密码"}
            className="sm:col-span-2"
          >
            <Input
              type="password"
              autoComplete="new-password"
              placeholder={initial ? "如需修改请输入新密码，否则保持空白" : "用于 SSH 登录"}
              {...form.register("sshPassword")}
            />
          </Field>
          <Field label="业务 IP">
            <Input {...form.register("bizIp")} />
          </Field>
          <Field label="VLAN">
            <Input {...form.register("vlan")} />
          </Field>
          <Field label="IDC" error={form.formState.errors.idc?.message}>
            <Input {...form.register("idc")} placeholder="BJ-IDC-A" />
          </Field>
          <Field label="机柜" error={form.formState.errors.rack?.message}>
            <Input {...form.register("rack")} placeholder="A03" />
          </Field>
          <Field label="U 位" error={form.formState.errors.uPosition?.message}>
            <Input {...form.register("uPosition")} placeholder="U24-U25" />
          </Field>
          <Field label="状态">
            <Select value={form.watch("status")} onValueChange={(v) => form.setValue("status", v as NetworkDeviceFormData["status"])}>
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
            <Input {...form.register("tags")} placeholder="core,prod" />
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
