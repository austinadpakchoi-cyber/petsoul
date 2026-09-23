/**
 * MemoryPolicy 客户端镜像（与后端 app/reception/policy.py 同语义），只用于 fixture 模拟与测试。
 * live 模式下授权与过滤只能由服务端执行，前端不得据此放宽任何访问。
 */
import type { CandidateKind, CareNote, HomeWelcome, MemoryGrant, MemoryProjection, MemoryPurpose, WelcomeDetail, WelcomeDetailKind } from "@/shared/contracts";

export const POLICY_VERSION = "memory-policy-r0-1";
export const NEVER_PROJECTED_KINDS: ReadonlySet<CandidateKind> = new Set(["owner_private", "inference"]);

export function projectMemory(petId: string, purpose: MemoryPurpose, notes: CareNote[], grants: MemoryGrant[], now: Date = new Date()): MemoryProjection {
  const superseded = new Set(notes.map((n) => n.supersedes_note_id).filter(Boolean) as string[]);
  const active = new Set(grants.filter((g) => !g.revoked_at).map((g) => `${g.note_id}|${g.note_version}|${g.purpose}`));
  const items = notes
    .filter(
      (note) =>
        note.pet_id === petId &&
        note.target === "give_to_pet" &&
        !NEVER_PROJECTED_KINDS.has(note.kind) &&
        !note.revoked_at &&
        !superseded.has(note.note_id) &&
        note.purposes.includes(purpose) &&
        active.has(`${note.note_id}|${note.version}|${purpose}`),
    )
    .map((note) => ({ note_id: note.note_id, note_version: note.version, kind: note.kind, text: note.text, slot: note.slot, slot_value: note.slot_value }));
  return { pet_id: petId, purpose, items, policy_version: POLICY_VERSION, generated_at: now.toISOString() };
}

const WELCOME_SLOTS: Partial<Record<string, WelcomeDetailKind>> = {
  owner_title: "owner_title",
  favorite_object: "favorite_object",
  interaction_boundary: "interaction_boundary",
};

export function buildHomeWelcome(projection: MemoryProjection, projectionVersion: number, confirmationId: string | null): HomeWelcome {
  if (projection.purpose !== "home_interaction") throw new Error("HomeWelcome 只能由 home_interaction 投影生成");
  let title: string | null = null;
  const details: WelcomeDetail[] = [];
  for (const item of projection.items) {
    const kind = item.slot ? WELCOME_SLOTS[item.slot] : undefined;
    if (!kind) continue;
    if (kind === "owner_title" && item.slot_value) title = item.slot_value;
    details.push({ kind, text: item.text, note_id: item.note_id, note_version: item.note_version });
  }
  return {
    pet_id: projection.pet_id,
    confirmation_id: confirmationId,
    projection_version: projectionVersion,
    greeting: title ? `${title}，我到家啦。` : "我到家啦，这里闻起来像你。",
    details,
  };
}
