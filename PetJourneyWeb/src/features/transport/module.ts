/**
 * 平行交通模块（R0 插槽 + fixture；真实班次/时刻表待用户分配的交通模块窗口实现）。
 * 提供：TransportService、地图 VehicleMarker 叠加层、班次卡面板。不注册独立交通页面。
 */
import { defineModule, slot } from "@/shared/modules/types";
import { LegSheet } from "./LegSheet";
import { createFixtureTransportService, createLiveTransportService } from "./service";
import { VehicleLayer } from "./VehicleLayer";

export default defineModule({
  id: "transport",
  services: {
    transport: { fixture: createFixtureTransportService, live: createLiveTransportService },
  },
  slots: [slot("journey.map.overlay", "transport.vehicle", VehicleLayer, 10), slot("journey.sheet", "transport.leg", LegSheet, 10)],
});
