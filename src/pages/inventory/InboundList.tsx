import { ArrowDownToLine } from "lucide-react";
import { MovementListView } from "./MovementListView";

export default function InboundList() {
  return (
    <MovementListView
      type="inbound"
      title="入库记录"
      description="备件入库流水（采购入库、归还入库等）"
      defaultMvType="inbound"
      icon={<ArrowDownToLine className="h-5 w-5" />}
    />
  );
}
