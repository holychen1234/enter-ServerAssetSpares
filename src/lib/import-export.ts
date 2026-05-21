import * as XLSX from "xlsx";
import type { Server, ServerStatus, Manufacturer, BmcProtocol } from "@/types/cmdb";

// ---------- constants ----------

/** Column headers (display) → field key mapping */
export const SERVER_COLUMNS = [
  { key: "hostname", label: "主机名", required: true, example: "srv-bj-prod-01" },
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
  "Dell", "HPE", "Lenovo", "Inspur", "Supermicro", "Huawei", "Other",
];
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
  XLSX.utils.book_append_sheet(wb, ws, "主机资产");
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

/** Parse a file (CSV or Excel) and return validated rows. */
export function parseImportFile(file: File): Promise<ImportResult> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = new Uint8Array(e.target!.result as ArrayBuffer);
        const wb = XLSX.read(data, { type: "array" });
        const sheet = wb.Sheets[wb.SheetNames[0]];
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
            const key = labelToKey.get(headerRow[j]?.trim() ?? "");
            if (key) {
              data[key] = (raw[j] ?? "").trim();
            }
          }
          const errors = validateImportRow(data);
          rows.push({ rowIndex: i + 1, data, errors });
        }

        const validCount = rows.filter((r) => r.errors.length === 0).length;
        resolve({ rows, validCount, errorCount: rows.length - validCount });
      } catch (err) {
        reject(err instanceof Error ? err : new Error("文件解析失败"));
      }
    };
    reader.onerror = () => reject(new Error("文件读取失败"));
    reader.readAsArrayBuffer(file);
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
    if (data.manufacturer && !VALID_MANUFACTURERS.includes(data.manufacturer as Manufacturer)) {
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
    if (data.purchaseDate && isNaN(Date.parse(data.purchaseDate))) {
      errors.push(`采购日期 "${data.purchaseDate}" 格式无效，请使用 YYYY-MM-DD`);
    }
    if (data.warrantyEnd && isNaN(Date.parse(data.warrantyEnd))) {
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
    manufacturer: (data.manufacturer || "Other") as Manufacturer,
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
    purchaseDate: data.purchaseDate || "",
    warrantyEnd: data.warrantyEnd || "",
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
