import { Link } from "react-router";
import type { HomeSnapshot } from "@/shared/contracts";
import { Card, Icon } from "@/shared/ui";
import "./journey.css";

/** home.panels：旅途状态入口。“看看 TA”打开同一张旅途地图并定位当前交通工具。 */
export function JourneyStatusPanel({ snapshot }: { snapshot: HomeSnapshot }) {
  if (!snapshot.journey) {
    if (snapshot.presence !== "at_home") return null;
    return (
      <Card>
        <Link to="/journey" className="ps-journey-card">
          <span className="ps-journey-card__icon">
            <Icon name="compass" />
          </span>
          <span style={{ flex: 1 }}>
            <strong>{snapshot.pet.name} 在家，想出去走走吗？</strong>
            <span className="ps-muted" style={{ display: "block" }}>
              去出发站选个地方，旅费 {snapshot.wallet.balance}
            </span>
          </span>
          <Icon name="chevron" />
        </Link>
      </Card>
    );
  }
  const visitId = snapshot.journey.current_visit_id;
  return (
    <Card>
      <Link to="/journey" className="ps-journey-card">
        <span className="ps-journey-card__icon">
          <Icon name="journey" />
        </span>
        <span style={{ flex: 1 }}>
          <strong>{snapshot.journey.headline}</strong>
          <span className="ps-muted" style={{ display: "block" }}>
            点开地图看 TA 在哪、在做什么
          </span>
        </span>
        <Icon name="chevron" />
      </Link>
      {visitId ? (
        <Link to={`/visits/${encodeURIComponent(visitId)}`} className="ps-btn ps-btn--secondary ps-btn--block" style={{ marginTop: 8 }}>
          <Icon name="cup" size={16} /> TA 在店里，进去看看
        </Link>
      ) : null}
    </Card>
  );
}
