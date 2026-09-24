import type { WelcomeDetailKind } from "@/shared/contracts";
import { Card, Chip, Icon } from "@/shared/ui";

const DETAIL_ICON: Record<WelcomeDetailKind, "user" | "bookmark" | "heart"> = {
  owner_title: "user",
  favorite_object: "bookmark",
  interaction_boundary: "heart",
};

/**
 * 入住叮嘱的兑现：只显示 HomeSnapshot.welcome（服务端/fixture 经 MemoryPolicy 投影后的结果）。
 * 出处只标在有出处的地方（2026-09-24 巡检 P2）：欢迎语没有来源字段，不标；细节各自带着叮嘱编号，
 * “来自你确认过的生活叮嘱”写在细节上面、只管这几项，没有细节就不写。
 */
export function HomeWelcomeBanner({ snapshot }: { snapshot: import("@/shared/contracts").HomeSnapshot }) {
  const welcome = snapshot.welcome;
  if (!welcome) return null;
  return (
    <Card paper className="ps-welcome" data-testid="home-welcome" data-projection-version={welcome.projection_version}>
      <div className="ps-welcome__greeting">“{welcome.greeting}”</div>
      {welcome.details.length ? (
        <div className="ps-welcome__notes">
          <div className="ps-welcome__meta">
            <Icon name="check" size={12} /> 来自你确认过的生活叮嘱
          </div>
          <div className="ps-row">
            {welcome.details.map((detail) => (
              <Chip key={detail.note_id} icon={DETAIL_ICON[detail.kind]}>
                {detail.text}
              </Chip>
            ))}
          </div>
        </div>
      ) : null}
    </Card>
  );
}
