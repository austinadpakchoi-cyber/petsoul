/**
 * 身份模块：欢迎/注册/登录/入住激活/设置页面 + SessionService。
 * live：用户名+密码（服务端 scrypt、可吊销会话 cookie + CSRF）；入住阶段与设置读写真实接口。
 * fixture：演示身份——不创建假账号；入住阶段视为已入住，设置只在本页内存里演示。
 */
import type { HomePlaceView, OnboardingState, SessionState, SettingsView } from "@/shared/contracts";
import { ApiError, isApiError } from "@/shared/api/errors";
import { defineModule } from "@/shared/modules/types";
import { LoginPage, MoveInPage, RegisterPage, SettingsPage, WelcomePage } from "./pages";

const FIXTURE_ONBOARDING: OnboardingState = {
  step: "active",
  pet_id: "fx-pet-mochi",
  home_id: "fx-home-1",
  reception_session_id: null,
  reception_skipped: false,
  home_activated_at: null,
  pet_origin: "own_pet",
};

export default defineModule({
  id: "identity",
  routes: [{ path: "settings", element: <SettingsPage /> }],
  bareRoutes: [
    { path: "welcome", element: <WelcomePage /> },
    { path: "register", element: <RegisterPage /> },
    { path: "login", element: <LoginPage /> },
    { path: "onboarding/move-in", element: <MoveInPage /> },
  ],
  services: {
    session: {
      live: ({ api }) => ({
        current: async () => {
          try {
            return await api.request<SessionState>("/session");
          } catch (error) {
            // cookie 过期或已吊销：当作未登录（服务端已拒绝该会话），由守卫带回欢迎页重新登录。
            if (isApiError(error) && error.code === "SESSION_EXPIRED") return { authenticated: false, user: null, csrf_required: false, expires_at: null, onboarding: null };
            throw error;
          }
        },
        register: (username, password, displayName, entry) => api.request<SessionState>("/auth/register", { method: "POST", body: { username, password, display_name: displayName ?? null, entry: entry ?? null } }),
        login: (username, password) => api.request<SessionState>("/auth/login", { method: "POST", body: { username, password } }),
        logout: () => api.request<void>("/auth/logout", { method: "POST" }),
        onboarding: () => api.request<OnboardingState>("/onboarding"),
        moveIn: (publicPosts, habitat, petId) => api.request<OnboardingState>("/onboarding/move-in", { method: "POST", body: { public_posts: publicPosts, habitat: habitat ?? null, pet_id: petId ?? null } }),
        homePlace: (petId) => api.request<HomePlaceView>("/home/place", { query: { pet_id: petId ?? undefined } }),
        // 设置里的简介、公开范围、公开动态是这只宠物的：一家有两只时不带 pet_id，读的是“第一只”，改则 409 pet_required。
        settings: (petId) => api.request<SettingsView>("/settings", { query: { pet_id: petId } }),
        updateSettings: (patch, petId) => api.request<SettingsView>("/settings", { method: "PATCH", query: { pet_id: petId }, body: patch }),
      }),
      fixture: () => {
        let settings: SettingsView = { username: null, display_name: "演示主人", public_posts: true, profile_visibility: "public", bio: "演示宠物的简介", intent_layer_mode: "off" };
        return {
          current: async () => ({ authenticated: false, user: null, csrf_required: false, expires_at: null, onboarding: null }),
          register: async () => {
            throw ApiError.capability("identity.password_registration", "演示模式不创建账号。");
          },
          login: async () => {
            throw ApiError.capability("identity.password_registration", "演示模式不提供登录。");
          },
          logout: async () => undefined,
          onboarding: async () => FIXTURE_ONBOARDING,
          moveIn: async () => FIXTURE_ONBOARDING,
          homePlace: async () => { throw ApiError.capability("home.place", "演示模式不选择正式住处。"); },
          settings: async () => settings,
          updateSettings: async (patch) => {
            settings = {
              ...settings,
              public_posts: patch.public_posts ?? settings.public_posts,
              profile_visibility: patch.profile_visibility ?? settings.profile_visibility,
              bio: patch.bio ?? settings.bio,
            };
            return settings;
          },
        };
      },
    },
  },
});
