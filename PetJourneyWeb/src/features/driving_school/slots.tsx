/**
 * 爪爪驾校在主包里的入口：journey.cards 里的驾照提示（地图“这趟旅途”面板和旅途页都放这个插槽）。
 * 报名学车后提示自己开车出门要先有驾照（乘车不受影响）；拿证后还有借车券时提示借车券。学车进度、领证提醒在地图主状态面板，这里不重复。
 * 原来的朋友圈入口（circle.places）和小窝进度卡（home.panels）两处都已不渲染，2026-09-24 删掉了。
 * 取不到驾校状态（未登录、旧后端）时安静地不显示，不打扰宿主页面。
 */
import { Link } from "react-router";
import type { JourneyOverlayProps } from "@/shared/slots/names";
import { Card, Icon } from "@/shared/ui";
import { useSchoolStatus } from "./hooks";

export function JourneySchoolHint(_props: JourneyOverlayProps) {
  const status = useSchoolStatus();
  const data = status.data;
  if (!data) return null;
  if (data.license) {
    if (!data.voucher_available) return null;
    return (
      <Card flat className="ds-journey-hint">
        <Icon name="gift" size={18} />
        <span>有一张驾校借车券：TA 第一次自己开车兜风时，借驾校的车不用租车费。</span>
      </Card>
    );
  }
  if (data.stage === "none") return null;
  return (
    <Card flat className="ds-journey-hint">
      <Icon name="car" size={18} />
      <span>
        自己开车出门需要先取得爪爪驾照（乘车不受影响）。<Link to="/school">去驾校看看</Link>
      </span>
    </Card>
  );
}
