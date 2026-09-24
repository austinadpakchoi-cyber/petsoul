/**
 * claude-6c2b · 切换当前宠物（新导航）：切宠物是换上下文，不是导航——留在当前页；
 * 只有停在上一只宠物的某条具体记录上（证件、到访、攻略、驾考、寻味推荐）才退回对应列表。
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import type { HouseholdBrief } from "@/shared/contracts";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider, listForPetScopedPath, useCurrentHousehold } from "@/shared/session/householdContext";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "live", isDev: false, apiBase: "/api/v1/web" } }));

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

describe("listForPetScopedPath", () => {
  it.each([
    ["/credentials/c-1", "/life"],
    ["/visits/v-9", "/map"],
    ["/guides/g-2", "/guides"],
    ["/school/session/s-1", "/school"],
    ["/school/result/s-1", "/school"],
    ["/journey/food/r-3", "/journey/food"],
  ])("%s → %s", (path, list) => expect(listForPetScopedPath(path)).toBe(list));

  it.each(["/map", "/memories", "/me", "/communicator", "/garden", "/life", "/guides", "/school", "/pets/p-1", "/homes/h-2"])("%s 留在原地", (path) => {
    expect(listForPetScopedPath(path)).toBeNull();
  });
});

const household = {
  household_id: "hh-1",
  name: "我们的家",
  role: "admin",
  home_activated: true,
  pets: [
    { pet_id: "p-1", name: "栗子", species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true },
    { pet_id: "p-2", name: "豆包", species: "dog", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-21T00:00:00Z", added_by_you: true },
  ],
} as unknown as HouseholdBrief;

function CurrentPet() {
  const { pet } = useCurrentHousehold();
  return <p data-testid="current">{pet?.name}</p>;
}

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const services = { households: { list: async () => [household] } } as unknown as ServiceMap;
  const element = (
    <HouseholdProvider userId="u-1">
      <CurrentPet />
    </HouseholdProvider>
  );
  const router = createMemoryRouter(
    [
      { path: "*", element },
      { path: "/life", element: <p>证件卡包列表</p> },
    ],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <RouterProvider router={router} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return router;
}

describe("切换当前宠物", () => {
  it("在“回忆”里切宠物：留在当前页，当前宠物换成新选的那只", async () => {
    const router = renderAt("/memories");
    expect((await screen.findByTestId("current")).textContent).toBe("栗子");
    fireEvent.click(screen.getByRole("button", { name: /查看 豆包/ }));
    expect((await screen.findByTestId("current")).textContent).toBe("豆包");
    expect(router.state.location.pathname).toBe("/memories");
  });

  it("停在上一只宠物的证件上切宠物：退回证件卡包列表，不显示错宠物的证件", async () => {
    const router = renderAt("/credentials/c-1");
    await screen.findByTestId("current");
    fireEvent.click(screen.getByRole("button", { name: /查看 豆包/ }));
    expect(await screen.findByText("证件卡包列表")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/life");
  });
});
