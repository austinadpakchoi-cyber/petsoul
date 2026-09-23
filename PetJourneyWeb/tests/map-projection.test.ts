import { describe, expect, it } from "vitest";
import type { BasemapView } from "@/shared/contracts";
import { basemapProjection, boundsBox, isUsableBasemap, schematicProjection } from "@/shared/map/projection";

const basemap = {
  available: true,
  reason: null,
  provider: "amap",
  image_url: "/api/v1/web/media/basemaps/bm_0123456789abcdef0123",
  center: { lat: 22.2837, lng: 114.1579 },
  zoom: 16,
  width: 352,
  height: 416,
  attribution: "底图：高德地图",
  expires_at: "2026-09-23T06:00:00+00:00",
} satisfies BasemapView;

describe("map projection", () => {
  it("puts the basemap centre in the middle and matches image pixels", () => {
    const size = { width: 352, height: 416 };
    const { base, fit } = basemapProjection(basemap, size);
    expect(fit).toBe(1);
    const c = base(basemap.center);
    expect(c.x).toBeCloseTo(176, 6);
    expect(c.y).toBeCloseTo(208, 6);
    // 缩放 16 时，经度 360° 对应 256·2^16 像素：往东 1 个图片像素 = 360 / (256·65536) 度
    const east = base({ lat: basemap.center.lat, lng: basemap.center.lng + 360 / (256 * 65536) });
    expect(east.x - c.x).toBeCloseTo(1, 6);
    expect(east.y).toBeCloseTo(c.y, 6);
  });

  it("contains (never crops) the image when the container aspect differs", () => {
    const { fit } = basemapProjection(basemap, { width: 360, height: 420 });
    expect(fit).toBeCloseTo(Math.min(360 / 352, 420 / 416), 9);
    expect(352 * fit).toBeLessThanOrEqual(360);
    expect(416 * fit).toBeLessThanOrEqual(420);
  });

  it("keeps the schematic fit and ignores empty coordinates when asking for a basemap", () => {
    const base = schematicProjection([{ lat: 22.28, lng: 114.15 }, { lat: 22.29, lng: 114.16 }], { width: 300, height: 300 });
    const a = base({ lat: 22.28, lng: 114.15 });
    const b = base({ lat: 22.29, lng: 114.16 });
    expect(a.x).toBeLessThan(b.x);
    expect(a.y).toBeGreaterThan(b.y);
    expect(boundsBox([{ lat: 0, lng: 0 }, { lat: 22.281912, lng: 114.158134 }, { lat: 22.28551, lng: 114.15771 }])).toEqual({
      south: 22.2819,
      west: 114.1577,
      north: 22.2855,
      east: 114.1581,
    });
    expect(boundsBox([])).toBeNull();
    expect(isUsableBasemap({ ...basemap, available: false })).toBe(false);
    expect(isUsableBasemap(basemap)).toBe(true);
  });
});
