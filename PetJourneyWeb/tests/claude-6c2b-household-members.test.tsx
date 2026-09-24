/**
 * claude-6c2b（分身）· 我们的家 · 成员管理（方案第 9 节：管理员可移除成员、调整角色）。
 * - 非管理员看不到“移除”“调整角色”；管理员对别人才有“移除”，自己那一行没有；
 *   你是唯一管理员时，自己那一行不给“改为共同照顾者”（家里不能没有管理员），还有别的管理员时才给。
 * - 每个动作二次确认、写清后果：移除后对方看不到这个家和家里的伙伴；选“先不”什么都不发。
 * - 成功：调用带对的家庭编号与成员编号；刷新家庭详情与 households 列表（切换宠物栏读的就是它）。
 * - 拒绝按原因码说人话（409 last_admin、403 admin_required、404 member_not_found、CSRF、断网），码收进“技术信息”；
 *   403 / 404 说明情况变了，顺手刷新。
 * - 演示模式：成员接口抛能力未接入，不编成员变动。
 */
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import type { HouseholdBrief, HouseholdDetail, HouseholdMember, HouseholdRole, PetRelationship } from "@/shared/contracts";
import { ApiError, isApiError } from "@/shared/api/errors";
import { createApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import { queryKeys } from "@/shared/query/queryClient";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { HouseholdPage } from "@/features/household/HouseholdPage";
import { memberActionFailure } from "@/features/household/MembersCard";

const mode = vi.hoisted(() => ({ dataMode: "live" as "fixture" | "live" }));
vi.mock("@/shared/config/env", () => ({
  env: {
    get dataMode() {
      return mode.dataMode;
    },
    isDev: false,
    apiBase: "/api/v1/web",
  },
}));

beforeEach(() => {
  mode.dataMode = "live";
  sessionStorage.clear();
  vi.stubGlobal("scrollTo", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/* ---------------- 测试数据 ---------------- */

const brief: HouseholdBrief = {
  household_id: "house-1",
  name: "海边的家",
  home_id: "home-1",
  role: "admin",
  home_activated: true,
  member_count: 3,
  pets: [{ pet_id: "pet-a", name: "奶茶", species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true }],
};

const member = (user_id: string, display_name: string, role: HouseholdRole, is_you = false): HouseholdMember => ({ user_id, display_name, role, joined_at: "2026-09-20T00:00:00Z", is_you });
const ME = member("owner-1", "小林", "admin", true);
const MOM = member("user-mom", "妈妈", "caregiver");
const BRO = member("user-bro", "哥哥", "admin");
const ADMIN_PERMS = ["view", "care", "spend", "manage"];
const CAREGIVER_PERMS = ["view", "care"];

const detailOf = (members: HouseholdMember[], permissions: string[] = ADMIN_PERMS): HouseholdDetail => ({
  household: { ...brief, member_count: members.length },
  members,
  settings: { name: "海边的家", caregivers_can_spend: false, generated_photos: false, pet_messages: true, public_posts: false },
  your_permissions: permissions,
  version: 1,
});

const relationship: PetRelationship = { pet_id: "pet-a", owner_title: null, relation_label: null, updated_at: null };

const rejection = (status: number, code: ApiError["code"], reason: string) =>
  new ApiError({ kind: "http", status, code, message: "后端原话（不直接给玩家看）", requestId: "req-42", details: { reason } });

/* ---------------- 渲染 ---------------- */

function strictServices(services: Record<string, unknown>): ServiceMap {
  return new Proxy(services as unknown as ServiceMap, {
    get(target, prop: string) {
      if (prop in target) return target[prop as keyof ServiceMap];
      throw new Error(`unexpected service ${prop}`);
    },
  });
}

function renderHousehold(households: Record<string, unknown>, element: ReactElement = <HouseholdPage />) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidated: string[] = [];
  const original = client.invalidateQueries.bind(client);
  client.invalidateQueries = ((filters?: { queryKey?: readonly unknown[] }) => {
    invalidated.push(JSON.stringify(filters?.queryKey ?? null));
    return original(filters);
  }) as typeof client.invalidateQueries;
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={strictServices({ households })}>
        <MemoryRouter initialEntries={["/households/manage"]}>
          <Routes>
            <Route path="/households/manage" element={<HouseholdProvider userId="owner-1">{element}</HouseholdProvider>} />
          </Routes>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { client, invalidated };
}

/** live 家庭服务：detail 每次读 state.current；removeMember / setMemberRole 用给定的实现。 */
function liveHouseholds(first: HouseholdDetail, impl: { removeMember?: (h: string, u: string) => Promise<void>; setMemberRole?: (h: string, u: string, r: HouseholdRole) => Promise<HouseholdDetail> } = {}) {
  const state = { current: first };
  const list = vi.fn(async () => [brief]);
  const detail = vi.fn(async () => state.current);
  const removeMember = vi.fn(impl.removeMember ?? (async () => undefined));
  const setMemberRole = vi.fn(impl.setMemberRole ?? (async () => state.current));
  const households = { list, detail, invites: async () => [], relationship: async () => relationship, saveRelationship: async () => relationship, removeMember, setMemberRole };
  return { state, list, detail, removeMember, setMemberRole, households };
}

const card = () => screen.getByRole("heading", { level: 2, name: "一起照顾 TA 的人" }).closest(".ps-family-card") as HTMLElement;
const rowOf = (name: string) => within(card()).getByText((text) => text.startsWith(name)).closest(".ps-member") as HTMLElement;
const confirmBox = (name: string) => screen.getByRole("group", { name: `确认：${name}` });
const DETAIL_KEY = JSON.stringify(queryKeys.householdDetail("owner-1", "house-1"));
const LIST_KEY = JSON.stringify(queryKeys.households("owner-1"));

/* ---------------- 看得到什么 ---------------- */

describe("成员管理：谁能看到按钮", () => {
  it("非管理员（共同照顾者）：只看名单，没有“移除”“设为管理员”“改为共同照顾者”", async () => {
    const api = liveHouseholds(detailOf([member("owner-1", "小林", "caregiver", true), member("user-admin", "妈妈", "admin")], CAREGIVER_PERMS));
    renderHousehold(api.households);
    await screen.findByRole("heading", { level: 2, name: "一起照顾 TA 的人" });
    expect(card().textContent).toContain("妈妈");
    expect(within(card()).queryAllByRole("button")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: /移除|设为管理员|改为共同照顾者/ })).toBeNull();
  });

  it("管理员：别人那一行有“移除”和按现角色给的调整；自己那一行没有“移除”；你是唯一管理员时自己不给降级，并说明怎么交出", async () => {
    const api = liveHouseholds(detailOf([ME, MOM]));
    renderHousehold(api.households);
    await screen.findByRole("heading", { level: 2, name: "一起照顾 TA 的人" });
    const mom = rowOf("妈妈");
    expect(within(mom).getByRole("button", { name: "移除" })).toBeTruthy();
    expect(within(mom).getByRole("button", { name: "设为管理员" })).toBeTruthy();
    const me = rowOf("小林");
    expect(within(me).queryAllByRole("button")).toHaveLength(0);
    expect(card().textContent).toContain("你是这个家唯一的管理员；想交出管理员，先把另一位家人设为管理员。");
  });

  it("管理员：家里还有别的管理员时，自己那一行可以“改为共同照顾者”（仍然不能移除自己）；另一位管理员那一行是“改为共同照顾者”", async () => {
    const api = liveHouseholds(detailOf([ME, BRO, MOM]));
    renderHousehold(api.households);
    await screen.findByRole("heading", { level: 2, name: "一起照顾 TA 的人" });
    const me = rowOf("小林");
    expect(within(me).getByRole("button", { name: "改为共同照顾者" })).toBeTruthy();
    expect(within(me).queryByRole("button", { name: "移除" })).toBeNull();
    expect(within(rowOf("哥哥")).getByRole("button", { name: "改为共同照顾者" })).toBeTruthy();
    expect(card().textContent).not.toContain("唯一的管理员");
  });
});

/* ---------------- 二次确认与成功 ---------------- */

describe("成员管理：二次确认与成功后的刷新", () => {
  it("移除要二次确认、写清后果；“先不”什么都不发；确定后带对编号发出，提示已移除，并刷新家庭详情与 households 列表", async () => {
    const api = liveHouseholds(detailOf([ME, MOM]));
    const { invalidated } = renderHousehold(api.households);
    await screen.findByRole("heading", { level: 2, name: "一起照顾 TA 的人" });

    fireEvent.click(within(rowOf("妈妈")).getByRole("button", { name: "移除" }));
    // “TA 们”之间是不换行空格（窄屏不拆行），用 \s 匹配。
    expect(confirmBox("妈妈").textContent).toMatch(/移除后，妈妈将看不到这个家和家里的伙伴，也不能再照顾 TA\s们；想让 TA 回来，需要重新邀请。/);
    fireEvent.click(within(confirmBox("妈妈")).getByRole("button", { name: "先不" }));
    expect(screen.queryByRole("group", { name: "确认：妈妈" })).toBeNull();
    expect(api.removeMember).not.toHaveBeenCalled();

    fireEvent.click(within(rowOf("妈妈")).getByRole("button", { name: "移除" }));
    api.state.current = detailOf([ME]);
    fireEvent.click(within(confirmBox("妈妈")).getByRole("button", { name: "确定移除" }));
    expect(await screen.findByText("已移除妈妈。")).toBeTruthy();
    expect(api.removeMember).toHaveBeenCalledWith("house-1", "user-mom");
    expect(invalidated).toContain(DETAIL_KEY);
    expect(invalidated).toContain(LIST_KEY);
    await waitFor(() => expect(within(card()).queryByText((text) => text.startsWith("妈妈"))).toBeNull());
    expect(api.setMemberRole).not.toHaveBeenCalled();
  });

  it("设为管理员也要确认（说清对方能做什么）；成功用返回的最新详情，并刷新家庭详情与列表", async () => {
    const promoted = detailOf([ME, member("user-mom", "妈妈", "admin")]);
    const api = liveHouseholds(detailOf([ME, MOM]), { setMemberRole: async () => promoted });
    const { invalidated } = renderHousehold(api.households);
    await screen.findByRole("heading", { level: 2, name: "一起照顾 TA 的人" });
    fireEvent.click(within(rowOf("妈妈")).getByRole("button", { name: "设为管理员" }));
    expect(confirmBox("妈妈").textContent).toContain("设为管理员后，妈妈可以管理家人、发出邀请、修改家里的约定，也能移除其他家人（包括你）");
    api.state.current = promoted;
    fireEvent.click(within(confirmBox("妈妈")).getByRole("button", { name: "确定设为管理员" }));
    expect(await screen.findByText("已把妈妈设为管理员。")).toBeTruthy();
    expect(api.setMemberRole).toHaveBeenCalledWith("house-1", "user-mom", "admin");
    expect(invalidated).toContain(DETAIL_KEY);
    expect(invalidated).toContain(LIST_KEY);
    await waitFor(() => expect(within(rowOf("妈妈")).getByRole("button", { name: "改为共同照顾者" })).toBeTruthy());
  });

  it("交出自己的管理员（还有别的管理员时）：确认里说清你将不能再管理；发出的是自己的编号", async () => {
    const api = liveHouseholds(detailOf([ME, BRO]), { setMemberRole: async () => detailOf([member("owner-1", "小林", "caregiver", true), BRO], CAREGIVER_PERMS) });
    renderHousehold(api.households);
    await screen.findByRole("heading", { level: 2, name: "一起照顾 TA 的人" });
    fireEvent.click(within(rowOf("小林")).getByRole("button", { name: "改为共同照顾者" }));
    expect(confirmBox("小林").textContent).toContain("改为共同照顾者后，你就不能再管理家人和家里的约定了");
    fireEvent.click(within(confirmBox("小林")).getByRole("button", { name: "确定改为共同照顾者" }));
    expect(await screen.findByText("已把你改为共同照顾者。")).toBeTruthy();
    expect(api.setMemberRole).toHaveBeenCalledWith("house-1", "owner-1", "caregiver");
  });
});

/* ---------------- 拒绝码的人话 ---------------- */

describe("成员管理：后端拒绝按码说人话，码收进“技术信息”", () => {
  it.each([
    [rejection(409, "CONFLICT", "last_admin"), "家里至少要有一位管理员。想交出管理员，先把另一位家人设为管理员。"],
    [rejection(403, "FORBIDDEN", "admin_required"), "这一步需要家庭管理员来做。你现在可能已经不是管理员了，页面已按最新情况刷新。"],
    [rejection(404, "NOT_FOUND", "member_not_found"), "这位家人已经不在这个家里了，页面已按最新情况刷新。"],
    [rejection(404, "NOT_FOUND", "household_not_found"), "你已经不在这个家里了。"],
    [new ApiError({ kind: "http", status: 403, code: "CSRF_FAILED", message: "csrf" }), "登录状态有变化，刷新页面后再试。"],
    [new ApiError({ kind: "network", code: "NETWORK_ERROR", message: "连不上", retryable: true }), "信号断了一下，没做成，再试一次。"],
    [rejection(409, "CONFLICT", "something_new"), "家里的情况刚有变化，这一步没做成。刷新看看最新的。"],
    [new Error("boom"), "这一步没做成，请稍后再试。"],
  ])("%#：%s → 人话", (error, text) => {
    expect(memberActionFailure(error)).toBe(text);
  });

  it("页面：移除被拒（409 last_admin）→ 说人话，不当成功；原因码与 request_id 收在“技术信息”里；确认框还在，可以再试或先不", async () => {
    const api = liveHouseholds(detailOf([ME, BRO]), {
      removeMember: async () => {
        throw rejection(409, "CONFLICT", "last_admin");
      },
    });
    renderHousehold(api.households);
    await screen.findByRole("heading", { level: 2, name: "一起照顾 TA 的人" });
    fireEvent.click(within(rowOf("哥哥")).getByRole("button", { name: "移除" }));
    fireEvent.click(within(confirmBox("哥哥")).getByRole("button", { name: "确定移除" }));
    const alert = await screen.findByRole("alert");
    expect(alert.querySelector("p")?.textContent).toBe("家里至少要有一位管理员。想交出管理员，先把另一位家人设为管理员。");
    const tech = alert.querySelector("details") as HTMLDetailsElement;
    expect(tech.open).toBe(false);
    expect(tech.textContent).toContain("CONFLICT · last_admin · request_id req-42");
    expect(screen.queryByText(/已移除/)).toBeNull();
    expect(alert.querySelector("p")?.textContent).not.toContain("后端原话");
    expect(confirmBox("哥哥")).toBeTruthy();
  });

  it("页面：403 admin_required / 404 member_not_found → 说人话，收起确认框，并刷新家庭详情与列表", async () => {
    for (const error of [rejection(403, "FORBIDDEN", "admin_required"), rejection(404, "NOT_FOUND", "member_not_found")]) {
      const api = liveHouseholds(detailOf([ME, MOM]), {
        setMemberRole: async () => {
          throw error;
        },
      });
      const { invalidated } = renderHousehold(api.households);
      await screen.findByRole("heading", { level: 2, name: "一起照顾 TA 的人" });
      fireEvent.click(within(rowOf("妈妈")).getByRole("button", { name: "设为管理员" }));
      fireEvent.click(within(confirmBox("妈妈")).getByRole("button", { name: "确定设为管理员" }));
      expect((await screen.findByRole("alert")).querySelector("p")?.textContent).toBe(memberActionFailure(error));
      expect(screen.queryByRole("group", { name: "确认：妈妈" })).toBeNull();
      expect(invalidated).toContain(DETAIL_KEY);
      expect(invalidated).toContain(LIST_KEY);
      cleanup();
    }
  });
});

/* ---------------- live 接线 ---------------- */

describe("成员管理：live 服务接线", () => {
  it("移除走 DELETE /households/{id}/members/{user_id}；调整角色走 PUT …/members/{user_id}/role，请求体是 {role}；编号都做 URL 编码", async () => {
    const calls: Array<{ path: string; method: string | undefined; body: unknown }> = [];
    const api = {
      base: "/api/v1/web",
      async request<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
        calls.push({ path, method: options.method, body: options.body });
        return (options.method === "PUT" ? detailOf([ME, MOM]) : undefined) as T;
      },
    };
    const services = buildServices(loadFeatureModules(), { mode: "live", api });
    await services.households.removeMember("house 1", "user/mom");
    await services.households.setMemberRole("house-1", "user-mom", "admin");
    expect(calls).toEqual([
      { path: "/households/house%201/members/user%2Fmom", method: "DELETE", body: undefined },
      { path: "/households/house-1/members/user-mom/role", method: "PUT", body: { role: "admin" } },
    ]);
  });
});

/* ---------------- 演示模式 ---------------- */

describe("成员管理：演示模式", () => {
  it("成员接口抛能力未接入，不编成员变动", async () => {
    const services = buildServices(loadFeatureModules(), { mode: "fixture", api: createApiClient("/api/v1/web") });
    for (const call of [() => services.households.removeMember("house-1", "user-mom"), () => services.households.setMemberRole("house-1", "user-mom", "admin")]) {
      let error: unknown = null;
      try {
        await call();
      } catch (caught) {
        error = caught;
      }
      expect(isApiError(error) && error.isCapabilityUnavailable).toBe(true);
    }
  });
});
