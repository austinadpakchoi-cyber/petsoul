/** 爪爪驾校页面共用的查询与失效规则（查询键统一登记在 shared/query/queryClient.ts）。 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { SchoolCurriculum } from "@/shared/contracts";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useActiveHome, useOptionalCurrentHousehold } from "@/shared/session/householdContext";
import { env } from "@/shared/config/env";
import { calibrate } from "@/shared/time/clock";

export function useSchoolStatus(enabled = true) {
  const { driving } = useServices();
  const selection = useOptionalCurrentHousehold();
  const petId = selection?.pet?.pet_id ?? null;
  const userId = selection?.userId ?? null;
  return useQuery({
    queryKey: env.dataMode === "fixture" ? queryKeys.drivingStatus : queryKeys.drivingStatusFor(userId ?? "-", petId ?? "-"),
    queryFn: async ({ signal }) => {
      const status = await driving.status(petId, signal);
      calibrate(status.server_time);
      return status;
    },
    enabled: enabled && (env.dataMode === "fixture" || Boolean(userId && petId)),
  });
}

export function useCurriculum() {
  const { driving } = useServices();
  return useQuery({ queryKey: queryKeys.drivingCurriculum, queryFn: () => driving.curriculum(), staleTime: 10 * 60_000 });
}

/**
 * 这些接口按宠物分：一家有两只时必须指明是哪一只（后端 require_pet 没收到 pet_id 就 409 pet_required）。
 * live 取当前宠物；演示模式没有家庭上下文，为 null（演示服务不看它）。
 */
export function useSchoolPetId(): string | null {
  return useOptionalCurrentHousehold()?.pet?.pet_id ?? null;
}

export function useSchoolHistory() {
  const { driving } = useServices();
  const selection = useOptionalCurrentHousehold();
  const petId = selection?.pet?.pet_id ?? null;
  const userId = selection?.userId ?? null;
  // live 按账号与宠物分键（挂在 queryKeys.drivingHistory 前缀下，写操作按 ["driving"] 失效照样覆盖）；演示只有一份。
  return useQuery({
    queryKey: env.dataMode === "fixture" ? queryKeys.drivingHistory : [...queryKeys.drivingHistory, userId ?? "-", petId ?? "-"],
    queryFn: () => driving.history(petId),
    enabled: env.dataMode === "fixture" || Boolean(userId && petId),
  });
}

/** 写操作之后：驾校状态、考局、历史，以及驾照（证件）、借车券与合影（收藏）、家园快照都可能变化。 */
export function useInvalidateSchool() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["driving"] });
    void queryClient.invalidateQueries({ queryKey: queryKeys.credentials });
    void queryClient.invalidateQueries({ queryKey: queryKeys.collection });
    void queryClient.invalidateQueries({ queryKey: queryKeys.home });
  };
}

/** 当前宠物（头像与名字）；取不到时用“TA”。 */
export function usePet() {
  const home = useActiveHome({ staleTime: 60_000 });
  const pet = home.data?.pet ?? null;
  return { pet, name: pet?.name ?? "TA" };
}

/** 练习提示：按项目取教学步骤的正文（文字来自服务端课程）。 */
const HINT_LESSON: Record<string, [string, string]> = {
  reverse_straight: ["s2", "第一步：直线倒车"],
  reverse_turn: ["s2", "第二步：转向与回正"],
  reverse_park: ["s2", "第三步：完整入库"],
  side_park: ["s2", "侧方停车"],
  curve: ["s2", "弯道行驶"],
  route: ["s3", "路线"],
};

export function practiceHints(curriculum: SchoolCurriculum | undefined): Record<string, string> {
  const out: Record<string, string> = {};
  if (!curriculum) return out;
  for (const [item, [subject, title]] of Object.entries(HINT_LESSON)) {
    const lesson = curriculum.subjects.find((s) => s.subject === subject)?.lessons.find((l) => l.title === title);
    if (lesson) out[item] = lesson.body;
  }
  return out;
}
