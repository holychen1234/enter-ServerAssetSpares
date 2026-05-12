import { ArrowUpFromLine } from "lucide-react";
import { MovementListView } from "./MovementListView";

export default function OutboundList() {
  return (
    <MovementListView
      type="outbound"
      title="出库 / 领用记录"
      description="备件出库与报废记录，可关联到具体服务器"
      defaultMvType="outbound"
      icon={<ArrowUpFromLine className="h-5 w-5" />}
    />
  );
}
