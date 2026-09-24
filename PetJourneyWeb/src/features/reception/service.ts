import type {
  CareNote,
  HomeWelcome,
  IntakeConfirmationResult,
  MemoryCorrectionResult,
  ReceptionBranch,
  ReceptionSession,
} from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import type { ReceptionService, ServiceContext } from "@/shared/services/types";
import { confirmFixture, fixtureHomeWelcome, markSkipped, readArchive, scriptedSession } from "@/fixtures/reception";
import { fixturePetName } from "@/fixtures/adoption";
import { delay } from "@/fixtures/world";

export function createLiveReceptionService({ api }: ServiceContext): ReceptionService {
  const s = (id: string) => `/reception/sessions/${encodeURIComponent(id)}`;
  return {
    start: (body, key) => api.request<ReceptionSession>("/reception/sessions", { method: "POST", body, idempotencyKey: key }),
    get: (id) => api.request<ReceptionSession>(s(id)),
    addTurn: (id, body, key) => api.request<ReceptionSession>(`${s(id)}/turns`, { method: "POST", body, idempotencyKey: key }),
    skip: (id) => api.request<ReceptionSession>(`${s(id)}/skip`, { method: "POST" }),
    confirm: (body, key) => api.request<IntakeConfirmationResult>("/reception/confirmations", { method: "POST", body, idempotencyKey: key }),
    notes: (petId) => api.request<CareNote[]>(`/pets/${encodeURIComponent(petId)}/care-notes`),
    correct: (noteId, body, key) => api.request<MemoryCorrectionResult>(`/care-notes/${encodeURIComponent(noteId)}/corrections`, { method: "POST", body, idempotencyKey: key }),
    homeWelcome: (petId) => api.request<HomeWelcome>(`/pets/${encodeURIComponent(petId)}/home-welcome`),
  };
}

/** fixture 控制：下一次确认模拟保存失败（只在演示模式可用）。 */
export const fixtureReceptionControls = { failNextSave: false };

export function createFixtureReceptionService(): ReceptionService {
  const sessions = new Map<string, ReceptionSession>();
  const confirmations = new Map<string, IntakeConfirmationResult>();

  function ensure(sessionId: string): ReceptionSession {
    const found = sessions.get(sessionId);
    if (found) return found;
    const branch = sessionId.endsWith("adopted") ? "adopted" : sessionId.endsWith("own_pet") ? "own_pet" : null;
    if (!branch) throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有找到这次接待。" });
    const petId = branch === "adopted" ? "fx-adopt-pet" : "fx-pet-001";
    const created = scriptedSession(branch as ReceptionBranch, petId, fixturePetName(petId));
    sessions.set(sessionId, created);
    return created;
  }

  return {
    async start(body) {
      const session = scriptedSession(body.branch, body.pet_id, fixturePetName(body.pet_id));
      if (!sessions.has(session.session_id)) sessions.set(session.session_id, session);
      return delay(sessions.get(session.session_id)!);
    },
    get: async (id) => delay(ensure(id)),
    async addTurn(id, body) {
      const session = ensure(id);
      if (body.expected_revision !== session.draft_revision) {
        throw new ApiError({ kind: "http", status: 409, code: "VERSION_CONFLICT", message: "叮嘱在别处更新过，请刷新。", details: { current: session.draft_revision } });
      }
      const seq = session.turns.length + 1;
      const ownerTurn = { turn_id: `t-${seq}`, seq, speaker: "owner" as const, text: body.text, created_at: new Date().toISOString() };
      const hostTurn = {
        turn_id: `t-${seq + 1}`,
        seq: seq + 1,
        speaker: "host" as const,
        text: "好，我先把这句放进待确认的生活叮嘱里。现在是引导记录模式：我不会替你改写或猜测，交给谁由你决定。",
        created_at: new Date().toISOString(),
      };
      const next: ReceptionSession = {
        ...session,
        turns: [...session.turns, ownerTurn, hostTurn],
        candidates: [
          ...session.candidates,
          { candidate_id: `c-new-${seq}`, kind: "habit", subject: "pet", text: body.text, source_turn_id: ownerTurn.turn_id, source_excerpt: body.text, needs_clarification: false, suggested_slot: null, suggested_slot_value: null, state: "unconfirmed" },
        ],
        draft_revision: session.draft_revision + 1,
      };
      sessions.set(id, next);
      return delay(next);
    },
    async skip(id) {
      const session = ensure(id);
      markSkipped();
      const next = { ...session, status: "skipped" as const };
      sessions.set(id, next);
      return delay(next);
    },
    async confirm(body, key) {
      const replay = confirmations.get(key);
      if (replay) return delay(replay);
      const session = ensure(body.session_id);
      if (fixtureReceptionControls.failNextSave) {
        fixtureReceptionControls.failNextSave = false;
        await delay(null, 400);
        throw new ApiError({ kind: "http", status: 503, code: "UPSTREAM_UNAVAILABLE", message: "服务暂时不可用（演示的保存失败）。", retryable: true });
      }
      if (body.draft_revision !== session.draft_revision) {
        throw new ApiError({ kind: "http", status: 409, code: "VERSION_CONFLICT", message: "叮嘱在别处更新过，请刷新后再确认。" });
      }
      const saved = confirmFixture(body, session);
      const result: IntakeConfirmationResult = {
        confirmation_id: saved.confirmationId,
        session_id: session.session_id,
        draft_revision: session.draft_revision,
        persist_state: "persisted",
        notes: saved.notes,
        grants: saved.grants,
        onboarding: { step: "active", pet_id: session.pet_id, home_id: "fx-home-001", reception_session_id: session.session_id, reception_skipped: false, home_activated_at: null, pet_origin: session.branch === "adopted" ? "adopted_original" : "own_pet" },
        data_origin: "fixture",
      };
      confirmations.set(key, result);
      sessions.set(session.session_id, { ...session, status: "completed" });
      return delay(result, 500);
    },
    notes: async () => delay(readArchive().notes),
    async correct(noteId, body) {
      const archive = readArchive();
      const at = new Date().toISOString();
      const notes = archive.notes.map((n) => (n.note_id === noteId ? { ...n, revoked_at: at } : n));
      const grants = archive.grants.map((g) => (g.note_id === noteId ? { ...g, revoked_at: at } : g));
      sessionStorage.setItem("petsoul.fixture.reception", JSON.stringify({ ...archive, notes, grants, version: archive.version + 1 }));
      return delay({ note_id: noteId, new_note: null, cleanup: body.action === "erase" ? "cleanup_pending" : "usage_stopped", affected_task_ids: [] } satisfies MemoryCorrectionResult);
    },
    async homeWelcome(petId) {
      const welcome = fixtureHomeWelcome(petId);
      if (!welcome) throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "还没有确认过的欢迎细节。" });
      return delay(welcome);
    },
  };
}
