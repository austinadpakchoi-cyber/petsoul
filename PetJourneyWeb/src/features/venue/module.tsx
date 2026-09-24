/**
 * 店内模块（R0：咖啡馆模板场景 + 选座/饮品/合影/打招呼可见反馈；到访状态由 journey 模块的 VisitService 提供）。
 */
import { Link } from "react-router";
import { defineModule, slot } from "@/shared/modules/types";
import type { JourneyOverlayProps } from "@/shared/slots/names";
import { Card, Icon } from "@/shared/ui";
import { VisitPage } from "./VisitPage";

/**
 * 旅途卡片入口。快照里没有地点类型（是店、小路还是公园要打开到访才知道），live 的说法不写“到店 / 座位 / 饮品”；
 * 演示到访固定是示例咖啡馆，保留原说法。
 */
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
          <strong>{snapshot.data_origin === "fixture" ? "看看 TA 在店里（演示到访）" : atVenue ? "TA 已经到了" : "这趟要去的地方"}</strong>
          {/* live 的副标题控制在一行（320 宽约 12 个字），不把一个词折成两半 */}
          <span className="ps-muted" style={{ display: "block" }}>
            {snapshot.data_origin === "fixture" ? "示例咖啡馆 · 选座、点饮品、合影" : atVenue ? "去看看 TA 在那儿做什么" : "到了以后才能开始活动"}
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
