import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BasemapView } from "@/shared/contracts";
import { SchematicMapSurface } from "@/shared/map";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";

vi.mock("@/shared/config/env", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/shared/config/env")>();
  return { env: { ...original.env, dataMode: "live" } };
});

const HOME = { lat: 22.2819, lng: 114.1581 };
const CAFE = { lat: 22.2855, lng: 114.1577 };
const AVAILABLE: BasemapView = {
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
};

class FixedResizeObserver {
  constructor(private readonly callback: ResizeObserverCallback) {}
  observe() {
    this.callback([{ contentRect: { width: 352, height: 416 } } as ResizeObserverEntry], this as unknown as ResizeObserver);
  }
  disconnect() {}
  unobserve() {}
}

function renderMap(basemap: (req: unknown) => Promise<BasemapView>, dashed = false) {
  const services = { platform: { meta: vi.fn(), basemap: vi.fn(basemap) } } as unknown as ServiceMap;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <SchematicMapSurface bounds={[HOME, CAFE]} routes={[{ id: "walk", points: [HOME, CAFE], dashed }]} places={[]} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { ...view, basemap: services.platform.basemap as ReturnType<typeof vi.fn> };
}

describe("journey map basemap", () => {
  beforeEach(() => vi.stubGlobal("ResizeObserver", FixedResizeObserver));
  afterEach(() => vi.unstubAllGlobals());

  it("layers the real basemap under the routes and credits the provider", async () => {
    const { container, basemap } = renderMap(async () => AVAILABLE, true);
    await waitFor(() => expect(container.querySelector("image.ps-map__basemap")).not.toBeNull());
    expect(basemap).toHaveBeenCalledWith({ south: 22.2819, west: 114.1577, north: 22.2855, east: 114.1581, width: 352, height: 416 });
    const image = container.querySelector("image.ps-map__basemap")!;
    expect(image.getAttribute("href")).toBe(`${AVAILABLE.image_url}?v=${encodeURIComponent(AVAILABLE.expires_at!)}`);
    expect(Number(image.getAttribute("width"))).toBeCloseTo(352, 6);
    expect(screen.getByText("底图：高德地图 · 虚线为示意线路")).toBeTruthy();
    expect(container.querySelector("[data-basemap]")?.getAttribute("data-basemap")).toBe("amap");
  });

  it("falls back to the labelled schematic map when the image fails or no basemap is offered", async () => {
    const { container, basemap } = renderMap(async () => AVAILABLE);
    await waitFor(() => expect(container.querySelector("image.ps-map__basemap")).not.toBeNull());
    fireEvent.error(container.querySelector("image.ps-map__basemap")!);
    await screen.findByText("示意地图 · 非真实底图");
    expect(container.querySelector("image.ps-map__basemap")).toBeNull();
    await waitFor(() => expect(basemap).toHaveBeenCalledTimes(2));

    const outside = renderMap(async () => ({ ...AVAILABLE, available: false, reason: "outside_region", image_url: null }));
    await waitFor(() => expect(outside.basemap).toHaveBeenCalled());
    expect(outside.container.querySelector("image.ps-map__basemap")).toBeNull();
    expect(outside.container.querySelector("[data-basemap]")?.getAttribute("data-basemap")).toBe("schematic");
  });
});
