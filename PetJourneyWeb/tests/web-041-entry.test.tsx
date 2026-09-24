import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import type { AdoptionCandidate, InvitePreview, PublicWorld, SessionState } from "@/shared/contracts";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { LoginPage, RegisterPage, WelcomePage } from "@/features/identity/pages";
import { AdoptPage } from "@/features/pets/pages";
import { PublicWorldPage } from "@/features/pets/PublicWorldPage";
import { JoinPage } from "@/features/household/JoinPage";

const guest: SessionState = { authenticated: false, user: null, csrf_required: false, expires_at: null, onboarding: null };
const resident: AdoptionCandidate = {
  candidate_id: "candidate-test-1",
  name: "小岚",
  species: "cat",
  personality: "慢热",
  dream: "看看海",
  origin: "adopted_original",
  source_note: null,
  background_available: false,
  availability: "available",
  data_origin: "fixture",
};

function renderEntry(children: React.ReactNode, services: Partial<ServiceMap>, initialEntries = ["/"]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const map = new Proxy(services as ServiceMap, {
    get(target, prop: string) {
      if (prop in target) return target[prop as keyof ServiceMap];
      throw new Error(`unexpected service ${prop}`);
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ServicesProvider services={map}>
        <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
}

describe("0.4.1 first-batch entry UX", () => {
  it("keeps the film decorative and offers both register and guest routes", async () => {
    renderEntry(<WelcomePage />, { session: { current: async () => guest } as ServiceMap["session"] });
    expect(screen.getByRole("link", { name: /寻找我的 TA/ }).getAttribute("href")).toBe("/register");
    expect(screen.getByRole("link", { name: /先去星球上逛逛/ }).getAttribute("href")).toBe("/world#residents");
    expect(screen.getByRole("link", { name: /已经找到 TA 了？登录/ }).getAttribute("href")).toBe("/login");
    expect(screen.getByRole("heading", { level: 1, name: /和 TA 一起，走进另一个世界。/ })).toBeTruthy();
    expect(screen.getByText(/每只宠物，都有一段属于自己的故事/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "暂停开场影片" })).toBeTruthy();
    expect(screen.getByText(/概念影像，不代表你或居民的真实宠物/)).toBeTruthy();
  });

  it("renders public entry options only when the public-world contract offers them", async () => {
    // 2026-09-23 星球页改为全屏地图 + 相遇卡（claude-6c2b）：注册入口沿用用户确认的“寻找我的 TA”，仍只在契约提供 own_pet 时出现。
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve() {} });
    const world: PublicWorld = {
      server_time: "2026-09-23T00:00:00Z", data_origin: "live", cache_seconds: 30,
      entries: [
        { route: "browse", label: "先逛逛", needs_login: false, note: null },
        { route: "own_pet", label: "带我的宠物来", needs_login: true, note: null },
        { route: "adopt", label: "认识新伙伴", needs_login: true, note: null },
      ],
      residents: [], recent_posts: [], living_residents: 0,
    };
    const view = renderEntry(<PublicWorldPage />, {
      session: { current: async () => guest } as ServiceMap["session"],
      pets: { publicWorld: async () => world } as ServiceMap["pets"],
      platform: { basemap: vi.fn() } as unknown as ServiceMap["platform"],
    });
    expect((await screen.findByRole("link", { name: "寻找我的 TA" })).getAttribute("href")).toBe("/register");
    expect((screen.getByRole("button", { name: /看全部居民/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByText("从家人邀请进入")).toBeNull();
    view.unmount();
    vi.unstubAllGlobals();
  });

  it("keeps the illustrated register and login entry tied to the real account form", () => {
    const services = { session: { current: async () => guest } as ServiceMap["session"] };
    const registerPage = renderEntry(<RegisterPage />, services);
    const registerView = within(registerPage.container);
    expect(registerView.getByText("和 TA 一起，走进另一个世界。")).toBeTruthy();
    expect(registerView.getByLabelText("你的账号名")).toBeTruthy();
    expect(registerView.getByLabelText("设置密码")).toBeTruthy();
    expect(registerView.getByRole("button", { name: "创建账号，继续" })).toBeTruthy();
    registerPage.unmount();
    const loginPage = renderEntry(<LoginPage />, services);
    const loginView = within(loginPage.container);
    expect(loginView.getByText("另一个世界，等你回来。")).toBeTruthy();
    expect(loginView.getByLabelText("你的账号名")).toBeTruthy();
    expect(loginView.getByLabelText("密码")).toBeTruthy();
    loginPage.unmount();
  });

  it("sends the selected public resident as entry intent during registration", async () => {
    const register = vi.fn(() => new Promise<SessionState>(() => undefined));
    renderEntry(<RegisterPage />, {
      session: { register } as unknown as ServiceMap["session"],
      pets: { publicPet: async () => ({ profile: { pet_id: "pet-test-1", display_name: "小岚", avatar_url: null }, adoptable: true, resident: null, posts: [] }) } as unknown as ServiceMap["pets"],
    }, ["/register?entry=adopt&pet_id=pet-test-1"]);
    expect(await screen.findByText("刚才认识的居民")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("你的账号名"), { target: { value: "entry_test" } });
    fireEvent.change(screen.getByLabelText("设置密码"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: "创建账号，继续" }));
    await waitFor(() => expect(register).toHaveBeenCalledWith("entry_test", "password123", undefined, { kind: "adopt", pet_id: "pet-test-1", invite_token: null }));
  });

  it("previews a family invitation without joining until the second explicit tap", async () => {
    const loggedIn: SessionState = { ...guest, authenticated: true, user: { user_id: "u-1", username: "member", display_name: null, auth_method: "web_password" }, onboarding: { step: "needs_companion", pet_id: null, home_id: null, reception_session_id: null, reception_skipped: false, home_activated_at: null, pet_origin: null } };
    const invite: InvitePreview = { invite_id: "inv-1", status: "pending", role: "caregiver", relation_hint: null, expires_at: "2026-10-01T00:00:00Z", household_name: "海边的家", inviter_name: "姐姐", pet_names: ["小岚"], already_member: false };
    const acceptInvite = vi.fn(() => new Promise<never>(() => undefined));
    renderEntry(<JoinPage />, {
      session: { current: async () => loggedIn } as ServiceMap["session"],
      households: { list: async () => [], previewInvite: async () => invite, acceptInvite } as unknown as ServiceMap["households"],
    }, ["/join?invite=local-test-token"]);
    expect(await screen.findByText("海边的家")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "我想加入这个家" }));
    expect(acceptInvite).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "确认加入" }));
    await waitFor(() => expect(acceptInvite).toHaveBeenCalledWith("local-test-token"));
  });

  it("does not adopt on the first tap; requires an explicit confirmation", async () => {
    const adopt = vi.fn(async () => ({ pet_id: "pet-test-1", candidate_id: resident.candidate_id, adopted_at: "2026-09-23T00:00:00Z" }));
    renderEntry(<AdoptPage />, {
      session: { current: async () => guest } as ServiceMap["session"],
      pets: { adoptionCandidates: async () => [resident], adopt } as unknown as ServiceMap["pets"],
    });
    fireEvent.click(await screen.findByRole("button", { name: /了解并迎接 小岚/ }));
    expect(adopt).not.toHaveBeenCalled();
    expect(screen.getByRole("group", { name: "确认领养 小岚" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "确认领养" }));
    await waitFor(() => expect(adopt).toHaveBeenCalledTimes(1));
  });
});
