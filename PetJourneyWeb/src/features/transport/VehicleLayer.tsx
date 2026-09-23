import type { TransportMode } from "@/shared/contracts";
import { MapAnchor } from "@/shared/map";
import { legTitle, MODE_LABEL, vehicleAnchorAt, currentLeg } from "@/shared/journey/vehicle";
import type { JourneyOverlayProps } from "@/shared/slots/names";
import { Icon, type IconName } from "@/shared/ui";
import "./transport.css";

const MODE_ICON: Record<TransportMode, IconName> = {
  flight: "plane",
  train: "train",
  ferry: "ship",
  drive: "car",
  taxi: "car",
  transit: "train",
  walk: "pin",
};


/** VehicleMarker：交通工具沿路线移动（位置由服务器时间与时间线决定），点击打开班次卡。 */
export function VehicleMarker({ mode, heading, label, onOpen }: { mode: TransportMode; heading: number; label: string; onOpen: () => void }) {
  const rotate = mode === "flight" ? heading : 0;
  return (
    <button type="button" className={`ps-vehicle ps-vehicle--${mode}`} data-map-interactive data-testid="vehicle-marker" aria-label={label} onClick={onOpen}>
      <span className="ps-vehicle__glow" aria-hidden="true" />
      <span className="ps-vehicle__icon" style={{ transform: `rotate(${rotate}deg)` }}>
        <Icon name={MODE_ICON[mode]} size={24} strokeWidth={1.9} />
      </span>
    </button>
  );
}

export function VehicleLayer({ snapshot, nowMs, openSheet }: JourneyOverlayProps) {
  const leg = currentLeg(snapshot);
  const anchor = vehicleAnchorAt(snapshot, nowMs);
  if (!leg || !anchor) return null;
  return (
    <MapAnchor at={anchor.point} z={2}>
      <VehicleMarker
        mode={leg.mode}
        heading={anchor.heading}
        label={`${leg.world_service ? `${MODE_LABEL[leg.mode]} ${legTitle(leg)}` : legTitle(leg)}：查看行程卡`}
        onOpen={() => openSheet("leg", leg.leg_id)}
      />
    </MapAnchor>
  );
}

export { MODE_ICON };
