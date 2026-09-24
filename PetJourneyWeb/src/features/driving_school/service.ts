/**
 * 爪爪驾校服务：live 调后端 /driving；fixture 在内存里按同一套规则运行（实现见 fixture.ts，按需加载，不进主包）。
 */
import type { AnswerResult, CeremonyResult, DrivingSchoolStatus, InputResult, SchoolCurriculum, SchoolSession, SessionBrief } from "@/shared/contracts";
import type { DrivingSchoolService, ServiceContext } from "@/shared/services/types";

export function createLiveDrivingService({ api }: ServiceContext): DrivingSchoolService {
  const path = (id: string, tail = "") => `/driving/sessions/${encodeURIComponent(id)}${tail}`;
  // 每只宠物各有自己的驾校进度、考局与驾照：除课程外每条都按 ?pet_id= 指明是哪一只（一家有两只时不带就 409 pet_required）。
  const pet = (petId?: string | null) => ({ pet_id: petId ?? null });
  return {
    status: (petId, signal) => api.request<DrivingSchoolStatus>("/driving", { query: pet(petId), signal }),
    curriculum: () => api.request<SchoolCurriculum>("/driving/curriculum"),
    enroll: (petId) => api.request<DrivingSchoolStatus>("/driving/enroll", { method: "POST", query: pet(petId) }),
    createSession: (body, idempotencyKey, petId) => api.request<SchoolSession>("/driving/sessions", { method: "POST", query: pet(petId), body, idempotencyKey }),
    session: (id, petId) => api.request<SchoolSession>(path(id), { query: pet(petId) }),
    begin: (id, petId) => api.request<SchoolSession>(path(id, "/begin"), { method: "POST", query: pet(petId) }),
    answer: (id, body, petId) => api.request<AnswerResult>(path(id, "/answers"), { method: "PUT", query: pet(petId), body }),
    inputs: (id, body, petId) => api.request<InputResult>(path(id, "/inputs"), { method: "POST", query: pet(petId), body }),
    pause: (id, petId) => api.request<SchoolSession>(path(id, "/pause"), { method: "POST", query: pet(petId) }),
    submit: (id, petId) => api.request<SchoolSession>(path(id, "/submit"), { method: "POST", query: pet(petId) }),
    abandon: (id, confirm, petId) => api.request<SchoolSession>(path(id, "/abandon"), { method: "POST", query: pet(petId), body: { confirm } }),
    history: (petId) => api.request<SessionBrief[]>("/driving/history", { query: pet(petId) }),
    ceremony: (petId) => api.request<CeremonyResult>("/driving/ceremony", { method: "POST", query: pet(petId) }),
  };
}

export interface FixtureDrivingOptions {
  /** 起始阶段（测试与演示用）：none＝还没开始（默认）；wish＝有了学车愿望还没报名；enrolled＝已报名；licensed＝四科已过、待领证 */
  stage?: "none" | "wish" | "enrolled" | "licensed";
  /** 当前时间（测试用来快进冷却）；默认 Date.now */
  now?: () => number;
  /** 演示延迟（毫秒）；测试传 0 */
  latency?: number;
}

/** fixture 模式的演示起点：网址带 ?school_demo=wish / enrolled / licensed 时从那个阶段开始（只在打开页面时读取一次）。 */
export function fixtureStageFromUrl(): FixtureDrivingOptions["stage"] {
  if (typeof window === "undefined") return undefined;
  const value = new URLSearchParams(window.location.search).get("school_demo");
  return value === "enrolled" || value === "licensed" || value === "wish" ? value : undefined;
}

/** fixture 服务的轻量入口：第一次调用时才加载演示数据与内存规则（fixture.ts）。 */
export function createFixtureDrivingService(options: FixtureDrivingOptions = {}): DrivingSchoolService {
  let impl: Promise<DrivingSchoolService> | null = null;
  const load = () => (impl ??= import("./fixture").then((m) => m.buildFixtureDrivingService(options)));
  // 参数原样转发（宠物、取消信号都不丢）：演示现在只有一只宠物，但包装层吞参数的写法以后会咬人（见 tests/claude-6c2b-pet-scoped-calls）。
  return {
    status: async (petId, signal) => (await load()).status(petId, signal),
    curriculum: async () => (await load()).curriculum(),
    enroll: async (petId) => (await load()).enroll(petId),
    createSession: async (body, key, petId) => (await load()).createSession(body, key, petId),
    session: async (id, petId) => (await load()).session(id, petId),
    begin: async (id, petId) => (await load()).begin(id, petId),
    answer: async (id, body, petId) => (await load()).answer(id, body, petId),
    inputs: async (id, body, petId) => (await load()).inputs(id, body, petId),
    pause: async (id, petId) => (await load()).pause(id, petId),
    submit: async (id, petId) => (await load()).submit(id, petId),
    abandon: async (id, confirm, petId) => (await load()).abandon(id, confirm, petId),
    history: async (petId) => (await load()).history(petId),
    ceremony: async (petId) => (await load()).ceremony(petId),
  };
}
