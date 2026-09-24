import { useQuery } from "@tanstack/react-query";
import type { OnboardingState, SessionState } from "@/shared/contracts";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";

/** 入住阶段 → 应该停留的页面（唯一映射，注册/登录/接待/入住都用它跳转）。 */
export function onboardingRoute(state: OnboardingState | null | undefined): string {
  switch (state?.step) {
    case "needs_companion":
      if (state.entry?.pending_invite) return "/join";
      return state.entry?.pending_adoption ? "/onboarding/choice" : "/onboarding";
    case "reception_optional":
      return "/onboarding/reception";
    case "ready_to_move_in":
      return "/onboarding/move-in";
    default:
      // 已入住：进地图首页（2026-09-24 新导航；小窝是地图下的二级页）。
      return "/map";
  }
}

export function routeAfterSession(session: SessionState): string {
  if (!session.authenticated) return "/welcome";
  return onboardingRoute(session.onboarding);
}

export function useSessionState() {
  const { session } = useServices();
  return useQuery({ queryKey: queryKeys.session, queryFn: () => session.current(), staleTime: 30_000 });
}
