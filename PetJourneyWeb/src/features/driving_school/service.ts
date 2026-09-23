/**
 * 爪爪驾校服务：live 调后端 /driving；fixture 在内存里按同一套规则运行（实现见 fixture.ts，按需加载，不进主包）。
 */
import type { AnswerResult, CeremonyResult, DrivingSchoolStatus, InputResult, SchoolCurriculum, SchoolSession, SessionBrief } from "@/shared/contracts";
import type { DrivingSchoolService, ServiceContext } from "@/shared/services/types";

export function createLiveDrivingService({ api }: ServiceContext): DrivingSchoolService {
  const path = (id: string, tail = "") => `/driving/sessions/${encodeURIComponent(id)}${tail}`;
  return {
    status: (petId, signal) => api.request<DrivingSchoolStatus>("/driving", { query: { pet_id: petId }, signal }),
    curriculum: () => api.request<SchoolCurriculum>("/driving/curriculum"),
    enroll: () => api.request<DrivingSchoolStatus>("/driving/enroll", { method: "POST" }),
    createSession: (body, idempotencyKey) => api.request<SchoolSession>("/driving/sessions", { method: "POST", body, idempotencyKey }),
    session: (id) => api.request<SchoolSession>(path(id)),
    begin: (id) => api.request<SchoolSession>(path(id, "/begin"), { method: "POST" }),
    answer: (id, body) => api.request<AnswerResult>(path(id, "/answers"), { method: "PUT", body }),
    inputs: (id, body) => api.request<InputResult>(path(id, "/inputs"), { method: "POST", body }),
    pause: (id) => api.request<SchoolSession>(path(id, "/pause"), { method: "POST" }),
    submit: (id) => api.request<SchoolSession>(path(id, "/submit"), { method: "POST" }),
    abandon: (id, confirm) => api.request<SchoolSession>(path(id, "/abandon"), { method: "POST", body: { confirm } }),
    history: () => api.request<SessionBrief[]>("/driving/history"),
    ceremony: () => api.request<CeremonyResult>("/driving/ceremony", { method: "POST" }),
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
  return {
    status: async () => (await load()).status(),
    curriculum: async () => (await load()).curriculum(),
    enroll: async () => (await load()).enroll(),
    createSession: async (body, key) => (await load()).createSession(body, key),
    session: async (id) => (await load()).session(id),
    begin: async (id) => (await load()).begin(id),
    answer: async (id, body) => (await load()).answer(id, body),
    inputs: async (id, body) => (await load()).inputs(id, body),
    pause: async (id) => (await load()).pause(id),
    submit: async (id) => (await load()).submit(id),
    abandon: async (id, confirm) => (await load()).abandon(id, confirm),
    history: async () => (await load()).history(),
    ceremony: async () => (await load()).ceremony(),
  };
}
