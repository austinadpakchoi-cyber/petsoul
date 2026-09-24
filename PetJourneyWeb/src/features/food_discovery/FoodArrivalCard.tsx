import { Link } from "react-router";
import type { PetArrivalContext } from "@/shared/contracts";
import type { JourneyOverlayProps } from "@/shared/slots/names";
import { useActiveHome, useOptionalCurrentHousehold } from "@/shared/session/householdContext";
import { formatLocalTime } from "@/shared/time/clock";
import { Card, Icon } from "@/shared/ui";
import { foodCardTitle, useFoodPicksAvailable } from "./availability";

/**
 * journey.cards：消费交通的到达上下文（预计到达时间），进入寻味。乘车中只收藏候选，不提前创建到访。
 * 寻味推荐没开（见 availability.ts）时不显示；标题按 TA 去的城市是不是家所在的城市来说；行程版本号不给玩家看。
 * 没有到达上下文时直接不渲染，不调任何接口（插槽里没有旅途时不打扰宿主页面）。
 */
export function FoodArrivalCard({ snapshot }: JourneyOverlayProps) {
  const ctx = snapshot.arrival_context;
  if (!ctx) return null;
  return <FoodArrivalEntry ctx={ctx} />;
}

function FoodArrivalEntry({ ctx }: { ctx: PetArrivalContext }) {
  const available = useFoodPicksAvailable();
  const household = useOptionalCurrentHousehold();
  if (!available) return null;
  // 不在家庭上下文里（个别裸测试）时不知道家在哪座城市，标题按“不知道”说
  return household ? <EntryWithHome ctx={ctx} /> : <EntryLink ctx={ctx} homeCity={null} />;
}

function EntryWithHome({ ctx }: { ctx: PetArrivalContext }) {
  const home = useActiveHome();
  if (home.isLoading) return null;
  return <EntryLink ctx={ctx} homeCity={home.data?.place?.city ?? null} />;
}

function EntryLink({ ctx, homeCity }: { ctx: PetArrivalContext; homeCity: string | null }) {
  return (
    <Card>
      <Link to="/journey/food" className="ps-journey-card">
        <span className="ps-journey-card__icon">
          <Icon name="cup" />
        </span>
        <span style={{ flex: 1 }}>
          <strong>{foodCardTitle(ctx, homeCity)}</strong>
          <span className="ps-muted" style={{ display: "block" }}>
            预计 {formatLocalTime(ctx.feasible_arrival_utc, ctx.destination_timezone)} 到达
          </span>
        </span>
        <Icon name="chevron" />
      </Link>
    </Card>
  );
}
