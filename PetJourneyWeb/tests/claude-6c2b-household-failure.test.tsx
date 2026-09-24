/**
 * claude-6c2b · 我们的家（/households/manage）保存失败时给玩家看的一句（2026-09-24 巡检 P1 追加，主窗口派）：
 * - 出错原因用 ApiError.playerMessage：还没开放、后端没有这条路（原话“没有找到这个接口。”）的换成人话，其余照用后端写给玩家的原话；
 *   不是接口错误的（前端自己的异常）不显示异常原文，只说“操作暂时没有完成，请重试。”。
 * - 照片许可那句“这次没有完成保存：……请以当前家庭状态为准。”：原因自己带句号时不再补一个，不出现“。。”。
 */
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import type { HouseholdBrief, HouseholdDetail, PetRelationship, WebErrorEnvelope } from "@/shared/contracts";
import { ApiError, PLAYER_ERROR_TEXT } from "@/shared/api/errors";
import type { ServiceMap } from "@/shared/services/types";
import { ServicesProvider } from "@/shared/services/registry";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { failure, HouseholdPage, PhotoConsentSetting, withStop } from "@/features/household/HouseholdPage";

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
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/* ---------------- 几种真实会遇到的失败 ---------------- */

const envelope = (code: WebErrorEnvelope["error"]["code"], message: string, details: Record<string, unknown> | null): WebErrorEnvelope => ({
  error: { code, message, request_id: "req_family_1", retryable: false, details },
});
/** 后端没有这条路：路由级 404，不带 details（web_platform/errors.py 的 _http_error）。 */
const ROUTE_404 = () => ApiError.fromEnvelope(404, envelope("NOT_FOUND", "没有找到这个接口。", null), null);
/** 业务上的拒绝：后端原话本来就是写给玩家的，自带句号。 */
const FORBIDDEN = () => ApiError.fromEnvelope(403, envelope("FORBIDDEN", "只有家庭管理员可以修改。", { reason: "admin_required" }), null);
/** 业务上的拒绝，原话没带句号。 */
const NO_STOP = () => ApiError.fromEnvelope(409, envelope("CONFLICT", "这份邀请已经用过了", { reason: "invite_used" }), null);
/** 前端自己的异常：原文是给开发看的。 */
const BUG = () => new TypeError("Cannot read properties of undefined (reading 'household_id')");

describe("我们的家：出错原因说人话（failure）", () => {
  it("后端没有这条路：换成人话，不出现“接口”", () => {
    expect(failure(ROUTE_404())).toBe(PLAYER_ERROR_TEXT.notFound);
    expect(failure(ROUTE_404())).not.toContain("接口");
  });

  it("还没开放：“这里暂时还没开放，准备好了会出现在这里。”", () => {
    expect(failure(ApiError.capability("households.invites"))).toBe(PLAYER_ERROR_TEXT.unavailable);
  });

  it("业务上的拒绝照用后端原话", () => {
    expect(failure(FORBIDDEN())).toBe("只有家庭管理员可以修改。");
    expect(failure(NO_STOP())).toBe("这份邀请已经用过了");
  });

  it("不是接口错误：不显示异常原文，只说“操作暂时没有完成，请重试。”", () => {
    expect(failure(BUG())).toBe("操作暂时没有完成，请重试。");
    expect(failure("oops")).toBe("操作暂时没有完成，请重试。");
    expect(failure(undefined)).toBe("操作暂时没有完成，请重试。");
  });
});

describe("我们的家：把原因接进整句不出现“。。”（withStop）", () => {
  it("原因自带句号、问号、叹号、省略号时不再补；没带时补一个句号；首尾空白去掉", () => {
    expect(withStop("只有家庭管理员可以修改。")).toBe("只有家庭管理员可以修改。");
    expect(withStop("这份邀请已经用过了")).toBe("这份邀请已经用过了。");
    expect(withStop("真的要这样吗？")).toBe("真的要这样吗？");
    expect(withStop("好的！")).toBe("好的！");
    expect(withStop("Done!")).toBe("Done!");
    expect(withStop("再等等…")).toBe("再等等…");
    expect(withStop("  这份邀请已经用过了 \n")).toBe("这份邀请已经用过了。");
  });
});

/* ---------------- 照片许可那一句 ---------------- */

function consentAlert(error: unknown) {
  const view = render(<PhotoConsentSetting enabled={false} canManage pending={false} error={error} onChange={vi.fn()} />);
  const alert = within(view.container).getByRole("alert");
  return alert.textContent ?? "";
}

describe("照片许可：这次没有完成保存", () => {
  it("原因自带句号：整句只有一个句号接着“请以当前家庭状态为准。”", () => {
    const text = consentAlert(FORBIDDEN());
    expect(text).toBe("这次没有完成保存：只有家庭管理员可以修改。请以当前家庭状态为准。");
    expect(text).not.toContain("。。");
  });

  it("原因没带句号：补一个", () => {
    expect(consentAlert(NO_STOP())).toBe("这次没有完成保存：这份邀请已经用过了。请以当前家庭状态为准。");
  });

  it("后端没有这条路：说人话，不出现“接口”和“。。”", () => {
    const text = consentAlert(ROUTE_404());
    expect(text).toBe(`这次没有完成保存：${PLAYER_ERROR_TEXT.notFound}请以当前家庭状态为准。`);
    expect(text).not.toMatch(/接口|。。/);
  });
});

/* ---------------- 整页：称呼、约定、邀请、撤销邀请的失败 ---------------- */

const brief: HouseholdBrief = {
  household_id: "house-1",
  name: "海边的家",
  home_id: "home-1",
  role: "admin",
  home_activated: true,
  member_count: 1,
  pets: [{ pet_id: "pet-a", name: "奶茶", species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true }],
};

const detail: HouseholdDetail = {
  household: brief,
  members: [{ user_id: "owner-1", display_name: "小林", role: "admin", joined_at: "2026-09-20T00:00:00Z", is_you: true }],
  settings: { name: "海边的家", caregivers_can_spend: false, generated_photos: false, pet_messages: true, public_posts: false },
  your_permissions: ["view", "care", "spend", "manage"],
  version: 1,
};

const relationship: PetRelationship = { pet_id: "pet-a", owner_title: null, relation_label: null, updated_at: null };

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
}

function liveHouseholds(overrides: Record<string, unknown>) {
  return {
    list: vi.fn(async () => [brief]),
    detail: vi.fn(async () => detail),
    invites: vi.fn(async () => [{ invite_id: "inv-1", relation_hint: "爸爸", status: "pending", created_at: "2026-09-24T00:00:00Z", expires_at: "2026-09-27T00:00:00Z" }]),
    relationship: vi.fn(async () => relationship),
    saveRelationship: vi.fn(async () => relationship),
    updateSettings: vi.fn(async () => detail),
    createInvite: vi.fn(async () => ({ invite_id: "inv-2", join_path: "/join/abc", expires_at: "2026-09-27T00:00:00Z" })),
    revokeInvite: vi.fn(async () => ({})),
    ...overrides,
  };
}

const cardOf = (heading: RegExp | string) => screen.getByRole("heading", { level: 2, name: heading }).closest(".ps-family-card") as HTMLElement;

describe("我们的家：整页上的失败说法", () => {
  it("生成邀请：后端没有这条路时说人话，不出现“没有找到这个接口”", async () => {
    const households = liveHouseholds({ createInvite: vi.fn(async () => { throw ROUTE_404(); }) });
    renderHousehold(households);
    fireEvent.click(await screen.findByRole("button", { name: "生成 72 小时邀请链接" }));
    const alert = await within(cardOf("邀请家人")).findByRole("alert");
    expect(alert.textContent).toBe(PLAYER_ERROR_TEXT.notFound);
    expect(households.createInvite).toHaveBeenCalledTimes(1);
  });

  it("保存称呼：前端自己的异常不显示原文", async () => {
    const households = liveHouseholds({ saveRelationship: vi.fn(async () => { throw BUG(); }) });
    renderHousehold(households);
    const card = await screen.findByRole("heading", { level: 2, name: /怎么称呼你$/ }).then((h) => h.closest(".ps-family-card") as HTMLElement);
    fireEvent.click(await within(card).findByRole("button", { name: "保存称呼" }));
    const alert = await within(card).findByRole("alert");
    expect(alert.textContent).toBe("操作暂时没有完成，请重试。");
    expect(document.body.textContent).not.toContain("Cannot read properties");
  });

  it("保存家名：业务拒绝照用后端原话", async () => {
    const households = liveHouseholds({ updateSettings: vi.fn(async () => { throw FORBIDDEN(); }) });
    renderHousehold(households);
    const card = await screen.findByRole("heading", { level: 2, name: "家里的约定" }).then((h) => h.closest(".ps-family-card") as HTMLElement);
    fireEvent.change(within(card).getByLabelText("家名"), { target: { value: "山边的家" } });
    fireEvent.click(within(card).getByRole("button", { name: "保存家名" }));
    const alert = await within(card).findByRole("alert");
    expect(alert.textContent).toBe("只有家庭管理员可以修改。");
  });

  it("撤销邀请：还没开放时说人话", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const households = liveHouseholds({ revokeInvite: vi.fn(async () => { throw ApiError.capability("households.invites"); }) });
    renderHousehold(households);
    const card = await screen.findByRole("heading", { level: 2, name: "邀请家人" }).then((h) => h.closest(".ps-family-card") as HTMLElement);
    fireEvent.click(await within(card).findByRole("button", { name: "撤销" }));
    const alert = await within(card).findByRole("alert");
    expect(alert.textContent).toBe(PLAYER_ERROR_TEXT.unavailable);
    expect(households.revokeInvite).toHaveBeenCalledWith("house-1", "inv-1");
    expect(confirm).toHaveBeenCalledTimes(1);
  });
});
