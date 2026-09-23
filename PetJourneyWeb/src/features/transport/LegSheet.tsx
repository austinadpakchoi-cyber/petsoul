import type { JourneyLeg, TimeBasis } from "@/shared/contracts";
import {
  effectiveArrival,
  effectiveDeparture,
  legProgress,
  remainingMs,
} from "@/shared/journey/vehicle";
import type { JourneySheetProps } from "@/shared/slots/names";
import { formatDuration, formatLocalTime } from "@/shared/time/clock";
import { Chip, DataOriginBadge, Progress, Sheet } from "@/shared/ui";
import { legTitle, MODE_LABEL } from "@/shared/journey/vehicle";

const BASIS_LABEL: Record<TimeBasis, string> = {
  verified_timetable: "按时刻表",
  live_status: "实时动态",
  routed_estimate: "预计车程",
  demo_fixture: "演示行程",
};

const ROLE_LABEL = {
  driver: "TA 在开车",
  passenger: "TA 是乘客",
  walker: "TA 在步行",
} as const;

function LegCard({ leg, nowMs }: { leg: JourneyLeg; nowMs: number }) {
  const progress = legProgress(leg.times, nowMs);
  const arrived = leg.phase === "arrived" || progress >= 1;
  return (
    <div className="ps-stack">
      <div className="ps-legcard">
        <div>
          <div className="ps-legcard__time">
            {formatLocalTime(
              new Date(effectiveDeparture(leg.times)).toISOString(),
              leg.times.origin_timezone,
            )}
          </div>
          <div className="ps-legcard__place">{leg.origin.name}</div>
          <div className="ps-muted">{leg.times.origin_timezone}</div>
        </div>
        <div className="ps-legcard__mid">{MODE_LABEL[leg.mode]}</div>
        <div style={{ textAlign: "right" }}>
          <div className="ps-legcard__time">
            {formatLocalTime(
              new Date(effectiveArrival(leg.times)).toISOString(),
              leg.times.destination_timezone,
            )}
          </div>
          <div className="ps-legcard__place">{leg.destination.name}</div>
          <div className="ps-muted">{leg.times.destination_timezone}</div>
        </div>
      </div>
      <Progress value={progress} label="行程时间进度" />
      <p className="ps-muted" style={{ margin: 0 }}>
        以上为当前有效时间（实际优先，其次预计、计划）。时间进度不代表实时定位或实际里程。
      </p>
      <div className="ps-row">
        <Chip tone={arrived ? "leaf" : "sky"}>
          {arrived
            ? "已到站"
            : `还剩 ${formatDuration(remainingMs(leg.times, nowMs))}`}
        </Chip>
        <Chip>{BASIS_LABEL[leg.time_basis]}</Chip>
        <Chip>{ROLE_LABEL[leg.role]}</Chip>
        {leg.position_basis === "schematic" ? (
          <Chip>线路示意</Chip>
        ) : (
          <Chip>模拟线路位置</Chip>
        )}
      </div>
      <p className="ps-muted" style={{ margin: 0 }}>
        时间依据：{leg.reference?.source_label ?? "未提供"}
        。车辆位置由服务器时间和已确认时间线推算，打开或关闭页面不会改变到达时间。
      </p>
      <DataOriginBadge
        origin={leg.time_basis === "demo_fixture" ? "fixture" : "live"}
        label="演示行程：不对应真实班次"
      />
    </div>
  );
}

export function LegSheet({
  snapshot,
  nowMs,
  kind,
  targetId,
  close,
}: JourneySheetProps) {
  if (kind !== "leg") return null;
  const leg = snapshot.legs.find((l) => l.leg_id === targetId);
  if (!leg) return null;
  const title = legTitle(leg);
  return (
    <Sheet
      title={title}
      subtitle={`${leg.origin.name} → ${leg.destination.name}`}
      onClose={close}
    >
      <LegCard leg={leg} nowMs={nowMs} />
    </Sheet>
  );
}
