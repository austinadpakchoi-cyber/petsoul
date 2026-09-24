/**
 * 地图主状态面板里的驾校提醒（方案 v2.1 第 8.1 / 8.2 节：驾校平时不占首屏）。
 * - wish（TA 自己想学）：「<名字>说想学开车：“<服务端 wish_text 原文>”」，例如“团子说想学开车：…”；拿不到名字时才说“TA 说想学开车”；
 * - enrolled：按服务端四科状态说一句进度——有没考完的考试 / 哪一科可以约考 / 等到什么时候可以再约；
 * - license_pending（服务端含义：四科已过、驾照正在签发）：如实说驾照正在签发；
 * - licensed 且领证仪式还没做（有驾照、ceremony_done=false）：“领证仪式在等你们”，点它去驾校自己的仪式入口 /school/ceremony
 *   （与驾校首页驾照卡的“去领证”同一落点；那一页打开只读状态，要主人再按“开始领证”才真正领证，“先不领”回 /school）；
 * - none、licensed 且仪式做过：不出现（主人主动的入口在证件卡包的驾照空卡位）。
 * 其余都点去 /school。文字只取服务端字段（阶段、wish_text、科目标题与状态、冷却截止时间、驾照、仪式是否做过），不编进度；字段不够就不出这一行。
 * 驾校服务取不到（能力未接入、报错、还在读）时返回 null：面板照常，只是没有这一行。
 *
 * 查询键、查询函数、启用条件与驾校模块自己的 useSchoolStatus（driving_school/hooks.ts）逐项一致，两边共用同一份缓存：
 * fixture 用 queryKeys.drivingStatus；live 用 queryKeys.drivingStatusFor(用户, 当前宠物)。
 */
import { useQuery } from "@tanstack/react-query";
import type { DrivingSchoolStatus, SubjectStatus } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useOptionalCurrentHousehold } from "@/shared/session/householdContext";
import { calibrate } from "@/shared/time/clock";
import type { PanelNote } from "./panelNotes";

/** 冷却截止时间（看的人所在时区），例如“9月30日 14:00”。 */
const UNTIL = new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });

/** 服务端科目标题形如“科目二：把小车开稳”，取冒号前的科目名（与驾校模块、后端同一取法）。 */
function subjectName(subject: SubjectStatus): string {
  return subject.title.split("：")[0] || subject.title;
}

function enrolledProgress(status: DrivingSchoolStatus): string | null {
  if (!status.subjects.length) return null;
  if (status.open_session) {
    const open = status.subjects.find((s) => s.subject === status.open_session!.subject);
    return open ? `${subjectName(open)}的考试还没考完` : "有一场考试还没考完";
  }
  // 正式考试按科目一到科目四依次解锁：第一门还没通过的，就是正在学的那一门。
  const current = status.subjects.find((s) => s.state !== "passed");
  if (!current) return "科目都考过了";
  const name = subjectName(current);
  switch (current.state) {
    case "available":
      return current.next_attempt === "retake" ? `${name}可以约补考了` : `${name}可以约考了`;
    case "in_exam":
      return `${name}的考试还没考完`;
    case "cooldown": {
      const until = current.cooldown_until ? Date.parse(current.cooldown_until) : Number.NaN;
      return Number.isFinite(until) ? `${name} ${UNTIL.format(until)} 后可以再约考` : null;
    }
    case "locked":
      return current.unlock_hint;
    default:
      return null;
  }
}

/** 面板提醒这一行说什么、点了去哪；这一阶段不该出现、或服务端字段不够说清楚时为 null。petName 是这只宠物的名字，没有就说“TA”。 */
export function schoolNoteContent(status: DrivingSchoolStatus, petName?: string | null): { text: string; to: string } | null {
  switch (status.stage) {
    case "wish": {
      const who = petName?.trim() ? petName.trim() : "TA ";
      return { text: status.wish_text ? `${who}说想学开车：“${status.wish_text}”` : `${who}说想学开车`, to: "/school" };
    }
    case "enrolled": {
      const progress = enrolledProgress(status);
      return progress ? { text: `驾校 · ${progress}`, to: "/school" } : null;
    }
    case "license_pending":
      return { text: "驾校 · 四科都过了，驾照正在签发", to: "/school" };
    case "licensed":
      // 领证仪式只做一次：有驾照、还没做过时提醒；做过就不再出现。
      return status.license && !status.ceremony_done ? { text: "驾校 · 领证仪式在等你们", to: "/school/ceremony" } : null;
    default:
      return null;
  }
}

/** 只要这一行的文字（测试与读屏核对用）。 */
export function schoolNoteText(status: DrivingSchoolStatus, petName?: string | null): string | null {
  return schoolNoteContent(status, petName)?.text ?? null;
}

/**
 * 当前宠物的驾校提醒（只关于这一只：面板点到别的宠物时由上层滤掉）。
 * 名字：live 用当前宠物的名字；演示没有家庭上下文，用上层给的（面板上那只，演示里就是那一只）。
 */
export function useSchoolNote(petNameHint?: string | null): PanelNote | null {
  const services = useServices();
  const selection = useOptionalCurrentHousehold();
  const petId = selection?.pet?.pet_id ?? null;
  const petName = selection?.pet?.name ?? petNameHint ?? null;
  const userId = selection?.userId ?? null;
  const status = useQuery({
    queryKey: env.dataMode === "fixture" ? queryKeys.drivingStatus : queryKeys.drivingStatusFor(userId ?? "-", petId ?? "-"),
    // 服务在查询函数里才取：驾校服务不论以哪种方式失败，都只落到这条查询的错误态，地图与面板照常。
    queryFn: async ({ signal }) => {
      const result = await services.driving.status(petId, signal);
      calibrate(result.server_time);
      return result;
    },
    enabled: env.dataMode === "fixture" || Boolean(userId && petId),
  });
  if (!status.isSuccess) return null;
  const content = schoolNoteContent(status.data, petName);
  return content ? { id: "school", kind: "school", ...content, petId: petId ?? undefined } : null;
}
