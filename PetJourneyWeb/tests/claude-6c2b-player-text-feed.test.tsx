/**
 * claude-6c2b · 出错原因用 playerMessage、宠物主页的动态去重（主窗口 2026-09-24 追加的三件小事）。
 * - 入住表单（认识 TA）直接显示出错原因的那一处、TA 的档案保存失败的兜底：都用 ApiError.playerMessage，
 *   “接口没接好 / 没有这条路”这类开发说法换成给玩家的人话；本来就是写给玩家的原话照用。
 * - 宠物主页 /pets/:petId 的“TA 的动态”：同一作者、一字不差、都没照片的老数据只留最新一条（social/feed.ts 的 collapseRepeats，与朋友圈同一个兜底）；
 *   带照片的照留，别的作者说同一句不算重复，留下的保持原来的先后。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import type { Post, SessionState } from "@/shared/contracts";
import { ApiError, PLAYER_ERROR_TEXT } from "@/shared/api/errors";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { OnboardingPage } from "@/features/pets/pages";
import { saveFailureText } from "@/features/me/dnaModel";
import { PetProfilePage } from "@/features/social/pages";

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
});
afterEach(() => cleanup());

const signedIn = {
  authenticated: true,
  user: { user_id: "u-1", display_name: null, username: "tester", auth_method: "web_password" },
  csrf_required: true,
  expires_at: null,
  onboarding: { step: "needs_companion", pet_id: null, home_id: null, reception_session_id: null, reception_skipped: false, home_activated_at: null, pet_origin: null, entry: null },
} as unknown as SessionState;

function strict(services: Record<string, unknown>): ServiceMap {
  return new Proxy(services as unknown as ServiceMap, {
    get(target, prop: string) {
      if (prop in target) return target[prop as keyof ServiceMap];
      throw new Error(`unexpected service ${prop}`);
    },
  });
}

function renderAt(path: string, pattern: string, element: React.ReactNode, services: Record<string, unknown>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={strict(services)}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path={pattern} element={element} />
          </Routes>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
}

describe("入住表单直接显示的出错原因用 playerMessage", () => {
  async function submitWith(error: ApiError) {
    const createOwn = vi.fn(async () => { throw error; });
    renderAt("/onboarding", "/onboarding", <OnboardingPage />, { session: { current: async () => signedIn }, pets: { createOwn } });
    fireEvent.change(await screen.findByLabelText("02 / TA 叫什么名字？"), { target: { value: "团子" } });
    fireEvent.click(screen.getByRole("radio", { name: "狗" }));
    fireEvent.click(screen.getByRole("button", { name: "继续，去见接待员" }));
    return (await screen.findByRole("alert")).textContent;
  }

  it("原话是开发说法（没有这条路）：换成给玩家的人话，不出现“接口”", async () => {
    const text = await submitWith(new ApiError({ kind: "http", status: 404, code: "MEDIA_REJECTED", message: "没有找到这个接口。", unknownRoute: true }));
    expect(text).toBe(PLAYER_ERROR_TEXT.notFound);
    expect(text).not.toContain("接口");
  });

  it("原话本来就是写给玩家的（图片不能用的原因）：照用", async () => {
    expect(await submitWith(new ApiError({ kind: "http", status: 422, code: "MEDIA_REJECTED", message: "这张图片打不开，换一张试试。", details: { reason: "decode_failed" } }))).toBe("这张图片打不开，换一张试试。");
  });
});

describe("TA 的档案保存失败的兜底用 playerMessage", () => {
  it("还没开放（能力未接入）：说“这里暂时还没开放”，不说“接入”", () => {
    const text = saveFailureText(new ApiError({ kind: "capability", code: "CAPABILITY_UNAVAILABLE", message: "档案接口尚未接入" }));
    expect(text).toBe(PLAYER_ERROR_TEXT.unavailable);
    expect(text).not.toMatch(/接口|接入/);
  });

  it("没有这条路（路由级 404）：说人话的“没有找到”", () => {
    expect(saveFailureText(new ApiError({ kind: "http", status: 405, code: "INTERNAL_ERROR", message: "没有找到这个接口。", unknownRoute: true }))).toBe(PLAYER_ERROR_TEXT.notFound);
  });

  it("后端写给玩家的原话照用", () => {
    expect(saveFailureText(new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "TA 正在外面旅行，回来再改。", details: { reason: "pet_away" } }))).toBe("TA 正在外面旅行，回来再改。");
  });
});

describe("宠物主页 /pets/:petId 的动态去重", () => {
  const post = (post_id: string, author: string, text: string, created_at: string, media: Post["media"] = []): Post => ({
    post_id, author: { actor_kind: "pet", actor_id: author, display_name: author }, text, media, source_event_id: `ev-${post_id}`, visit_id: null,
    visibility: "public", created_at, reaction_count: 0, comment_count: 0, viewer_reacted: false, data_origin: "live",
  }) as unknown as Post;
  const SAME = "在家附近的星球小路待了一会儿。";
  const items = [
    post("p-old", "PJ-1", SAME, "2026-09-20T10:00:00Z"),
    post("p-new", "PJ-1", ` ${SAME} `, "2026-09-22T10:00:00Z"),
    post("p-photo", "PJ-1", SAME, "2026-09-19T10:00:00Z", [{ media_id: "m-1", kind: "image", url: "/media/m-1.webp", width: 10, height: 10, alt: null }] as unknown as Post["media"]),
    post("p-other", "PJ-2", SAME, "2026-09-18T10:00:00Z"),
    post("p-diff", "PJ-1", "今天去了海边。", "2026-09-17T10:00:00Z"),
  ];

  function renderProfile() {
    const services = {
      session: { current: async () => signedIn },
      households: { list: async () => [] },
      pets: { publicProfile: async () => { throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有找到这只宠物的公开主页。", details: { resource: "pet" } }); } },
      social: { petPosts: async () => ({ items, next_cursor: null }) },
      world: { home: async () => ({ pet: { pet_id: "PJ-ME", name: "我家的" } }) },
    };
    mode.dataMode = "fixture"; // 家庭上下文在演示模式下不读账号；这里只看动态列表怎么排
    renderAt("/pets/PJ-1", "/pets/:petId", <HouseholdProvider userId={null}><PetProfilePage /></HouseholdProvider>, services);
  }
  const threadLinks = () => [...document.querySelectorAll('a[href^="/posts/"]')].map((a) => a.getAttribute("href"));

  it("同一作者、一字不差（去掉首尾空白后比）、都没照片的只留最新一条；带照片的、别的作者的、不同的话都留着，先后不变", async () => {
    renderProfile();
    await waitFor(() => expect(threadLinks().length).toBeGreaterThan(0));
    expect(threadLinks()).toEqual(["/posts/p-new", "/posts/p-photo", "/posts/p-other", "/posts/p-diff"]);
  });
});
