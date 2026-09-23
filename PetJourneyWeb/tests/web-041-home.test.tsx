import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { HomeSnapshot, HouseholdBrief } from "@/shared/contracts";
import { cropVisual } from "@/features/farm/cropVisual";
import { HouseholdProvider, useActiveHome, useCurrentHousehold } from "@/shared/session/householdContext";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "live", isDev: false, apiBase: "/api/v1/web" } }));

const household = {
  household_id: "house-1", name: "同一个家", home_id: "home-1", role: "admin", home_activated: true, member_count: 1,
  pets: [
    { pet_id: "pet-a", name: "奶茶", species: "cat", photo_url: "/a.jpg", origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-23T00:00:00Z", added_by_you: true },
    { pet_id: "pet-b", name: "小布", species: "dog", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-23T00:01:00Z", added_by_you: true },
  ],
} as HouseholdBrief;

function snapshot(petId: string, name: string) {
  return { pet: { pet_id: petId, name } } as HomeSnapshot;
}

function Probe() {
  const { pet } = useCurrentHousehold();
  const home = useActiveHome();
  return <>
    <output data-testid="selected-pet">{pet?.name}</output>
    <output data-testid="server-pet">{home.data?.pet.name ?? "读取中"}</output>
  </>;
}

beforeEach(() => sessionStorage.clear());

describe("0.4.1 household and visual identity", () => {
  it("uses a crop-specific mature illustration and an honest generic growing stage", () => {
    expect(cropVisual("sun_pea", "ripe")).toContain("crop-pea-v1.webp");
    expect(cropVisual("moon_radish", "ripe")).toContain("crop-radish-v1.webp");
    expect(cropVisual("star_tomato", "ripe")).toContain("crop-tomato.webp");
    expect(cropVisual("moon_radish", "growing")).toContain("crop-sprouts.webp");
  });

  it("switches pets without projecting a late old-home result into the new pet", async () => {
    let resolveOld: ((value: HomeSnapshot) => void) | undefined;
    let oldSignal: AbortSignal | undefined;
    const home = vi.fn((petId: string | null, signal?: AbortSignal) => {
      if (petId === "pet-a") {
        oldSignal = signal;
        return new Promise<HomeSnapshot>((resolve) => { resolveOld = resolve; });
      }
      return Promise.resolve(snapshot("pet-b", "小布"));
    });
    const services = {
      households: { list: async () => [household] },
      world: { home },
    } as unknown as ServiceMap;
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><ServicesProvider services={services}><MemoryRouter>
      <HouseholdProvider userId="owner-1"><Probe /></HouseholdProvider>
    </MemoryRouter></ServicesProvider></QueryClientProvider>);

    await waitFor(() => expect(home).toHaveBeenCalledWith("pet-a", expect.any(AbortSignal)));
    expect(screen.getByTestId("selected-pet").textContent).toBe("奶茶");
    fireEvent.click(screen.getByRole("button", { name: "查看 小布，同一个家" }));
    await waitFor(() => expect(screen.getByTestId("server-pet").textContent).toBe("小布"));
    expect(screen.getByTestId("selected-pet").textContent).toBe("小布");
    expect(oldSignal?.aborted).toBe(true);
    await act(async () => { resolveOld?.(snapshot("pet-a", "奶茶")); });
    expect(screen.getByTestId("server-pet").textContent).toBe("小布");
    expect(sessionStorage.getItem("petsoul:current-pet:owner-1")).toBe("pet-b");
  });
});
