import * as XLSX from "xlsx";
import type { Server, ServerStatus, Manufacturer, BmcProtocol } from "@/types/cmdb";

// ---------- constants ----------

/** Column headers (display) → field key mapping */
export const SERVER_COLUMNS = [
  { key: "hostname", label: "服务器名", required: true, example: "srv-bj-prod-01" },
  { key: "sn", label: "序列号(SN)", required: true, example: "ABC123456" },
  { key: "assetTag", label: "资产编号", required: true, example: "AST-2024-001" },
  { key: "manufacturer", label: "厂商", required: true, example: "Dell" },
  { key: "model", label: "型号", required: true, example: "PowerEdge R750" },
  { key: "cpuModel", label: "CPU型号", required: true, example: "Intel Xeon Gold 6330" },
  { key: "cpuCount", label: "CPU数量", required: false, example: "2" },
  { key: "memoryGB", label: "内存(GB)", required: false, example: "256" },
  { key: "idc", label: "机房", required: true, example: "北京-亦庄" },
  { key: "rack", label: "机柜", required: true, example: "A-12" },
  { key: "uPosition", label: "U位", required: true, example: "18-20" },
  { key: "mgmtIp", label: "管理IP", required: true, example: "10.0.1.100" },
  { key: "bizIp", label: "业务IP", required: true, example: "10.0.2.100" },
  { key: "bmcProtocol", label: "BMC协议", required: false, example: "redfish" },
  { key: "bmcUser", label: "BMC用户", required: false, example: "admin" },
  { key: "bmcPassword", label: "BMC密码", required: false, example: "" },
  { key: "status", label: "状态", required: false, example: "online" },
  { key: "owner", label: "负责人", required: false, example: "张三" },
  { key: "purchaseDate", label: "采购日期", required: false, example: "2024-01-15" },
  { key: "warrantyEnd", label: "保修截止", required: false, example: "2027-01-15" },
  { key: "tags", label: "标签", required: false, example: "生产;核心" },
  { key: "remark", label: "备注", required: false, example: "" },
];

const VALID_STATUSES: ServerStatus[] = ["online", "offline", "maintenance", "retired"];
const VALID_MANUFACTURERS: Manufacturer[] = [
  "Dell", "HPE", "Lenovo", "Inspur", "Supermicro", "Huawei", "XFusion", "Other",
];

/** Display names that users might fill in from the dropdown → internal value */
const MANUFACTURER_ALIASES: Record<string, Manufacturer> = {
  "超聚变": "XFusion",
};

function normalizeManufacturer(raw: string): string {
  const trimmed = raw.trim();
  return MANUFACTURER_ALIASES[trimmed] ?? trimmed;
}
const VALID_BMC_PROTOCOLS: BmcProtocol[] = ["redfish", "ipmi"];

// ---------- export ----------

export function exportToCsv(servers: Server[]): Blob {
  const headers = SERVER_COLUMNS.map((c) => c.label);
  const rows = servers.map((s) =>
    SERVER_COLUMNS.map((c) => pickExportValue(s, c.key))
  );
  const csv = [headers, ...rows]
    .map((row) => row.map(escapeCsvField).join(","))
    .join("\n");
  return new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
}

export function exportToExcel(servers: Server[]): Blob {
  const headers = SERVER_COLUMNS.map((c) => c.label);
  const rows = servers.map((s) =>
    SERVER_COLUMNS.map((c) => pickExportValue(s, c.key))
  );
  const ws = XLSX.utils.aoa_to_sheet([headers, ...rows]);
  ws["!cols"] = SERVER_COLUMNS.map((c) => ({
    wch: Math.max(c.label.length, 12),
  }));
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "服务器资产");
  const buf = XLSX.write(wb, { type: "array", bookType: "xlsx" });
  return new Blob([buf], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

function pickExportValue(s: Server, key: string): string {
  switch (key) {
    case "hostname": return s.hostname;
    case "sn": return s.sn;
    case "assetTag": return s.assetTag;
    case "manufacturer": return s.manufacturer;
    case "model": return s.model;
    case "cpuModel": return s.cpuModel;
    case "cpuCount": return String(s.cpuCount);
    case "memoryGB": return String(s.memoryGB);
    case "idc": return s.location.idc;
    case "rack": return s.location.rack;
    case "uPosition": return s.location.uPosition;
    case "mgmtIp": return s.mgmtIp;
    case "bizIp": return s.bizIp;
    case "bmcProtocol": return s.bmcProtocol;
    case "bmcUser": return s.bmcUser;
    case "bmcPassword": return "";
    case "status": return s.status;
    case "owner": return s.owner;
    case "purchaseDate": return s.purchaseDate;
    case "warrantyEnd": return s.warrantyEnd;
    case "tags": return s.tags.join(";");
    case "remark": return s.remark ?? "";
    default: return "";
  }
}

function escapeCsvField(v: string): string {
  if (v.includes(",") || v.includes('"') || v.includes("\n")) {
    return `"${v.replace(/"/g, '""')}"`;
  }
  return v;
}

// ---------- template ----------

export function generateTemplate(format: "csv" | "xlsx"): Blob {
  const headers = SERVER_COLUMNS.map((c) => c.label);
  const examples = [
    SERVER_COLUMNS.map((c) => c.example),
    SERVER_COLUMNS.map((c) => {
      if (c.key === "hostname") return "srv-sh-prod-01";
      if (c.key === "sn") return "XYZ789012";
      if (c.key === "assetTag") return "AST-2024-002";
      if (c.key === "manufacturer") return "HPE";
      if (c.key === "model") return "ProLiant DL380 Gen11";
      if (c.key === "cpuModel") return "Intel Xeon Gold 6426Y";
      if (c.key === "idc") return "上海-金桥";
      if (c.key === "rack") return "B-05";
      if (c.key === "uPosition") return "10-12";
      if (c.key === "mgmtIp") return "10.1.1.200";
      if (c.key === "bizIp") return "10.2.1.200";
      if (c.key === "status") return "maintenance";
      if (c.key === "owner") return "李四";
      return c.example;
    }),
  ];

  if (format === "csv") {
    const csv = [headers, ...examples]
      .map((row) => row.map(escapeCsvField).join(","))
      .join("\n");
    return new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
  }

  const ws = XLSX.utils.aoa_to_sheet([headers, ...examples]);
  ws["!cols"] = SERVER_COLUMNS.map((c) => ({
    wch: Math.max(c.label.length, 14),
  }));
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "模板");
  const buf = XLSX.write(wb, { type: "array", bookType: "xlsx" });
  return new Blob([buf], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

/** Convert an Excel date serial number to YYYY-MM-DD string. */
function excelSerialToDate(serial: number): string | null {
  // Excel serial 1 = 1900-01-01. Range ~30k (1982) – ~55k (2050).
  if (serial < 30000 || serial > 55000) return null;
  // 25569 = days from 1900-01-01 to 1970-01-01 + Excel leap-year bug offset
  const d = new Date(Math.round((serial - 25569) * 86400000));
  if (isNaN(d.getTime())) return null;
  return d.toISOString().slice(0, 10);
}

/** Columns that may contain Excel date serial numbers. */
const DATE_KEYS = new Set(["purchaseDate", "warrantyEnd"]);

// ---------- import ----------

export interface ImportRow {
  rowIndex: number;
  data: Record<string, string>;
  errors: string[];
}

export interface ImportResult {
  rows: ImportRow[];
  validCount: number;
  errorCount: number;
}

/** Detect file type from File object */
function isCsvFile(file: File): boolean {
  return file.name.toLowerCase().endsWith(".csv");
}

/** Parse a file (CSV or Excel) and return validated rows. */
export function parseImportFile(file: File): Promise<ImportResult> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = (e) => {
      try {
        const isCsv = isCsvFile(file);
        let wb: XLSX.WorkBook;

        if (isCsv) {
          // CSV: read as text for proper encoding handling (BOM, UTF-8)
          const text = e.target!.result as string;
          wb = XLSX.read(text, { type: "string", raw: true });
        } else {
          // XLSX/XLS: read as binary array
          const data = new Uint8Array(e.target!.result as ArrayBuffer);
          wb = XLSX.read(data, { type: "array" });
        }

        const sheet = wb.Sheets[wb.SheetNames[0]];
        if (!sheet) {
          reject(new Error("文件中未找到有效的工作表"));
          return;
        }

        const json = XLSX.utils.sheet_to_json<string[]>(sheet, { header: 1 });
        if (json.length < 1) {
          resolve({ rows: [], validCount: 0, errorCount: 0 });
          return;
        }

        const headerRow = json[0] as string[];
        const labelToKey = new Map<string, string>();
        for (const col of SERVER_COLUMNS) {
          labelToKey.set(col.label, col.key);
        }

        const rows: ImportRow[] = [];
        for (let i = 1; i < json.length; i++) {
          const raw = json[i] as string[] | undefined;
          if (!raw || raw.every((c) => !c)) continue;
          const data: Record<string, string> = {};
          for (let j = 0; j < headerRow.length; j++) {
            const key = labelToKey.get(String(headerRow[j] ?? "").trim());
            if (key) {
              const cell = raw[j];
              if (DATE_KEYS.has(key) && typeof cell === "number") {
                data[key] = excelSerialToDate(cell) ?? String(cell ?? "").trim();
              } else {
                data[key] = String(cell ?? "").trim();
              }
            }
          }
          const errors = validateImportRow(data);
          rows.push({ rowIndex: i + 1, data, errors });
        }

        const validCount = rows.filter((r) => r.errors.length === 0).length;
        resolve({ rows, validCount, errorCount: rows.length - validCount });
      } catch (err) {
        const msg = err instanceof Error ? err.message : "文件解析失败";
        console.error("parseImportFile error:", err);
        reject(new Error(msg));
      }
    };

    reader.onerror = () => reject(new Error("文件读取失败，请检查文件是否损坏"));

    if (isCsvFile(file)) {
      reader.readAsText(file, "UTF-8");
    } else {
      reader.readAsArrayBuffer(file);
    }
  });
}

function validateImportRow(data: Record<string, string>): string[] {
  const errors: string[] = [];

  const required = SERVER_COLUMNS.filter((c) => c.required);
  for (const col of required) {
    if (!data[col.key] || data[col.key].trim() === "") {
      errors.push(`"${col.label}" 为必填项`);
    }
  }

  if (!errors.length) {
    const mfr = data.manufacturer ? normalizeManufacturer(data.manufacturer) : "";
    data.manufacturer = mfr;
    if (mfr && !VALID_MANUFACTURERS.includes(mfr as Manufacturer)) {
      errors.push(`厂商 "${data.manufacturer}" 无效，可选: ${VALID_MANUFACTURERS.join(", ")}`);
    }
    if (data.status && !VALID_STATUSES.includes(data.status as ServerStatus)) {
      errors.push(`状态 "${data.status}" 无效，可选: ${VALID_STATUSES.join(", ")}`);
    }
    if (data.bmcProtocol && !VALID_BMC_PROTOCOLS.includes(data.bmcProtocol as BmcProtocol)) {
      errors.push(`BMC协议 "${data.bmcProtocol}" 无效，可选: redfish, ipmi`);
    }
    if (data.cpuCount && isNaN(Number(data.cpuCount))) {
      errors.push(`CPU数量 "${data.cpuCount}" 不是有效数字`);
    }
    if (data.memoryGB && isNaN(Number(data.memoryGB))) {
      errors.push(`内存 "${data.memoryGB}" 不是有效数字`);
    }
    if (data.purchaseDate && !/^\d{4}-\d{2}-\d{2}$/.test(data.purchaseDate)) {
      errors.push(`采购日期 "${data.purchaseDate}" 格式无效，请使用 YYYY-MM-DD`);
    }
    if (data.warrantyEnd && !/^\d{4}-\d{2}-\d{2}$/.test(data.warrantyEnd)) {
      errors.push(`保修截止 "${data.warrantyEnd}" 格式无效，请使用 YYYY-MM-DD`);
    }
    if (data.mgmtIp && !/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(data.mgmtIp)) {
      errors.push(`管理IP "${data.mgmtIp}" 格式无效`);
    }
    if (data.bizIp && !/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(data.bizIp)) {
      errors.push(`业务IP "${data.bizIp}" 格式无效`);
    }
  }

  return errors;
}

export function importRowToPayload(
  data: Record<string, string>,
): Omit<Server, "id" | "createdAt" | "updatedAt"> {
  return {
    hostname: data.hostname,
    sn: data.sn,
    assetTag: data.assetTag,
    manufacturer: (normalizeManufacturer(data.manufacturer) || "Other") as Manufacturer,
    model: data.model,
    cpuModel: data.cpuModel,
    cpuCount: parseInt(data.cpuCount) || 1,
    memoryGB: parseInt(data.memoryGB) || 0,
    diskCount: 0,
    location: {
      idc: data.idc,
      rack: data.rack,
      uPosition: data.uPosition,
    },
    mgmtIp: data.mgmtIp,
    bizIp: data.bizIp,
    bmcProtocol: (data.bmcProtocol || "redfish") as BmcProtocol,
    bmcUser: data.bmcUser || "admin",
    bmcPassword: data.bmcPassword || undefined,
    status: (data.status || "online") as ServerStatus,
    owner: data.owner || "",
    purchaseDate: data.purchaseDate || undefined,
    warrantyEnd: data.warrantyEnd || undefined,
    tags: data.tags ? data.tags.split(/[;,]/).map((t) => t.trim()).filter(Boolean) : [],
    remark: data.remark || undefined,
  };
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── Network Device import / export ──────────────────────────────

import type { NetworkDevice, NetworkDeviceType, MgmtProtocol, Workstation, WorkstationManufacturer, OperatingSystem } from "@/types/cmdb";

const NETWORK_DEVICE_COLUMNS = [
  { key: "hostname", label: "设备名", required: true, example: "bj-core-sw-01" },
  { key: "sn", label: "序列号(SN)", required: true, example: "NDEV001" },
  { key: "assetTag", label: "资产编号", required: true, example: "AST-ND-001" },
  { key: "deviceType", label: "设备类型", required: true, example: "switch" },
  { key: "manufacturer", label: "厂商", required: true, example: "Cisco" },
  { key: "model", label: "型号", required: true, example: "Catalyst 9300" },
  { key: "firmwareVersion", label: "固件版本", required: false, example: "17.9.3" },
  { key: "mgmtIp", label: "管理IP", required: true, example: "10.0.1.1" },
  { key: "mgmtProtocol", label: "管理协议", required: false, example: "ssh" },
  { key: "mgmtPort", label: "管理端口", required: false, example: "22" },
  { key: "snmpCommunity", label: "SNMP团体字", required: false, example: "public" },
  { key: "sshUsername", label: "SSH用户名", required: false, example: "admin" },
  { key: "sshPassword", label: "SSH密码", required: false, example: "" },
  { key: "bizIp", label: "业务IP", required: false, example: "10.0.2.1" },
  { key: "vlan", label: "VLAN", required: false, example: "100" },
  { key: "portCount", label: "端口数量", required: false, example: "48" },
  { key: "idc", label: "机房", required: true, example: "北京-亦庄" },
  { key: "rack", label: "机柜", required: true, example: "A-01" },
  { key: "uPosition", label: "U位", required: true, example: "24-25" },
  { key: "status", label: "状态", required: false, example: "online" },
  { key: "owner", label: "负责人", required: false, example: "张三" },
  { key: "purchaseDate", label: "采购日期", required: false, example: "2024-01-15" },
  { key: "warrantyEnd", label: "保修截止", required: false, example: "2027-01-15" },
  { key: "tags", label: "标签", required: false, example: "核心;生产" },
  { key: "remark", label: "备注", required: false, example: "" },
];

const VALID_DEVICE_TYPES: NetworkDeviceType[] = ["switch", "router", "firewall", "load_balancer"];
const VALID_MGMT_PROTOCOLS: MgmtProtocol[] = ["ssh", "snmp", "telnet"];

function pickNdevExportValue(d: NetworkDevice, key: string): string {
  switch (key) {
    case "hostname": return d.hostname;
    case "sn": return d.sn;
    case "assetTag": return d.assetTag;
    case "deviceType": return d.deviceType;
    case "manufacturer": return d.manufacturer;
    case "model": return d.model;
    case "firmwareVersion": return d.firmwareVersion ?? "";
    case "mgmtIp": return d.mgmtIp;
    case "mgmtProtocol": return d.mgmtProtocol;
    case "mgmtPort": return String(d.mgmtPort);
    case "snmpCommunity": return d.snmpCommunity ?? "";
    case "sshUsername": return d.sshUsername ?? "";
    case "bizIp": return d.bizIp ?? "";
    case "vlan": return d.vlan ?? "";
    case "portCount": return String(d.portCount);
    case "idc": return d.idc;
    case "rack": return d.rack;
    case "uPosition": return d.uPosition;
    case "status": return d.status;
    case "owner": return d.owner ?? "";
    case "purchaseDate": return d.purchaseDate;
    case "warrantyEnd": return d.warrantyEnd;
    case "tags": return (d.tags ?? []).join(";");
    case "remark": return d.remark ?? "";
    default: return "";
  }
}

export function exportNetworkDevicesToCsv(devices: NetworkDevice[]): Blob {
  const headers = NETWORK_DEVICE_COLUMNS.map((c) => c.label);
  const rows = devices.map((d) =>
    NETWORK_DEVICE_COLUMNS.map((c) => pickNdevExportValue(d, c.key))
  );
  const csv = [headers, ...rows]
    .map((row) => row.map(escapeCsvField).join(","))
    .join("\n");
  return new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
}

export function exportNetworkDevicesToExcel(devices: NetworkDevice[]): Blob {
  const headers = NETWORK_DEVICE_COLUMNS.map((c) => c.label);
  const rows = devices.map((d) =>
    NETWORK_DEVICE_COLUMNS.map((c) => pickNdevExportValue(d, c.key))
  );
  const ws = XLSX.utils.aoa_to_sheet([headers, ...rows]);
  ws["!cols"] = NETWORK_DEVICE_COLUMNS.map((c) => ({
    wch: Math.max(c.label.length, 12),
  }));
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "网络设备");
  const buf = XLSX.write(wb, { type: "array", bookType: "xlsx" });
  return new Blob([buf], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

export function generateNetworkDeviceTemplate(format: "csv" | "xlsx"): Blob {
  const headers = NETWORK_DEVICE_COLUMNS.map((c) => c.label);
  const examples = [
    NETWORK_DEVICE_COLUMNS.map((c) => c.example),
    NETWORK_DEVICE_COLUMNS.map((c) => {
      if (c.key === "hostname") return "sh-core-sw-01";
      if (c.key === "sn") return "NDEV002";
      if (c.key === "assetTag") return "AST-ND-002";
      if (c.key === "deviceType") return "router";
      if (c.key === "manufacturer") return "Huawei";
      if (c.key === "model") return "AR6300";
      if (c.key === "mgmtIp") return "10.1.1.1";
      if (c.key === "idc") return "上海-金桥";
      if (c.key === "rack") return "B-01";
      if (c.key === "uPosition") return "30-31";
      return c.example;
    }),
  ];

  if (format === "csv") {
    const csv = [headers, ...examples]
      .map((row) => row.map(escapeCsvField).join(","))
      .join("\n");
    return new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
  }

  const ws = XLSX.utils.aoa_to_sheet([headers, ...examples]);
  ws["!cols"] = NETWORK_DEVICE_COLUMNS.map((c) => ({
    wch: Math.max(c.label.length, 14),
  }));
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "模板");
  const buf = XLSX.write(wb, { type: "array", bookType: "xlsx" });
  return new Blob([buf], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

export function parseNetworkDeviceImportFile(file: File): Promise<ImportResult> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = (e) => {
      try {
        const isCsv = file.name.toLowerCase().endsWith(".csv");
        let wb: XLSX.WorkBook;

        if (isCsv) {
          const text = e.target!.result as string;
          wb = XLSX.read(text, { type: "string", raw: true });
        } else {
          const data = new Uint8Array(e.target!.result as ArrayBuffer);
          wb = XLSX.read(data, { type: "array" });
        }

        const sheet = wb.Sheets[wb.SheetNames[0]];
        if (!sheet) {
          reject(new Error("文件中未找到有效的工作表"));
          return;
        }

        const json = XLSX.utils.sheet_to_json<string[]>(sheet, { header: 1 });
        if (json.length < 1) {
          resolve({ rows: [], validCount: 0, errorCount: 0 });
          return;
        }

        const headerRow = json[0] as string[];
        const labelToKey = new Map<string, string>();
        for (const col of NETWORK_DEVICE_COLUMNS) {
          labelToKey.set(col.label, col.key);
        }

        const rows: ImportRow[] = [];
        for (let i = 1; i < json.length; i++) {
          const raw = json[i] as string[] | undefined;
          if (!raw || raw.every((c) => !c)) continue;
          const data: Record<string, string> = {};
          for (let j = 0; j < headerRow.length; j++) {
            const key = labelToKey.get(String(headerRow[j] ?? "").trim());
            if (key) {
              const cell = raw[j];
              data[key] = String(cell ?? "").trim();
            }
          }
          const errors = validateNetworkDeviceImportRow(data);
          rows.push({ rowIndex: i + 1, data, errors });
        }

        const validCount = rows.filter((r) => r.errors.length === 0).length;
        resolve({ rows, validCount, errorCount: rows.length - validCount });
      } catch (err) {
        const msg = err instanceof Error ? err.message : "文件解析失败";
        reject(new Error(msg));
      }
    };

    reader.onerror = () => reject(new Error("文件读取失败，请检查文件是否损坏"));

    if (file.name.toLowerCase().endsWith(".csv")) {
      reader.readAsText(file, "UTF-8");
    } else {
      reader.readAsArrayBuffer(file);
    }
  });
}

function validateNetworkDeviceImportRow(data: Record<string, string>): string[] {
  const errors: string[] = [];

  const required = NETWORK_DEVICE_COLUMNS.filter((c) => c.required);
  for (const col of required) {
    if (!data[col.key] || data[col.key].trim() === "") {
      errors.push(`"${col.label}" 为必填项`);
    }
  }

  if (!errors.length) {
    if (data.deviceType && !VALID_DEVICE_TYPES.includes(data.deviceType as NetworkDeviceType)) {
      errors.push(`设备类型 "${data.deviceType}" 无效，可选: ${VALID_DEVICE_TYPES.join(", ")}`);
    }
    if (data.mgmtProtocol && !VALID_MGMT_PROTOCOLS.includes(data.mgmtProtocol as MgmtProtocol)) {
      errors.push(`管理协议 "${data.mgmtProtocol}" 无效，可选: ssh, snmp, telnet`);
    }
    if (data.mgmtPort && isNaN(Number(data.mgmtPort))) {
      errors.push(`管理端口 "${data.mgmtPort}" 不是有效数字`);
    }
    if (data.portCount && isNaN(Number(data.portCount))) {
      errors.push(`端口数量 "${data.portCount}" 不是有效数字`);
    }
    if (data.purchaseDate && !/^\d{4}-\d{2}-\d{2}$/.test(data.purchaseDate)) {
      errors.push(`采购日期 "${data.purchaseDate}" 格式无效，请使用 YYYY-MM-DD`);
    }
    if (data.warrantyEnd && !/^\d{4}-\d{2}-\d{2}$/.test(data.warrantyEnd)) {
      errors.push(`保修截止 "${data.warrantyEnd}" 格式无效，请使用 YYYY-MM-DD`);
    }
    if (data.mgmtIp && !/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(data.mgmtIp)) {
      errors.push(`管理IP "${data.mgmtIp}" 格式无效`);
    }
    if (data.bizIp && !/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(data.bizIp)) {
      errors.push(`业务IP "${data.bizIp}" 格式无效`);
    }
  }

  return errors;
}

export function networkDeviceImportRowToPayload(
  data: Record<string, string>,
): Omit<NetworkDevice, "id" | "createdAt" | "updatedAt"> {
  return {
    hostname: data.hostname,
    sn: data.sn,
    assetTag: data.assetTag,
    deviceType: (data.deviceType || "switch") as NetworkDeviceType,
    manufacturer: data.manufacturer as NetworkDevice["manufacturer"],
    model: data.model,
    firmwareVersion: data.firmwareVersion ?? "",
    cpuModel: "",
    cpuCount: 1,
    memoryGB: 0,
    flashGB: 0,
    mgmtIp: data.mgmtIp,
    mgmtProtocol: (data.mgmtProtocol || "ssh") as MgmtProtocol,
    mgmtPort: parseInt(data.mgmtPort) || 22,
    snmpCommunity: data.snmpCommunity ?? "",
    sshUsername: data.sshUsername ?? "",
    sshPassword: data.sshPassword || undefined,
    bizIp: data.bizIp ?? "",
    vlan: data.vlan ?? "",
    portCount: parseInt(data.portCount) || 0,
    portSpec: [],
    idc: data.idc,
    rack: data.rack,
    uPosition: data.uPosition,
    status: (data.status || "online") as NetworkDevice["status"],
    owner: data.owner ?? "",
    purchaseDate: data.purchaseDate ?? "",
    warrantyEnd: data.warrantyEnd ?? "",
    tags: data.tags ? data.tags.split(/[;,]/).map((t) => t.trim()).filter(Boolean) : [],
    remark: data.remark,
  };
}

// ── Workstation import / export ─────────────────────────────────

const WORKSTATION_COLUMNS = [
  { key: "hostname", label: "计算机名", required: true, example: "BJ-FIN-001" },
  { key: "sn", label: "序列号(SN)", required: true, example: "WKS001" },
  { key: "assetTag", label: "资产编号", required: true, example: "AST-WKS-001" },
  { key: "manufacturer", label: "厂商", required: true, example: "Dell" },
  { key: "model", label: "型号", required: true, example: "OptiPlex 7080" },
  { key: "cpuModel", label: "CPU型号", required: true, example: "Intel Core i7-10700" },
  { key: "cpuCount", label: "CPU核心数", required: false, example: "8" },
  { key: "memoryGB", label: "内存(GB)", required: false, example: "16" },
  { key: "diskType", label: "硬盘类型", required: false, example: "SSD" },
  { key: "diskCapacityGB", label: "硬盘容量(GB)", required: false, example: "512" },
  { key: "macAddress", label: "MAC地址", required: false, example: "AA:BB:CC:DD:EE:FF" },
  { key: "os", label: "操作系统", required: true, example: "Windows 11" },
  { key: "osVersion", label: "操作系统版本", required: false, example: "22H2" },
  { key: "bizIp", label: "IP地址", required: false, example: "192.168.1.100" },
  { key: "userName", label: "使用人", required: false, example: "张三" },
  { key: "department", label: "部门", required: false, example: "财务部" },
  { key: "officeBuilding", label: "办公楼", required: false, example: "A座" },
  { key: "floor", label: "楼层", required: false, example: "5F" },
  { key: "seat", label: "工位", required: false, example: "A-12" },
  { key: "status", label: "状态", required: false, example: "online" },
  { key: "purchaseDate", label: "采购日期", required: false, example: "2024-01-15" },
  { key: "warrantyEnd", label: "保修截止", required: false, example: "2027-01-15" },
  { key: "tags", label: "标签", required: false, example: "财务;办公" },
  { key: "remark", label: "备注", required: false, example: "" },
];

const VALID_WORKSTATION_MANUFACTURERS: WorkstationManufacturer[] = [
  "Dell", "HP", "Lenovo", "Apple", "Huawei", "ASUS", "Acer", "Microsoft", "Other",
];

const VALID_OS: OperatingSystem[] = [
  "Windows 10", "Windows 11", "macOS", "Ubuntu", "CentOS", "Other",
];

const VALID_DISK_TYPES = ["SSD", "HDD", "NVMe", "混合"];

const VALID_WORKSTATION_STATUSES: ServerStatus[] = ["online", "offline", "maintenance", "retired"];

function pickWorkstationExportValue(w: Workstation, key: string): string {
  switch (key) {
    case "hostname": return w.hostname;
    case "sn": return w.sn;
    case "assetTag": return w.assetTag;
    case "manufacturer": return w.manufacturer;
    case "model": return w.model;
    case "cpuModel": return w.cpuModel;
    case "cpuCount": return String(w.cpuCount);
    case "memoryGB": return String(w.memoryGB);
    case "diskType": return w.diskType ?? "";
    case "diskCapacityGB": return String(w.diskCapacityGB);
    case "macAddress": return w.macAddress ?? "";
    case "os": return w.os;
    case "osVersion": return w.osVersion ?? "";
    case "bizIp": return w.bizIp ?? "";
    case "userName": return w.userName ?? "";
    case "department": return w.department ?? "";
    case "officeBuilding": return w.officeBuilding ?? "";
    case "floor": return w.floor ?? "";
    case "seat": return w.seat ?? "";
    case "status": return w.status;
    case "purchaseDate": return w.purchaseDate ?? "";
    case "warrantyEnd": return w.warrantyEnd ?? "";
    case "tags": return (w.tags ?? []).join(";");
    case "remark": return w.remark ?? "";
    default: return "";
  }
}

export function exportWorkstationsToCsv(workstations: Workstation[]): Blob {
  const headers = WORKSTATION_COLUMNS.map((c) => c.label);
  const rows = workstations.map((w) =>
    WORKSTATION_COLUMNS.map((c) => pickWorkstationExportValue(w, c.key))
  );
  const csv = [headers, ...rows]
    .map((row) => row.map(escapeCsvField).join(","))
    .join("\n");
  return new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
}

export function exportWorkstationsToExcel(workstations: Workstation[]): Blob {
  const headers = WORKSTATION_COLUMNS.map((c) => c.label);
  const rows = workstations.map((w) =>
    WORKSTATION_COLUMNS.map((c) => pickWorkstationExportValue(w, c.key))
  );
  const ws = XLSX.utils.aoa_to_sheet([headers, ...rows]);
  ws["!cols"] = WORKSTATION_COLUMNS.map((c) => ({
    wch: Math.max(c.label.length, 12),
  }));
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "终端PC");
  const buf = XLSX.write(wb, { type: "array", bookType: "xlsx" });
  return new Blob([buf], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

export function generateWorkstationTemplate(format: "csv" | "xlsx"): Blob {
  const headers = WORKSTATION_COLUMNS.map((c) => c.label);
  const examples = [
    WORKSTATION_COLUMNS.map((c) => c.example),
    WORKSTATION_COLUMNS.map((c) => {
      if (c.key === "hostname") return "SH-MKT-001";
      if (c.key === "sn") return "WKS002";
      if (c.key === "assetTag") return "AST-WKS-002";
      if (c.key === "manufacturer") return "Lenovo";
      if (c.key === "model") return "ThinkCentre M80q";
      if (c.key === "cpuModel") return "Intel Core i5-12400";
      if (c.key === "cpuCount") return "6";
      if (c.key === "memoryGB") return "8";
      if (c.key === "diskType") return "NVMe";
      if (c.key === "diskCapacityGB") return "256";
      if (c.key === "macAddress") return "11:22:33:44:55:66";
      if (c.key === "os") return "Windows 10";
      if (c.key === "osVersion") return "21H2";
      if (c.key === "bizIp") return "192.168.2.50";
      if (c.key === "userName") return "李四";
      if (c.key === "department") return "市场部";
      if (c.key === "officeBuilding") return "B座";
      if (c.key === "floor") return "3F";
      if (c.key === "seat") return "B-08";
      return c.example;
    }),
  ];

  if (format === "csv") {
    const csv = [headers, ...examples]
      .map((row) => row.map(escapeCsvField).join(","))
      .join("\n");
    return new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
  }

  const ws = XLSX.utils.aoa_to_sheet([headers, ...examples]);
  ws["!cols"] = WORKSTATION_COLUMNS.map((c) => ({
    wch: Math.max(c.label.length, 14),
  }));
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "模板");
  const buf = XLSX.write(wb, { type: "array", bookType: "xlsx" });
  return new Blob([buf], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

export function parseWorkstationImportFile(file: File): Promise<ImportResult> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = (e) => {
      try {
        const isCsv = file.name.toLowerCase().endsWith(".csv");
        let wb: XLSX.WorkBook;

        if (isCsv) {
          const text = e.target!.result as string;
          wb = XLSX.read(text, { type: "string", raw: true });
        } else {
          const data = new Uint8Array(e.target!.result as ArrayBuffer);
          wb = XLSX.read(data, { type: "array" });
        }

        const sheet = wb.Sheets[wb.SheetNames[0]];
        if (!sheet) {
          reject(new Error("文件中未找到有效的工作表"));
          return;
        }

        const json = XLSX.utils.sheet_to_json<string[]>(sheet, { header: 1 });
        if (json.length < 1) {
          resolve({ rows: [], validCount: 0, errorCount: 0 });
          return;
        }

        const headerRow = json[0] as string[];
        const labelToKey = new Map<string, string>();
        for (const col of WORKSTATION_COLUMNS) {
          labelToKey.set(col.label, col.key);
        }

        const rows: ImportRow[] = [];
        for (let i = 1; i < json.length; i++) {
          const raw = json[i] as string[] | undefined;
          if (!raw || raw.every((c) => !c)) continue;
          const data: Record<string, string> = {};
          for (let j = 0; j < headerRow.length; j++) {
            const key = labelToKey.get(String(headerRow[j] ?? "").trim());
            if (key) {
              const cell = raw[j];
              data[key] = String(cell ?? "").trim();
            }
          }
          const errors = validateWorkstationImportRow(data);
          rows.push({ rowIndex: i + 1, data, errors });
        }

        const validCount = rows.filter((r) => r.errors.length === 0).length;
        resolve({ rows, validCount, errorCount: rows.length - validCount });
      } catch (err) {
        const msg = err instanceof Error ? err.message : "文件解析失败";
        reject(new Error(msg));
      }
    };

    reader.onerror = () => reject(new Error("文件读取失败，请检查文件是否损坏"));

    if (file.name.toLowerCase().endsWith(".csv")) {
      reader.readAsText(file, "UTF-8");
    } else {
      reader.readAsArrayBuffer(file);
    }
  });
}

function validateWorkstationImportRow(data: Record<string, string>): string[] {
  const errors: string[] = [];

  const required = WORKSTATION_COLUMNS.filter((c) => c.required);
  for (const col of required) {
    if (!data[col.key] || data[col.key].trim() === "") {
      errors.push(`"${col.label}" 为必填项`);
    }
  }

  if (!errors.length) {
    if (data.manufacturer && !VALID_WORKSTATION_MANUFACTURERS.includes(data.manufacturer as WorkstationManufacturer)) {
      errors.push(`厂商 "${data.manufacturer}" 无效，可选: ${VALID_WORKSTATION_MANUFACTURERS.join(", ")}`);
    }
    if (data.os && !VALID_OS.includes(data.os as OperatingSystem)) {
      errors.push(`操作系统 "${data.os}" 无效，可选: ${VALID_OS.join(", ")}`);
    }
    if (data.diskType && !VALID_DISK_TYPES.includes(data.diskType)) {
      errors.push(`硬盘类型 "${data.diskType}" 无效，可选: ${VALID_DISK_TYPES.join(", ")}`);
    }
    if (data.status && !VALID_WORKSTATION_STATUSES.includes(data.status as ServerStatus)) {
      errors.push(`状态 "${data.status}" 无效，可选: ${VALID_WORKSTATION_STATUSES.join(", ")}`);
    }
    if (data.cpuCount && isNaN(Number(data.cpuCount))) {
      errors.push(`CPU核心数 "${data.cpuCount}" 不是有效数字`);
    }
    if (data.memoryGB && isNaN(Number(data.memoryGB))) {
      errors.push(`内存 "${data.memoryGB}" 不是有效数字`);
    }
    if (data.diskCapacityGB && isNaN(Number(data.diskCapacityGB))) {
      errors.push(`硬盘容量 "${data.diskCapacityGB}" 不是有效数字`);
    }
    if (data.purchaseDate && !/^\d{4}-\d{2}-\d{2}$/.test(data.purchaseDate)) {
      errors.push(`采购日期 "${data.purchaseDate}" 格式无效，请使用 YYYY-MM-DD`);
    }
    if (data.warrantyEnd && !/^\d{4}-\d{2}-\d{2}$/.test(data.warrantyEnd)) {
      errors.push(`保修截止 "${data.warrantyEnd}" 格式无效，请使用 YYYY-MM-DD`);
    }
    if (data.bizIp && !/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(data.bizIp)) {
      errors.push(`IP地址 "${data.bizIp}" 格式无效`);
    }
    if (data.macAddress && !/^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$/.test(data.macAddress)) {
      errors.push(`MAC地址 "${data.macAddress}" 格式无效，请使用 AA:BB:CC:DD:EE:FF`);
    }
  }

  return errors;
}

export function workstationImportRowToPayload(
  data: Record<string, string>,
): Omit<Workstation, "id" | "createdAt" | "updatedAt"> {
  return {
    hostname: data.hostname,
    sn: data.sn,
    assetTag: data.assetTag,
    manufacturer: (data.manufacturer || "Other") as WorkstationManufacturer,
    model: data.model,
    cpuModel: data.cpuModel,
    cpuCount: parseInt(data.cpuCount) || 4,
    memoryGB: parseInt(data.memoryGB) || 16,
    diskType: data.diskType || "SSD",
    diskCapacityGB: parseInt(data.diskCapacityGB) || 512,
    macAddress: data.macAddress ?? "",
    os: (data.os || "Windows 11") as OperatingSystem,
    osVersion: data.osVersion ?? "",
    bizIp: data.bizIp ?? "",
    userName: data.userName ?? "",
    department: data.department ?? "",
    monitors: [],
    officeBuilding: data.officeBuilding ?? "",
    floor: data.floor ?? "",
    seat: data.seat ?? "",
    status: (data.status || "online") as ServerStatus,
    purchaseDate: data.purchaseDate ?? "",
    warrantyEnd: data.warrantyEnd ?? "",
    tags: data.tags ? data.tags.split(/[;,]/).map((t) => t.trim()).filter(Boolean) : [],
    remark: data.remark,
  };
}
