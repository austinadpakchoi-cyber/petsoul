/**
 * “这趟旅途”底部面板（?sheet=trip，第 1 步）：只在行程快照与 W1 对齐后出现，内容全部来自对齐后的快照。
 * - 这一趟的路线（精简版）：每段出发时刻（出发地当地时间）、起止、交通方式、走过了 / 正在走 / 接下来；
 *   “正在走”只认快照的 current_leg_id（W1 的 leg 是主段，不是当前段）。点一段打开它的行程卡（?sheet=leg:<段 id>）。
 * - 四个记录入口：手账、旅途来信、带回的收藏、照片；journey.cards 插槽整块照放（寻味、到店计划、驾校提示由各模块自己判断出不出现）；
 *   数据来源标记（演示行程才显示）。
 * - 面板属于面板上那只宠物：从这里去别的页面（四个入口和卡片里的链接）之前，先把当前宠物换成它（onEnter，同面板其他入口）。
 */
import type { MouseEvent } from "react";
import { Link } from "react-router";
import type { JourneyMapSnapshot } from "@/shared/contracts";
import { effectiveArrival, effectiveDeparture, legTitle, MODE_LABEL } from "@/shared/journey/vehicle";
import { Slot } from "@/shared/slots/Slot";
import { DataOriginBadge, Icon, Sheet } from "@/shared/ui";

function clean(name: string): string {
  return name.replace("（示意）", "");
}

function localClock(ms: number, timeZone: string): string {
  try {
    return new Date(ms).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", timeZone });
  } catch {
    return new Date(ms).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  }
}

export function TripSheet({
  snapshot,
  nowMs,
  openSheet,
  close,
  onEnter,
}: {
  snapshot: JourneyMapSnapshot;
  /** 校准过的真实时间（不是演示加速时钟）。 */
  nowMs: number;
  openSheet: (kind: "leg" | "media", id: string) => void;
  close: () => void;
  /** 离开地图去别的页面之前调用（把当前宠物换成这趟旅途的那只）。 */
  onEnter: () => void;
}) {
  // 点到离开地图的链接（不是 ?sheet= 这种地图内的）：先换当前宠物，再由链接自己跳转。
  const onClickCapture = (event: MouseEvent) => {
    const link = (event.target as Element).closest?.("a[href]");
    const href = link?.getAttribute("href") ?? "";
    if (link && !href.startsWith("?")) onEnter();
  };
  return (
    <Sheet title="这趟旅途" subtitle={snapshot.destination_title ? clean(snapshot.destination_title) : undefined} onClose={close} className="ps-wmap-trip">
      <div onClickCapture={onClickCapture}>
        <h3 className="ps-wmap-trip__heading">这一趟的路线</h3>
        <ol className="ps-wmap-trip__legs">
          {snapshot.legs.map((leg) => {
            const done = leg.phase === "arrived" || effectiveArrival(leg.times) <= nowMs;
            const current = leg.leg_id === snapshot.current_leg_id && !done;
            const state = done ? "走过了" : current ? "正在走" : "接下来";
            const [from, to] = [clean(leg.origin.name), clean(leg.destination.name)];
            const route = `${from} → ${to}`;
            const mode = leg.world_service ? legTitle(leg) : MODE_LABEL[leg.mode];
            return (
              <li key={leg.leg_id} className={done ? "is-done" : current ? "is-current" : ""}>
                <button type="button" onClick={() => openSheet("leg", leg.leg_id)} aria-label={`${route}，${mode}，${state}。看这一段的行程卡`}>
                  <span className="ps-wmap-trip__time">{localClock(effectiveDeparture(leg.times), leg.times.origin_timezone)}</span>
                  <span className="ps-wmap-trip__what">
                    {/* 起点、终点各自成块：窄屏折行先在箭头处断，不把地名拆成两半。 */}
                    <strong>
                      <span>{from}</span> → <span>{to}</span>
                    </strong>
                    <small>
                      {mode} · {state}
                    </small>
                  </span>
                  <Icon name="chevron" size={16} />
                </button>
              </li>
            );
          })}
        </ol>
        <nav className="ps-wmap-trip__links" aria-label="这趟旅途的记录">
          <Link to={`/guides?journey=${encodeURIComponent(snapshot.journey_id)}`}>
            <Icon name="bookmark" size={17} />
            <span>手账</span>
          </Link>
          <Link to="/communicator?channel=family">
            <Icon name="mail" size={17} />
            <span>旅途来信</span>
          </Link>
          <Link to="/collection">
            <Icon name="gift" size={17} />
            <span>带回的收藏</span>
          </Link>
          <Link to="/photos?scene=train">
            <Icon name="camera" size={17} />
            <span>照片</span>
          </Link>
        </nav>
        <div className="ps-wmap-trip__cards">
          <Slot name="journey.cards" props={{ snapshot, nowMs, openSheet }} />
        </div>
        <DataOriginBadge origin={snapshot.data_origin} label="演示行程：不对应真实班次或车辆位置" />
      </div>
    </Sheet>
  );
}
