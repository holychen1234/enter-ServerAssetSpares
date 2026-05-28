import { useState, useRef, useCallback } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Progress } from "@/components/ui/progress";
import { toast } from "@/hooks/use-toast";
import {
  Upload,
  Download,
  FileSpreadsheet,
  FileText,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Loader2,
} from "lucide-react";
import {
  parseImportFile,
  importRowToPayload,
  parseNetworkDeviceImportFile,
  networkDeviceImportRowToPayload,
  generateTemplate,
  generateNetworkDeviceTemplate,
  downloadBlob,
  type ImportResult,
} from "@/lib/import-export";
import { createServer, createNetworkDevice } from "@/lib/api/cmdb";

type AssetType = "server" | "networkDevice";

interface Props {
  open: boolean;
  onClose: () => void;
  onImported: () => void;
  type?: AssetType;
}

export function ImportDialog({ open, onClose, onImported, type = "server" }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState<"upload" | "preview" | "importing" | "done">("upload");
  const [result, setResult] = useState<ImportResult | null>(null);
  const [importingProgress, setImportingProgress] = useState({ done: 0, total: 0 });
  const [importErrors, setImportErrors] = useState<string[]>([]);
  const [dragOver, setDragOver] = useState(false);

  const isNdev = type === "networkDevice";
  const title = isNdev ? "网络设备" : "服务器";
  const labelName = isNdev ? "设备名" : "服务器名";

  const reset = () => {
    setStep("upload");
    setResult(null);
    setImportingProgress({ done: 0, total: 0 });
    setImportErrors([]);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleFile = useCallback(async (file: File) => {
    try {
      const parseFn = isNdev ? parseNetworkDeviceImportFile : parseImportFile;
      const r = await parseFn(file);
      if (r.rows.length === 0) {
        toast({ title: "文件为空", description: "未检测到有效数据行" });
        return;
      }
      setResult(r);
      setStep("preview");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "未知错误";
      console.error("文件解析失败:", msg, err);
      toast({
        title: "文件解析失败",
        description: msg,
        variant: "destructive",
      });
    }
  }, [isNdev]);

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = "";
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setDragOver(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const handleImport = async () => {
    if (!result) return;
    const valid = result.rows.filter((r) => r.errors.length === 0);
    if (valid.length === 0) {
      toast({ title: "无有效数据", description: "请修正错误后重试" });
      return;
    }
    setStep("importing");
    setImportingProgress({ done: 0, total: valid.length });
    setImportErrors([]);

    const toPayload = isNdev ? networkDeviceImportRowToPayload : importRowToPayload;
    const createFn = isNdev ? createNetworkDevice : createServer;

    let ok = 0;
    const errs: string[] = [];
    for (let i = 0; i < valid.length; i++) {
      try {
        const payload = toPayload(valid[i].data);
        await createFn(payload as any);
        ok++;
      } catch (err) {
        const msg = err instanceof Error ? err.message : "未知错误";
        errs.push(`第 ${valid[i].rowIndex} 行：${msg}`);
      }
      setImportingProgress({ done: i + 1, total: valid.length });
    }

    setImportErrors(errs);
    setStep("done");
    if (ok > 0) {
      toast({ title: `成功导入 ${ok} 条${title}` });
      onImported();
    }
    if (errs.length > 0) {
      toast({ title: `${errs.length} 条失败`, variant: "destructive" });
    }
  };

  const downloadTemplate = (format: "csv" | "xlsx") => {
    const genFn = isNdev ? generateNetworkDeviceTemplate : generateTemplate;
    const blob = genFn(format);
    const ext = format === "csv" ? "csv" : "xlsx";
    downloadBlob(blob, `${title}资产导入模板.${ext}`);
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && handleClose()}>
      <DialogContent className="sm:max-w-[700px] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>批量导入{title}</DialogTitle>
          <DialogDescription>
            支持 Excel (.xlsx) 和 CSV 文件。请先下载模板，按格式填写后上传。
          </DialogDescription>
        </DialogHeader>

        {step === "upload" && (
          <div className="space-y-4">
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => downloadTemplate("xlsx")}>
                <Download className="mr-1 h-4 w-4" />
                Excel 模板
              </Button>
              <Button variant="outline" size="sm" onClick={() => downloadTemplate("csv")}>
                <Download className="mr-1 h-4 w-4" />
                CSV 模板
              </Button>
            </div>

            <div
              className={`relative border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
                dragOver
                  ? "border-primary bg-primary/5"
                  : "border-border hover:border-muted-foreground/50"
              }`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <Upload className="mx-auto h-10 w-10 text-muted-foreground mb-3" />
              <p className="text-sm text-muted-foreground">
                拖拽文件到此处，或 <span className="text-primary cursor-pointer underline">点击选择文件</span>
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                支持 .xlsx、.csv 格式
              </p>
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.csv"
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                onChange={handleFileInput}
              />
            </div>
          </div>
        )}

        {step === "preview" && result && (
          <div className="space-y-4">
            <div className="flex items-center gap-4 text-sm">
              <span className="flex items-center gap-1 text-green-600">
                <CheckCircle2 className="h-4 w-4" />
                {result.validCount} 条有效
              </span>
              {result.errorCount > 0 && (
                <span className="flex items-center gap-1 text-red-500">
                  <XCircle className="h-4 w-4" />
                  {result.errorCount} 条有误
                </span>
              )}
              <span className="text-muted-foreground">
                共 {result.rows.length} 条
              </span>
            </div>

            <div className="border rounded-lg max-h-[360px] overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[60px]">行号</TableHead>
                    <TableHead>{labelName}</TableHead>
                    <TableHead>SN</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead className="w-[200px]">校验</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.rows.map((row) => (
                    <TableRow
                      key={row.rowIndex}
                      className={
                        row.errors.length > 0 ? "bg-red-50 dark:bg-red-950/20" : ""
                      }
                    >
                      <TableCell className="text-xs text-muted-foreground">
                        {row.rowIndex}
                      </TableCell>
                      <TableCell className="font-medium">
                        {row.data.hostname || "-"}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {row.data.sn || "-"}
                      </TableCell>
                      <TableCell>{row.data.status || "online"}</TableCell>
                      <TableCell>
                        {row.errors.length === 0 ? (
                          <span className="flex items-center gap-1 text-green-600 text-xs">
                            <CheckCircle2 className="h-3 w-3" /> 通过
                          </span>
                        ) : (
                          <div className="text-xs text-red-500 space-y-0.5">
                            {row.errors.map((e, i) => (
                              <div key={i} className="flex items-start gap-1">
                                <AlertCircle className="h-3 w-3 mt-0.5 shrink-0" />
                                <span>{e}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            <div className="flex justify-between">
              <Button variant="ghost" onClick={reset}>
                重新选择文件
              </Button>
              {result.validCount > 0 && (
                <Button onClick={handleImport}>
                  导入 {result.validCount} 条有效数据
                </Button>
              )}
            </div>
          </div>
        )}

        {step === "importing" && (
          <div className="space-y-4 py-8">
            <div className="flex items-center justify-center gap-2 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span>正在导入...</span>
            </div>
            <Progress
              value={
                importingProgress.total > 0
                  ? (importingProgress.done / importingProgress.total) * 100
                  : 0
              }
            />
            <p className="text-center text-sm text-muted-foreground">
              {importingProgress.done} / {importingProgress.total}
            </p>
          </div>
        )}

        {step === "done" && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-green-600">
              <CheckCircle2 className="h-5 w-5" />
              <span className="font-medium">
                导入完成：成功 {importingProgress.done - importErrors.length} 条
                {importErrors.length > 0 && `，失败 ${importErrors.length} 条`}
              </span>
            </div>

            {importErrors.length > 0 && (
              <div className="bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900 rounded-lg p-3 max-h-[200px] overflow-auto">
                <p className="text-sm font-medium text-red-700 dark:text-red-400 mb-2">
                  失败明细：
                </p>
                <ul className="text-xs text-red-600 dark:text-red-400 space-y-1">
                  {importErrors.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex gap-2">
              <Button variant="outline" onClick={reset}>
                继续导入
              </Button>
              <Button onClick={handleClose}>完成</Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
