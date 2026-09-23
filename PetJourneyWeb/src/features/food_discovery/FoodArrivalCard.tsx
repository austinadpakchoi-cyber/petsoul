import { Link } from "react-router";
import type { JourneyOverlayProps } from "@/shared/slots/names";
import { formatLocalTime } from "@/shared/time/clock";
import { Card, Icon } from "@/shared/ui";

/** journey.cards：消费交通的到达上下文（可行到达/停留窗口/行程版本），进入寻味。乘车中只收藏候选，不提前创建到访。 */
export function FoodArrivalCard({ snapshot }: JourneyOverlayProps) {
  const ctx = snapshot.arrival_context;
  if (!ctx) return null;
  return (
    <Card>
      <Link to="/journey/food" className="ps-journey-card">
        <span className="ps-journey-card__icon">
          <Icon name="cup" />
        </span>
        <span style={{ flex: 1 }}>
          <strong>到{ctx.city}后，让 TA 挑一家</strong>
          <span className="ps-muted" style={{ display: "block" }}>
            预计 {formatLocalTime(ctx.feasible_arrival_utc, ctx.destination_timezone)} 能到店 · 行程第 {ctx.itinerary_version} 版
          </span>
        </span>
        <Icon name="chevron" />
      </Link>
    </Card>
  );
}
