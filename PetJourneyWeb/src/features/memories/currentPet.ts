/**
 * 新版全屏页（回忆 /memories、我的 /me）读“当前这只宠物”的唯一入口，必须在 WorldGate 里用。
 * - live：WorldGate 里的 HouseholdProvider 已按 /households 校验过当前家庭与宠物，直接用，不再额外请求。
 * - fixture：家庭上下文是空的，用演示世界家园快照里的样板宠物（与地图演示剧本、小窝是同一只）。
 * 这里只搬运事实字段（名字、照片地址），不补任何形象；头像由 PetPortrait 决定怎么画（不写名字首字）。
 */
import { useQuery } from "@tanstack/react-query";
import type { HouseholdBrief, PetSpecies } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useCurrentHousehold } from "@/shared/session/householdContext";

export interface CurrentPet {
  petId: string;
  name: string;
  species: PetSpecies;
  photoUrl: string | null;
}

export type CurrentPetState =
  | { status: "pending" }
  | { status: "error"; error: unknown; retry: () => void }
  | { status: "ready"; pet: CurrentPet | null; userId: string | null; household: HouseholdBrief | null };

export function useCurrentPet(): CurrentPetState {
  const services = useServices();
  const { userId, pet, household } = useCurrentHousehold();
  const live = env.dataMode === "live";
  // 与 useActiveHome 在 fixture 下是同一个键、同一个请求，缓存共用；live 下不发。
  const demoHome = useQuery({
    queryKey: queryKeys.home,
    queryFn: ({ signal }) => services.world.home(pet?.pet_id ?? null, signal),
    enabled: !live,
  });
  if (live) {
    return {
      status: "ready",
      pet: pet ? { petId: pet.pet_id, name: pet.name, species: pet.species, photoUrl: pet.photo_url } : null,
      userId,
      household,
    };
  }
  if (demoHome.isPending) return { status: "pending" };
  if (demoHome.isError) return { status: "error", error: demoHome.error, retry: () => void demoHome.refetch() };
  const demoPet = demoHome.data.pet;
  return {
    status: "ready",
    pet: { petId: demoPet.pet_id, name: demoPet.name, species: demoPet.species, photoUrl: demoPet.photo_url },
    userId: null,
    household: demoHome.data.household ?? null,
  };
}
