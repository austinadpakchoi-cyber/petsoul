/**
 * 爪爪驾校的三个入口：
 * - circle.places：星球圈“星球上的地方”——主入口；
 * - home.panels：家园里的紧凑进度卡（学车进行中、待领证、还有借车券时才出现）；
 * - journey.cards：旅途里在报名学车后提示自驾需要驾照，拿证后提示借车券。乘车出行不受影响。
 * 取不到驾校状态（未登录、旧后端）时入口安静地不显示，不打扰宿主页面。
 */
import { Link } from "react-router";
import type { DrivingSchoolStatus } from "@/shared/contracts";
import type { JourneyOverlayProps, SlotPropsMap } from "@/shared/slots/names";
import { Card, Chip, Icon } from "@/shared/ui";
import { useSchoolStatus } from "./hooks";
import { STATE_TEXT, SUBJECT_SHORT } from "./text";

function progress(status: DrivingSchoolStatus): string {
  if (status.license) return status.ceremony_done ? "已拿到爪爪驾照" : "四科全过，等你们去领证";
  if (status.stage === "none") return "陪 TA 学开车：主人陪考，宠物拿证";
  if (status.stage === "wish") return "TA 说想学开车，等你陪 TA 报名";
  const current = status.subjects.find((s) => s.state !== "passed");
  const passed = status.subjects.filter((s) => s.state === "passed").length;
  return current ? `已通过 ${passed}/4 · ${SUBJECT_SHORT[current.subject]}${STATE_TEXT[current.state]}` : `已通过 ${passed}/4`;
}

export function CircleSchoolEntry(_props: SlotPropsMap["circle.places"]) {
  const status = useSchoolStatus();
  if (status.isError) return null;
  return (
    <section aria-labelledby="ds-places" className="ds-places">
      <h2 id="ds-places" className="ps-section-title">
        星球上的地方
      </h2>
      <Link to="/school" className="ds-place-card">
        <span className="ds-place-card__icon" aria-hidden="true">
          <Icon name="car" size={26} />
        </span>
        <span className="ds-place-card__body">
          <strong>爪爪驾校</strong>
          <span className="ps-muted">{status.data ? progress(status.data) : "龟教练：方向可以慢慢找，停车要稳稳当当。"}</span>
        </span>
        {status.data?.open_session ? <Chip tone="sun">考试中</Chip> : <Icon name="chevron" size={16} />}
      </Link>
    </section>
  );
}

export function HomeSchoolCard(_props: SlotPropsMap["home.panels"]) {
  const status = useSchoolStatus();
  const data = status.data;
  if (!data || data.stage === "none") return null;
  if (data.license && data.ceremony_done) return null;
  return (
    <Card className="ds-home-card">
      <Link to="/school" className="ds-place-card ds-place-card--flat">
        <span className="ds-place-card__icon" aria-hidden="true">
          <Icon name="car" size={22} />
        </span>
        <span className="ds-place-card__body">
          <strong>爪爪驾校</strong>
          <span className="ps-muted">{progress(data)}</span>
        </span>
        <Icon name="chevron" size={16} />
      </Link>
    </Card>
  );
}

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
