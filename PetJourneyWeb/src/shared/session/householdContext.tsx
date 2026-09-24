import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { matchPath, useLocation, useNavigate } from "react-router";
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

/** 切换栏的样子：整条栏 / 场景上的小胶囊 / 只切家的小控件（地图）/ 不显示。 */
export type PetBarMode = "bar" | "capsule" | "household" | "none";

/**
 * 切换栏只在“按宠物区分”的页面出现。这是显式清单：每条已注册的路由都必须归到其中一类，
 * tests/claude-6c2b-pet-bar-routes.test.tsx 会逐条核对，新路由漏归类就红。
 * - bar：内容跟着当前宠物变的页面，顶上一条切换栏；
 * - capsule：整屏场景页，切换栏收成浮在场景上方的小胶囊，不把场景往下推；
 * - household：地图。一个家的几只本来就画在同一张图上，所以不切宠物；只有宠物分在不止一个家时，才出现一个只切家的小控件；
 * - none：不按宠物区分的页面（设置、邻居与邻居家、朋友圈、公告、别人的主页、我的举报、添伙伴），
 *   进行中的考试与颁证典礼（只属于这一只，回驾校首页再切），以及入住前、没有家庭上下文的页面。
 * 不在清单里的路径（404、“/” 的跳转）一律不显示。
 */
export const PET_BAR_ROUTES: Readonly<Record<PetBarMode, readonly string[]>> = {
  bar: [
    "/communicator", "/memories", "/timeline", "/me", "/me/dna", "/me/look",
    "/life", "/credentials/:credentialId", "/collection", "/market", "/photos",
    "/journey", "/journey/food", "/journey/food/:recommendationId",
    "/guides", "/guides/:guideId", "/guides/wish", "/guides/plan/:planId",
    "/school", "/school/subject/:subject", "/school/result/:sessionId",
    "/visits/:visitId", "/households/manage", "/onboarding/reception",
  ],
  capsule: ["/home", "/garden"],
  household: ["/map"],
  none: [
    "/settings", "/neighbors", "/homes/:homeId", "/circle", "/posts/:postId", "/pets/:petId", "/announcements",
    "/me/reports", "/pets/new", "/school/session/:sessionId", "/school/ceremony", "/school/try",
    "/welcome", "/register", "/login", "/join", "/onboarding", "/onboarding/choice", "/onboarding/move-in", "/onboarding/notes",
    "/adopt", "/world", "/world/residents/:petId",
  ],
};

const MODES: readonly PetBarMode[] = ["bar", "capsule", "household", "none"];

export function petBarModeFor(pathname: string): PetBarMode {
  return MODES.find((mode) => PET_BAR_ROUTES[mode].some((path) => matchPath({ path, end: true }, pathname))) ?? "none";
}

/** 胶囊在各场景页上的位置（按页面自己的顶部布局让开返回、标题、金币和“庭院 / 屋内”），见 householdContext.css。 */
const CAPSULE_PLACEMENT: Readonly<Record<string, string>> = { "/home": "home", "/garden": "garden" };

/**
 * 家的称呼：起了名就用名字；没起名用“第一只已入住宠物的名字＋的家”；家里还没有已入住的宠物，才按它在这个人的家庭列表里的顺序叫“家庭 1 / 家庭 2”。
 */
export function householdLabel(household: HouseholdBrief, index: number): string {
  const name = household.name?.trim();
  if (name) return name;
  const first = household.pets.find((pet) => pet.join_step === "moved_in");
  return first ? `${first.name}的家` : `家庭 ${index + 1}`;
}

/** 同一个人的几个家叫出来撞了（例如两个家的第一只都叫奶茶）：撞名的几个都在后面带上它在列表里的序号，与“家庭 N”同一套顺序。 */
export function householdLabels(households: HouseholdBrief[]): Map<string, string> {
  const base = households.map((household, index) => householdLabel(household, index));
  return new Map(households.map((household, index) => [
    household.household_id,
    base.filter((label) => label === base[index]).length > 1 ? `${base[index]}（${index + 1}）` : base[index],
  ]));
}

/**
 * 页面里要叫这个家时用（例如“我们的家”的大标题）：与切换栏读同一份 /households 缓存、同一套称呼（撞名带序号）。
 * 演示模式或还没有账号时没有列表，返回 null，由调用方退回 householdLabel。
 */
export function useHouseholdLabels(userId: string | null): Map<string, string> | null {
  const { households } = useServices();
  const list = useQuery({ queryKey: queryKeys.households(userId ?? "-"), queryFn: () => households.list(), enabled: env.dataMode === "live" && Boolean(userId), staleTime: 15_000 });
  return list.data ? householdLabels(list.data) : null;
}

function preferredPet(userId: string): string | null {
  try { return sessionStorage.getItem(`petsoul:current-pet:${userId}`); } catch { return null; }
}

function PetSwitcher({ variant, placement, label, pets, activePetId, labelOf, onSelect }: {
  variant: "bar" | "capsule";
  placement: string;
  label: string;
  pets: AvailablePet[];
  activePetId: string;
  labelOf(household: HouseholdBrief): string;
  onSelect(petId: string): void;
}) {
  const group = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // 窄屏上当前那只可能在横向可视范围外（例如选的是第三只，换页后栏重挂）：把它滚进来；block: nearest 不动页面的纵向位置。
    group.current?.querySelector<HTMLElement>('[aria-pressed="true"]')?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [activePetId]);
  const bar = <div className={`ps-current-pet-bar${variant === "capsule" ? " ps-current-pet-bar--capsule" : ""}`} aria-label="当前家庭与宠物">
    {variant === "bar" ? <span>{label}</span> : null}
    <div ref={group} role="group" aria-label="切换当前宠物">
      {pets.map(({ household, pet }) => <button key={pet.pet_id} type="button" aria-pressed={pet.pet_id === activePetId} aria-label={`查看 ${pet.name}，${labelOf(household)}`} onClick={() => onSelect(pet.pet_id)}>
        <PetAvatar petId={pet.pet_id} name={pet.name} species={pet.species} photoUrl={pet.photo_url} size={26} />
        <strong>{pet.name}</strong>
      </button>)}
    </div>
  </div>;
  // 胶囊挂在零高度的锚点里：锚点留在原来切换栏的位置（开发时的模式条下面也一样），场景不被往下推。
  return variant === "capsule" ? <div className={`ps-pet-capsule-anchor ps-pet-capsule-anchor--${placement}`}>{bar}</div> : bar;
}

function HouseholdSwitcher({ households, activeId, labelOf, onSelect }: {
  households: HouseholdBrief[];
  activeId: string;
  labelOf(household: HouseholdBrief): string;
  onSelect(householdId: string): void;
}) {
  const group = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // 与宠物栏同一个做法：窄屏上选中的那个家可能在横向可视范围外（例如选了第二个家，离开地图再回来控件重挂）：把它滚进来。
    group.current?.querySelector<HTMLElement>('[aria-pressed="true"]')?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [activeId]);
  return <div ref={group} className="ps-household-switch" role="group" aria-label="切换当前的家">
    {households.map((household) => <button key={household.household_id} type="button" aria-pressed={household.household_id === activeId} onClick={() => onSelect(household.household_id)}>
      {labelOf(household)}
    </button>)}
  </div>;
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
  const labels = householdLabels(list.data);
  const labelOf = (household: HouseholdBrief) => labels.get(household.household_id) ?? householdLabel(household, 0);
  const mode = petBarModeFor(location.pathname);
  const petHouseholds = pets.map(({ household }) => household).filter((household, index, all) => all.findIndex((item) => item.household_id === household.household_id) === index);
  let switcher: ReactNode = null;
  if ((mode === "bar" || mode === "capsule") && pets.length > 1) {
    switcher = <PetSwitcher variant={mode} placement={CAPSULE_PLACEMENT[location.pathname] ?? "home"} label={labelOf(active.household)} pets={pets} activePetId={active.pet.pet_id} labelOf={labelOf} onSelect={selectPet} />;
  } else if (mode === "household" && petHouseholds.length > 1) {
    // 只切家：换到那个家里排在前面的那只（地图按当前宠物所在的家画，一个家的几只都在图上）。
    switcher = <HouseholdSwitcher households={petHouseholds} activeId={active.household.household_id} labelOf={labelOf} onSelect={(householdId) => {
      const target = pets.find(({ household }) => household.household_id === householdId);
      if (target) selectPet(target.pet.pet_id);
    }} />;
  }
  return <HouseholdContext.Provider value={{ userId, household: active.household, pet: active.pet, pets, selectPet }}>
    {switcher}
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
