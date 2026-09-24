import { Link } from "react-router";
import type { HomeSnapshot } from "@/shared/contracts";
import { Card, Icon } from "@/shared/ui";
import { useVisitSetting } from "@/features/venue/useVisitSetting";
import "./journey.css";

/**
 * home.panels：旅途状态入口。“看看 TA”打开同一张旅途地图并定位当前交通工具。
 * 到访入口只有确定是门店（到访的场景模板是 cafe / restaurant，见 venue/visitKind）才说“在店里”，其余说“到了”。
 * 注：小窝的 home.panels 白名单目前是空的（features/home/HomePage.tsx），这张卡现在不在任何页面上显示。
 */
export function JourneyStatusPanel({ snapshot }: { snapshot: HomeSnapshot }) {
  const setting = useVisitSetting(snapshot.journey?.current_visit_id ?? null);
  if (!snapshot.journey) {
    if (snapshot.presence !== "at_home") return null;
    return (
      <Card>
        <Link to="/journey" className="ps-journey-card">
          <span className="ps-journey-card__icon">
            <Icon name="compass" />
          </span>
          <span style={{ flex: 1 }}>
            <strong>{snapshot.pet.name} 在家 · 出不出门由 TA 决定</strong>
            <span className="ps-muted" style={{ display: "block" }}>
              想到好地方，可以悄悄告诉 TA
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
          {setting === "shop" ? <><Icon name="cup" size={16} /> TA 在店里，进去看看</> : <><Icon name="pin" size={16} /> TA 到了，去看看</>}
        </Link>
      ) : null}
    </Card>
  );
}
