import type { WelcomeDetailKind } from "@/shared/contracts";
import { Card, Chip, Icon } from "@/shared/ui";

const DETAIL_ICON: Record<WelcomeDetailKind, "user" | "bookmark" | "heart"> = {
  owner_title: "user",
  favorite_object: "bookmark",
  interaction_boundary: "heart",
};

/** 入住叮嘱的兑现：只显示 HomeSnapshot.welcome（服务端/fixture 经 MemoryPolicy 投影后的结果）。 */
export function HomeWelcomeBanner({ snapshot }: { snapshot: import("@/shared/contracts").HomeSnapshot }) {
  const welcome = snapshot.welcome;
  if (!welcome) return null;
  return (
    <Card paper className="ps-welcome" data-testid="home-welcome" data-projection-version={welcome.projection_version}>
      <div className="ps-welcome__greeting">“{welcome.greeting}”</div>
      <div className="ps-row">
        {welcome.details.map((detail) => (
          <Chip key={detail.note_id} icon={DETAIL_ICON[detail.kind]}>
            {detail.text}
          </Chip>
        ))}
      </div>
      <div className="ps-welcome__meta">
        <Icon name="check" size={12} /> 来自你确认过的入住叮嘱 · 第 {welcome.projection_version} 版
      </div>
    </Card>
  );
}
