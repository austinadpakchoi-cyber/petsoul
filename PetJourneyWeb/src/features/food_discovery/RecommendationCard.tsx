import { Link } from "react-router";
import type { FoodRecommendation } from "@/shared/contracts";
import { Card, Chip, DataOriginBadge, Icon } from "@/shared/ui";

const GROUP_TEXT = { primary: "首选", alternative: "备选", explore: "可以试试", needs_verification: "待核实" } as const;

function pct(value: number | null): string {
  return value === null ? "未知" : `${Math.round(value * 100)}`;
}

/** 推荐卡：为什么选、建议点什么、何时不合适、还有什么没核实；四类判断分开，不给“满意概率”。 */
export function RecommendationCard({ rec, stale }: { rec: FoodRecommendation; stale?: boolean }) {
  return (
    <Card className="ps-rec" data-testid={`food-rec-${rec.recommendation_id}`}>
      <div className="ps-row" style={{ justifyContent: "space-between" }}>
        <Chip tone={rec.group === "primary" ? "leaf" : rec.group === "explore" ? "sky" : "neutral"}>{GROUP_TEXT[rec.group]}</Chip>
        {stale ? <Chip tone="danger">行程变了，待复核</Chip> : <DataOriginBadge origin={rec.data_origin} label="演示资料" />}
      </div>
      <h3 className="ps-rec__name">{rec.branch.name}</h3>
      {rec.dishes.map(({ dish, why }) => (
        <div key={dish.dish_id} className="ps-rec__dish">
          <Icon name="cup" size={16} />
          <div>
            <strong>{dish.name}</strong>
            <div className="ps-muted">{why}</div>
          </div>
        </div>
      ))}
      <ul className="ps-rec__list">
        {rec.reasons.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
      {rec.not_suitable_when.length ? (
        <div className="ps-rec__warn">
          <strong>什么时候不合适：</strong>
          {rec.not_suitable_when.join(" ")}
        </div>
      ) : null}
      {rec.unknowns.length ? (
        <div className="ps-rec__unknown">
          <strong>还没核实：</strong>
          {rec.unknowns.join("；")}
        </div>
      ) : null}
      <div className="ps-rec__scores" aria-label="四类判断分开显示">
        <span>品质证据 {pct(rec.scores.quality)}</span>
        <span>口味匹配 {pct(rec.scores.match)}</span>
        <span>本次价值 {pct(rec.scores.value)}</span>
        <span>证据把握 {rec.scores.uncertainty === null ? "未知" : pct(1 - rec.scores.uncertainty)}</span>
      </div>
      <Link className="ps-btn ps-btn--secondary ps-btn--sm" to={`/journey/food/${rec.recommendation_id}`}>
        看依据与出处
      </Link>
    </Card>
  );
}
