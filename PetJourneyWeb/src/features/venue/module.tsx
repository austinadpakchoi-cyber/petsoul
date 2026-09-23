/**
 * 店内模块（R0：咖啡馆模板场景 + 选座/饮品/合影/打招呼可见反馈；到访状态由 journey 模块的 VisitService 提供）。
 */
import { Link } from "react-router";
import { defineModule, slot } from "@/shared/modules/types";
import type { JourneyOverlayProps } from "@/shared/slots/names";
import { Card, Icon } from "@/shared/ui";
import { VisitPage } from "./VisitPage";

function VisitEntryCard({ snapshot }: JourneyOverlayProps) {
  const visitId = snapshot.current_visit_id ?? snapshot.planned_visit_id;
  if (!visitId && snapshot.data_origin !== "fixture") return null;
  if (!visitId && !snapshot.arrival_context) return null;
  const atVenue = Boolean(snapshot.current_visit_id);
  return (
    <Card>
      <Link to={`/visits/${encodeURIComponent(visitId ?? "fx-visit-001")}`} className="ps-journey-card">
        <span className="ps-journey-card__icon">
          <Icon name="seat" />
        </span>
        <span style={{ flex: 1 }}>
          <strong>{snapshot.data_origin === "fixture" ? "看看 TA 在店里（演示到访）" : atVenue ? "TA 已到店，进去看看" : "这趟到店计划"}</strong>
          <span className="ps-muted" style={{ display: "block" }}>
            {snapshot.data_origin === "fixture" ? "示例咖啡馆 · 选座、点饮品、合影" : atVenue ? "座位、饮品与合影按真实到访状态变化" : "尚未到店；行动要等 TA 抵达后才开放"}
          </span>
        </span>
        <Icon name="chevron" />
      </Link>
    </Card>
  );
}

export default defineModule({
  id: "venue",
  routes: [{ path: "visits/:visitId", element: <VisitPage /> }],
  slots: [slot("journey.cards", "venue.entry", VisitEntryCard, 20)],
});
