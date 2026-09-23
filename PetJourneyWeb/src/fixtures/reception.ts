/**
 * 接待 fixture：两条分支（自己的宠物 / 领养伙伴）的脚本化对话与候选便笺，以及确认后的演示存档。
 * mode=guided_notes：R0 没有接入接待模型；候选由脚本预置，主人新输入的话“原样”成为待确认便笺，
 * 不冒充模型理解。确认结果只保存在本浏览器标签页（sessionStorage），不是服务器保存。
 */
import type {
  CareNote,
  CareNoteDecision,
  IntakeCandidate,
  IntakeConfirmationRequest,
  IntakeConfirmationResult,
  MemoryGrant,
  ReceptionBranch,
  ReceptionHost,
  ReceptionSession,
  ReceptionTurn,
} from "@/shared/contracts";
import { buildHomeWelcome, projectMemory } from "@/shared/memory/policy";
import type { HomeWelcome } from "@/shared/contracts";

export const fixtureHost: ReceptionHost = {
  host_id: "fx-host-reception",
  display_name: "星球接待员",
  role_label: "PetSoul 的 AI 接待角色",
  avatar_url: null,
  is_ai: true,
  disclosure: "我是 PetSoul 的 AI 接待角色。你选择保存的内容，才会用来帮助塑造你的伙伴；不想说可以随时跳过。",
};

const now = () => new Date().toISOString();

function turn(id: string, seq: number, speaker: "host" | "owner", text: string): ReceptionTurn {
  return { turn_id: id, seq, speaker, text, created_at: now() };
}

function candidate(c: Omit<IntakeCandidate, "state" | "needs_clarification"> & { needs_clarification?: boolean }): IntakeCandidate {
  return { needs_clarification: false, state: "unconfirmed", ...c };
}

function ownPetSession(petId: string, petName: string): ReceptionSession {
  const turns = [
    turn("t1", 1, "host", `我正在给 ${petName} 准备入住的小档案。有些只有你知道的小事——它怎么撒娇、习惯睡哪里、听到哪个小名会抬头——我也想替你带过去。有什么想特别交代的吗？一件小事也可以，我们不用一次说完。`),
    turn("t2", 2, "owner", "它不喜欢别人抱，都是自己靠过来。我坐沙发的时候，它会把下巴搭在我腿上。"),
    turn("t3", 3, "host", "那我先整理成一句叮嘱：别急着抱它，等它自己靠近。你想这样记下来吗？"),
    turn("t4", 4, "owner", "它有一条蓝色小毯子，睡觉会叼着。还有，让它叫我姐姐就好。"),
    turn("t5", 5, "owner", "其实我总觉得它最后在怪我。"),
    turn("t6", 6, "host", "谢谢你愿意说。这句我先放在“只留在这里”，不会交给它，也不会出现在任何公开的地方。"),
  ];
  const candidates = [
    candidate({ candidate_id: "c-own-1", kind: "habit", subject: "relationship", text: "别急着抱它，等它自己靠近；坐沙发时它会把下巴搭在主人腿上。", source_turn_id: "t2", source_excerpt: "它不喜欢别人抱，都是自己靠过来。我坐沙发的时候，它会把下巴搭在我腿上。", suggested_slot: "interaction_boundary", suggested_slot_value: null }),
    candidate({ candidate_id: "c-own-2", kind: "habit", subject: "pet", text: "睡觉时会叼着一条蓝色小毯子。", source_turn_id: "t4", source_excerpt: "它有一条蓝色小毯子，睡觉会叼着。", suggested_slot: "favorite_object", suggested_slot_value: "蓝色小毯子" }),
    candidate({ candidate_id: "c-own-3", kind: "habit", subject: "relationship", text: "称呼主人为“姐姐”。", source_turn_id: "t4", source_excerpt: "让它叫我姐姐就好。", suggested_slot: "owner_title", suggested_slot_value: "姐姐" }),
    candidate({ candidate_id: "c-own-4", kind: "owner_private", subject: "owner", text: "主人担心它最后在怪自己。", source_turn_id: "t5", source_excerpt: "其实我总觉得它最后在怪我。", suggested_slot: null, suggested_slot_value: null }),
    candidate({ candidate_id: "c-own-5", kind: "inference", subject: "pet", text: "（推测）它可能比较独立。", source_turn_id: "t2", source_excerpt: "它不喜欢别人抱", needs_clarification: true, suggested_slot: null, suggested_slot_value: null }),
  ];
  return base(petId, "own_pet", turns, candidates);
}

function adoptedSession(petId: string, petName: string): ReceptionSession {
  const turns = [
    turn("a1", 1, "host", `${petName} 第一次来到你家。你想怎样欢迎它？比如希望它怎么称呼你，或者给它准备了什么小角落。`),
    turn("a2", 2, "owner", "希望它叫我阿姨。我在窗边给它放了一个软垫子。"),
    turn("a3", 3, "owner", "以后想带它去看海。"),
  ];
  const candidates = [
    candidate({ candidate_id: "c-ad-1", kind: "habit", subject: "relationship", text: "称呼主人为“阿姨”。", source_turn_id: "a2", source_excerpt: "希望它叫我阿姨。", suggested_slot: "owner_title", suggested_slot_value: "阿姨" }),
    candidate({ candidate_id: "c-ad-2", kind: "habit", subject: "pet", text: "窗边有一个为它准备的软垫子。", source_turn_id: "a2", source_excerpt: "我在窗边给它放了一个软垫子。", suggested_slot: "favorite_object", suggested_slot_value: "窗边软垫" }),
    candidate({ candidate_id: "c-ad-3", kind: "wish", subject: "relationship", text: "以后想一起去看海（未来愿望，不是过去经历）。", source_turn_id: "a3", source_excerpt: "以后想带它去看海。", suggested_slot: "wish_place", suggested_slot_value: "海边" }),
  ];
  return base(petId, "adopted", turns, candidates);
}

function base(petId: string, branch: ReceptionBranch, turns: ReceptionTurn[], candidates: IntakeCandidate[]): ReceptionSession {
  return {
    session_id: `fx-rs-${branch}`,
    pet_id: petId,
    branch,
    mode: "guided_notes",
    status: "active",
    host: fixtureHost,
    turns,
    candidates,
    draft_revision: 1,
    draft_expires_at: new Date(Date.now() + 24 * 3600_000).toISOString(),
    data_origin: "fixture",
  };
}

export function scriptedSession(branch: ReceptionBranch, petId: string, petName: string): ReceptionSession {
  return branch === "own_pet" ? ownPetSession(petId, petName) : adoptedSession(petId, petName);
}

// ---- 演示存档（本标签页 sessionStorage；不是服务器持久化） ----

interface FixtureArchive {
  notes: CareNote[];
  grants: MemoryGrant[];
  confirmationId: string | null;
  version: number;
  skipped: boolean;
}

const KEY = "petsoul.fixture.reception";
const EMPTY: FixtureArchive = { notes: [], grants: [], confirmationId: null, version: 0, skipped: false };

export function readArchive(): FixtureArchive {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as FixtureArchive) : EMPTY;
  } catch {
    return EMPTY;
  }
}

function writeArchive(archive: FixtureArchive) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(archive));
  } catch {
    /* 隐私模式下不可写：演示仍可在内存中完成本次流程 */
  }
}

export function markSkipped(): void {
  writeArchive({ ...readArchive(), skipped: true });
}

export function confirmFixture(request: IntakeConfirmationRequest, session: ReceptionSession): { notes: CareNote[]; grants: MemoryGrant[]; confirmationId: string } {
  const archive = readArchive();
  const confirmedAt = now();
  const confirmationId = `fx-conf-${archive.version + 1}`;
  const notes: CareNote[] = [];
  const grants: MemoryGrant[] = [];
  request.decisions.forEach((decision: CareNoteDecision, index) => {
    if (decision.target === "do_not_save") return;
    const cand = session.candidates.find((c) => c.candidate_id === decision.candidate_id);
    if (!cand) return;
    const note: CareNote = {
      note_id: `fx-note-${archive.version + 1}-${index}`,
      pet_id: session.pet_id,
      kind: cand.kind,
      subject: cand.subject,
      text: decision.text,
      target: decision.target,
      purposes: decision.target === "give_to_pet" ? decision.purposes : [],
      slot: decision.slot,
      slot_value: decision.slot_value,
      version: 1,
      confirmed_at: confirmedAt,
      supersedes_note_id: null,
      revoked_at: null,
    };
    notes.push(note);
    for (const purpose of note.purposes) {
      grants.push({ grant_id: `${note.note_id}-${purpose}`, note_id: note.note_id, note_version: 1, purpose, granted_at: confirmedAt, revoked_at: null });
    }
  });
  writeArchive({ notes, grants, confirmationId, version: archive.version + 1, skipped: false });
  return { notes, grants, confirmationId };
}

export function fixtureHomeWelcome(petId: string): HomeWelcome | null {
  const archive = readArchive();
  if (archive.version === 0 || archive.notes.length === 0) return null;
  const projection = projectMemory(petId, "home_interaction", archive.notes, archive.grants);
  if (projection.items.length === 0) return null;
  return buildHomeWelcome(projection, archive.version, archive.confirmationId);
}

export function resetFixtureReception(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

export type { IntakeConfirmationResult };
