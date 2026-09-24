import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { HomeScene, LivingCharacterContext } from "@/features/home/HomeScene";
import {
  fixtureFarmAct,
  fixtureHomeSnapshot,
  fixtureSell,
} from "@/fixtures/home";
import {
  effectiveArrival,
  legProgress,
  remainingMs,
} from "@/shared/journey/vehicle";
import type { HomeSnapshot, LegTimes } from "@/shared/contracts";

afterEach(cleanup);
const sprites = {
  petId: "fx-pet-001",
  rest: "/test-rest.webp",
  sit: "/test-sit.webp",
  bag: "/test-bag.webp",
};
function Scene({ snapshot }: { snapshot: HomeSnapshot }) {
  return (
    <MemoryRouter>
      <LivingCharacterContext.Provider value={sprites}>
        <HomeScene snapshot={snapshot} />
      </LivingCharacterContext.Provider>
    </MemoryRouter>
  );
}

describe("layered home", () => {
  it("removes pet and bag when away without changing the space", () => {
    const snapshot = fixtureHomeSnapshot();
    const view = render(
      <Scene snapshot={{ ...snapshot, presence: "at_home" }} />,
    );
    const background = document
      .querySelector(".ps-living-background")
      ?.getAttribute("src");
    expect(screen.getByTestId("home-pet")).toBeTruthy();
    expect(screen.getByTestId("home-bag")).toBeTruthy();
    view.rerender(<Scene snapshot={{ ...snapshot, presence: "in_transit" }} />);
    expect(screen.queryByTestId("home-pet")).toBeNull();
    expect(screen.queryByTestId("home-bag")).toBeNull();
    expect(screen.getByTestId("home-cup")).toBeTruthy();
    expect(
      document.querySelector(".ps-living-background")?.getAttribute("src"),
    ).toBe(background);
  });
  it("does not use the internal cat for any other pet", () => {
    const snapshot = fixtureHomeSnapshot();
    render(
      <Scene
        snapshot={{
          ...snapshot,
          presence: "at_home",
          pet: { ...snapshot.pet, pet_id: "another-pet" },
        }}
      />,
    );
    expect(document.querySelector('img[src="/test-rest.webp"]')).toBeNull();
  });
  it("opens the same interior from its explicit room control", () => {
    render(
      <Scene snapshot={{ ...fixtureHomeSnapshot(), presence: "at_home" }} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "屋内" }));
    expect(screen.getByRole("region", { name: "共同的家·屋内" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /第 1 块菜地/ })).toBeNull();
  });
  it("places the pet action sheet above scene clipping, then restores keyboard focus", () => {
    render(
      <Scene snapshot={{ ...fixtureHomeSnapshot(), presence: "at_home" }} />,
    );
    const pet = screen.getByRole("button", { name: "看看 团子" });
    pet.focus();
    fireEvent.click(pet);
    // 小窝里的东西点到先冒出名字与能做的事（claude-6c2b 小窝二级页），面板从气泡里的“陪 TA 待一会儿”打开。
    fireEvent.click(screen.getByRole("button", { name: "陪 TA 待一会儿" }));
    expect(screen.getByRole("dialog").parentElement).toBe(document.body);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(pet);
  });
  it("harvest settles inventory only, retries once, then selling changes the wallet", () => {
    const before = fixtureHomeSnapshot();
    const plot = before.plots.find((p) => p.stage === "ripe")!;
    const input = {
      home_id: before.home_id,
      plot_id: plot.plot_id,
      cycle_id: plot.cycle_id,
      action: "harvest" as const,
    };
    fixtureFarmAct(input, "living-harvest-test");
    const after = fixtureHomeSnapshot();
    expect(after.plots.find((p) => p.plot_id === plot.plot_id)?.stage).toBe(
      "harvested",
    );
    expect(after.wallet.balance).toBe(before.wallet.balance);
    expect(after.pantry.find((p) => p.item_key === plot.crop_key)!.qty).toBe(
      before.pantry.find((p) => p.item_key === plot.crop_key)!.qty + 3,
    );
    fixtureFarmAct(input, "living-harvest-test");
    expect(fixtureHomeSnapshot().pantry).toEqual(after.pantry);
    const sale = fixtureSell(plot.crop_key!, 1, "living-sale-test");
    expect(sale.wallet.balance).toBe(after.wallet.balance + sale.gained_coins);
    expect(sale.gained_coins).toBeGreaterThan(0);
  });
});

it("uses one time anchor across a UTC+8 to UTC+9 journey", () => {
  const times = {
    planned_departure_utc: "2026-09-22T08:20:00Z",
    planned_arrival_utc: "2026-09-22T10:43:00Z",
    actual_departure_utc: null,
    estimated_departure_utc: null,
    actual_arrival_utc: null,
    estimated_arrival_utc: null,
    origin_timezone: "Asia/Shanghai",
    destination_timezone: "Asia/Tokyo",
  } as LegTimes;
  const now = Date.parse("2026-09-22T09:00:00Z");
  expect(legProgress(times, now)).toBeCloseTo(40 / 143);
  expect(remainingMs(times, now)).toBe(103 * 60_000);
  expect(effectiveArrival(times) - now).toBe(remainingMs(times, now));
});
