import { createContext, useContext, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router";
import type { HomeSnapshot, HouseholdBrief, HouseholdPetBrief } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { ErrorState, LoadingState, Page, PetAvatar } from "@/shared/ui";
import "./householdContext.css";

type AvailablePet = { household: HouseholdBrief; pet: HouseholdPetBrief };
type Selection = { userId: string; petId: string };
type HouseholdContextValue = {
  userId: string | null;
  household: HouseholdBrief | null;
  pet: HouseholdPetBrief | null;
  pets: AvailablePet[];
  selectPet(petId: string): void;
};

const HouseholdContext = createContext<HouseholdContextValue | null>(null);

/**
 * 属于“某一只宠物的某条具体记录”的页面（证件、到访、攻略、驾考考局与成绩、寻味推荐）：切到别的宠物后留在原地会指向上一只的东西，
 * 所以退回对应的列表；其余页面（地图、通讯器、回忆、我的、菜园、别人的公开主页……）留在原地。
 */
export function listForPetScopedPath(pathname: string): string | null {
  const rules: Array<[RegExp, string]> = [
    [/^\/credentials\/[^/]+/, "/life"],
    [/^\/visits\/[^/]+/, "/map"],
    [/^\/guides\/[^/]+/, "/guides"],
    [/^\/school\/(session|result)\/[^/]+/, "/school"],
    [/^\/journey\/food\/[^/]+/, "/journey/food"],
  ];
  return rules.find(([re]) => re.test(pathname))?.[1] ?? null;
}

function preferredPet(userId: string): string | null {
  try { return sessionStorage.getItem(`petsoul:current-pet:${userId}`); } catch { return null; }
}

/** 仅存 UI 选中项；家庭/宠物归属始终重新从 /households 校验。 */
export function HouseholdProvider({ userId, children }: { userId: string | null; children: ReactNode }) {
  const { households } = useServices();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const [selection, setSelection] = useState<Selection | null>(null);
  const list = useQuery({ queryKey: queryKeys.households(userId ?? "-"), queryFn: () => households.list(), enabled: env.dataMode === "live" && Boolean(userId), staleTime: 15_000 });

  if (env.dataMode === "fixture") return <HouseholdContext.Provider value={{ userId: null, household: null, pet: null, pets: [], selectPet: () => undefined }}>{children}</HouseholdContext.Provider>;
  if (list.isPending) return <Page><LoadingState lines={2} label="正在确认这个家和宠物…" /></Page>;
  if (list.isError) return <Page><ErrorState error={list.error} onRetry={() => void list.refetch()} /></Page>;

  const pets = list.data.flatMap((household) => household.home_activated ? household.pets.filter((pet) => pet.join_step === "moved_in").map((pet) => ({ household, pet })) : []);
  const preferred = selection?.userId === userId ? selection.petId : userId ? preferredPet(userId) : null;
  const active = pets.find(({ pet }) => pet.pet_id === preferred) ?? pets[0] ?? null;
  if (!active) return <Page><p role="status">当前账号没有可查看的已入住房间。请返回入住流程，或稍后重试。</p></Page>;

  const selectPet = (petId: string) => {
    if (!userId || petId === active.pet.pet_id || !pets.some(({ pet }) => pet.pet_id === petId)) return;
    // 先切到新 key，再清除旧宠物远端结果；旧请求即使晚到也不能投影到新 key。
    setSelection({ userId, petId });
    try { sessionStorage.setItem(`petsoul:current-pet:${userId}`, petId); } catch { /* 私密浏览器仍可在当前页切换 */ }
    void queryClient.cancelQueries({ predicate: (query) => !["identity", "households", "platform"].includes(String(query.queryKey[0])) });
    queryClient.removeQueries({ predicate: (query) => !["identity", "households", "platform"].includes(String(query.queryKey[0])) });
    // 切宠物是换上下文、不是导航：留在当前页，按新宠物重新读。只有停在上一只宠物某条具体记录上时才退回对应列表。
    const fallback = listForPetScopedPath(location.pathname);
    if (fallback) navigate(fallback, { replace: true });
  };
  return <HouseholdContext.Provider value={{ userId, household: active.household, pet: active.pet, pets, selectPet }}>
    {pets.length > 1 ? <div className="ps-current-pet-bar" aria-label="当前家庭与宠物">
      <span>{active.household.name || "我们的家"}</span>
    <div role="group" aria-label="切换当前宠物">
        {pets.map(({ household, pet }) => <button key={pet.pet_id} type="button" aria-pressed={pet.pet_id === active.pet.pet_id} aria-label={`查看 ${pet.name}，${household.name || "同一个家"}`} onClick={() => selectPet(pet.pet_id)}>
          <PetAvatar petId={pet.pet_id} name={pet.name} species={pet.species} photoUrl={pet.photo_url} size={26} />
          <strong>{pet.name}</strong>
        </button>)}
      </div>
    </div> : null}
    {children}
  </HouseholdContext.Provider>;
}

export function useCurrentHousehold(): HouseholdContextValue {
  const value = useContext(HouseholdContext);
  if (!value) throw new Error("当前家庭必须在 HouseholdProvider 内读取");
  return value;
}

/** Bare fixture tests can omit the provider; live route guards always provide it. */
export function useOptionalCurrentHousehold(): HouseholdContextValue | null {
  return useContext(HouseholdContext);
}

/** 所有主页面通过同一个宠物 ID 与用户 ID 请求家园；prefix 仍兼容既有写操作失效。 */
export function useActiveHome(options: { staleTime?: number; refetchInterval?: number } = {}) {
  const { world } = useServices();
  const { userId, pet } = useCurrentHousehold();
  const petId = pet?.pet_id ?? null;
  return useQuery<HomeSnapshot>({
    queryKey: env.dataMode === "fixture" ? queryKeys.home : queryKeys.homeFor(userId ?? "-", petId ?? "-"),
    queryFn: ({ signal }) => world.home(petId, signal),
    enabled: env.dataMode === "fixture" || Boolean(userId && petId),
    staleTime: options.staleTime,
    refetchInterval: options.refetchInterval,
  });
}
