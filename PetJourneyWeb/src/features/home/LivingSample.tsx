/** Internal-only composition, imported by output/design/living-sample, never by app routes. */
import { useMemo, useState } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import { apiClient } from "@/shared/api/client";
import { createQueryClient, queryKeys } from "@/shared/query/queryClient";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import { buildSlotRegistry, SlotProvider } from "@/shared/slots/Slot";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { resetFixtureEpoch } from "@/fixtures/world";
import { LivingCharacterContext } from "./HomeScene";
import rest from "./assets/living/sample-cat-photo-rest-v2.webp";
import sit from "./assets/living/sample-cat-photo-sit-v2.webp";
import bag from "./assets/living/travel-bag.webp";

export function LivingSample() {
  const [away, setAway] = useState(false);
  const sample = useMemo(() => {
    const modules = loadFeatureModules();
    const services = buildServices(modules, {
      mode: "fixture",
      api: apiClient,
    });
    const originalHome = services.world.home;
    const presence = { away: false };
    services.world = {
      ...services.world,
      home: async (petId, signal) => {
        const snapshot = await originalHome(petId, signal);
        return presence.away
          ? snapshot
          : {
              ...snapshot,
              presence: "at_home" as const,
              pet: { ...snapshot.pet, presence: "at_home" as const },
              journey: null,
              guard: {
                ...snapshot.guard,
                guarding: true,
                basis: "pet_at_home" as const,
              },
            };
      },
    };
    return {
      services,
      presence,
      query: createQueryClient(),
      slots: buildSlotRegistry(modules.flatMap((m) => m.slots ?? [])),
      router: createMemoryRouter(buildRoutes(modules), {
        initialEntries: ["/home"],
      }),
    };
  }, []);
  const change = (next: boolean) => {
    sample.presence.away = next;
    setAway(next);
    void sample.query.invalidateQueries({ queryKey: queryKeys.home });
    void sample.router.navigate("/home");
    window.scrollTo(0, 0);
  };
  return (
    <>
      <QueryClientProvider client={sample.query}>
        <ServicesProvider services={sample.services}>
          <SlotProvider registry={sample.slots}>
            <LivingCharacterContext.Provider
              value={{ petId: "fx-pet-001", rest, sit, bag }}
            >
              <RouterProvider router={sample.router} />
            </LivingCharacterContext.Provider>
          </SlotProvider>
        </ServicesProvider>
      </QueryClientProvider>
      <aside className="living-sample-controls" aria-label="画板外测试控制">
        <h2>交互样板 · 非真实账号</h2>
        <p>
          银灰猫依据你提供的照片制作，仅用于内部测试；暂沿用 fixture
          名字“团子”，不是对照片中猫姓名的认定。
        </p>
        <p>
          在家／外出由此测试开关控制，不冒充已完成真实出发。收获沿用现有 fixture
          结算，刷新会重置。播放使用自制测试音视频。
        </p>
        <button
          type="button"
          aria-pressed={!away}
          onClick={() => change(false)}
        >
          测试：在家
        </button>
        <button type="button" aria-pressed={away} onClick={() => change(true)}>
          测试：出门
        </button>
        <button
          type="button"
          onClick={() => {
            resetFixtureEpoch();
            sample.presence.away = true;
            setAway(true);
            void sample.query.invalidateQueries();
            void sample.router.navigate("/journey");
            window.scrollTo(0, 0);
          }}
        >
          测试：旅途与播放
        </button>
      </aside>
    </>
  );
}
