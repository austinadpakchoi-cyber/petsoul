/**
 * TA 的档案（/me/dna）的纯数据部分：栏目表、表单与请求体互转、保存前检查、草稿来源的说法、冲突识别、行为倾向整理。
 * - 栏目上限与后端 PetDNA 一致（owner_title ≤12、nicknames ≤5 条、personality ≤80、voice_style / catchphrase ≤40、
 *   爱吃的 / 喜欢的地方 / 爱好 / 小习惯各 ≤8 条、害怕的东西 ≤6 条，每条 ≤40；shared_memories ≤8 条、每条 ≤80）：
 *   在前端先拦住，不让后端整单拒绝，也不让它悄悄截断。
 * - 栏目名与后端行为出处里的 field_label 是同一套叫法（性格、说话的样子、口头禅、小习惯、爱好、喜欢的地方、爱吃的、害怕的东西），
 *   “出自性格：「……」”才能和上面的栏目对得上。
 * - 清洗规则跟后端 normalize 一致：去首尾空白；列表每条把连续空白并成一个、去空、去重。
 */
import type { BehaviorEvidence, BehaviorPreference, BehaviorTrait, PetBehavior, PetDNA } from "@/shared/contracts";
import { isApiError } from "@/shared/api/errors";

export type TextKey = "owner_title" | "personality" | "voice_style" | "catchphrase";
export type ListKey = "nicknames" | "favorite_foods" | "favorite_places" | "hobbies" | "habits" | "fears" | "shared_memories";
export type FieldKey = TextKey | ListKey;

interface FieldBase {
  label: string;
  /** 编辑时栏目下的一句小字 */
  hint?: string;
  placeholder: string;
}
export interface TextFieldSpec extends FieldBase {
  kind: "text";
  key: TextKey;
  max: number;
  multiline?: boolean;
}
export interface ListFieldSpec extends FieldBase {
  kind: "list";
  key: ListKey;
  maxItems: number;
  itemMax: number;
}
export type FieldSpec = TextFieldSpec | ListFieldSpec;
export interface FieldGroup {
  id: string;
  title: string;
  fields: FieldSpec[];
}

/** 列表栏的占位字（连“例如：”）不超过 10 个字：320 宽手机上“添上”旁边的输入框只放得下这么多。 */
export const DNA_GROUPS: FieldGroup[] = [
  {
    id: "call",
    title: "怎么称呼",
    fields: [
      { kind: "text", key: "owner_title", label: "TA 怎么叫你", placeholder: "例如：妈妈、姐姐", max: 12 },
      { kind: "list", key: "nicknames", label: "家里叫 TA 的小名", placeholder: "例如：团子", maxItems: 5, itemMax: 40 },
    ],
  },
  {
    id: "temper",
    title: "TA 的性子",
    fields: [
      { kind: "text", key: "personality", label: "性格", placeholder: "例如：慢热，熟了以后特别黏人", max: 80, multiline: true },
      { kind: "text", key: "voice_style", label: "说话的样子", placeholder: "例如：慢吞吞、爱撒娇", max: 40 },
      { kind: "text", key: "catchphrase", label: "口头禅", hint: "也可以是 TA 常发出的声音", placeholder: "例如：喵呜～", max: 40 },
    ],
  },
  {
    id: "likes",
    title: "TA 喜欢的",
    fields: [
      { kind: "list", key: "favorite_foods", label: "爱吃的", placeholder: "例如：冻干小鱼", maxItems: 8, itemMax: 40 },
      { kind: "list", key: "favorite_places", label: "喜欢的地方", placeholder: "例如：窗台", maxItems: 8, itemMax: 40 },
      { kind: "list", key: "hobbies", label: "爱好", placeholder: "例如：晒太阳", maxItems: 8, itemMax: 40 },
    ],
  },
  {
    id: "days",
    title: "TA 的日常",
    fields: [
      { kind: "list", key: "habits", label: "小习惯", placeholder: "例如：睡前踩奶", maxItems: 8, itemMax: 40 },
      { kind: "list", key: "fears", label: "害怕的东西", placeholder: "例如：打雷", maxItems: 6, itemMax: 40 },
    ],
  },
  {
    id: "between",
    title: "你们之间",
    fields: [
      {
        kind: "list",
        key: "shared_memories",
        label: "小暗号和趣事",
        hint: "只有你们俩懂的话、一起做过的傻事",
        placeholder: "例如：一摇铃就跑来",
        maxItems: 8,
        itemMax: 80,
      },
    ],
  },
];

export const TEXT_KEYS: TextKey[] = ["owner_title", "personality", "voice_style", "catchphrase"];
export const LIST_KEYS: ListKey[] = ["nicknames", "favorite_foods", "favorite_places", "hobbies", "habits", "fears", "shared_memories"];

/* ---------------- 表单 ---------------- */

export type DnaForm = Record<TextKey, string> & Record<ListKey, string[]>;
/** 每个列表栏目输入框里还没点“添上”的字。 */
export type PendingItems = Partial<Record<ListKey, string>>;

export function formFrom(dna: PetDNA): DnaForm {
  const form = {} as DnaForm;
  for (const key of TEXT_KEYS) form[key] = dna[key] ?? "";
  for (const key of LIST_KEYS) form[key] = [...(dna[key] ?? [])];
  return form;
}

/** 一条标签的清洗：和后端一样，去首尾空白、中间连续空白并成一个。 */
export function cleanItem(text: string): string {
  return text.split(/\s+/).filter(Boolean).join(" ");
}

/** 整体保存的请求体：每一栏都带上（后端整体替换）；空字符串写成 null，列表去空去重。 */
export function bodyFrom(form: DnaForm): PetDNA {
  const body = {} as PetDNA;
  for (const key of TEXT_KEYS) body[key] = form[key].trim() || null;
  for (const key of LIST_KEYS) body[key] = [...new Set(form[key].map(cleanItem).filter(Boolean))];
  return body;
}

export function sameBody(a: PetDNA, b: PetDNA): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** 保存时把输入框里还没点“添上”的那条也算进去（满了就不加，重复的不加）。 */
export function withPending(form: DnaForm, pending: PendingItems): DnaForm {
  const next = { ...form };
  for (const field of listFields()) {
    const item = cleanItem(pending[field.key] ?? "");
    if (item && !next[field.key].includes(item) && next[field.key].length < field.maxItems) next[field.key] = [...next[field.key], item];
  }
  return next;
}

function listFields(): ListFieldSpec[] {
  return DNA_GROUPS.flatMap((group) => group.fields).filter((field): field is ListFieldSpec => field.kind === "list");
}

/** 按字符数（与后端一致，一个表情算一个）。 */
export function charCount(text: string): number {
  return Array.from(text).length;
}

/** 保存前的检查：超长、超条数就不发（输入框已限长，这里兜住读进来就超的旧数据）。 */
export function formProblems(form: DnaForm): string[] {
  const problems: string[] = [];
  for (const group of DNA_GROUPS) {
    for (const field of group.fields) {
      if (field.kind === "text") {
        if (charCount(form[field.key].trim()) > field.max) problems.push(`“${field.label}”最多写 ${field.max} 个字，改短一点再保存。`);
      } else if (form[field.key].length > field.maxItems) {
        problems.push(`“${field.label}”最多 ${field.maxItems} 条，去掉几条再保存。`);
      } else if (form[field.key].some((item) => charCount(cleanItem(item)) > field.itemMax)) {
        problems.push(`“${field.label}”每条最多 ${field.itemMax} 个字，改短一点再保存。`);
      }
    }
  }
  return problems;
}

/* ---------------- 草稿与保存结果 ---------------- */

const DRAFT_SOURCE_TEXT: Record<string, string> = {
  adoption_profile: "领养时的介绍",
  owner_bio: "TA 的简介",
  reception_notes: "你入住时说的话",
};

/** 未确认草稿的一句提示：按草稿的真实来源写，不说它没有的来源。 */
export function draftNote(sources: string[] | undefined): string {
  const parts = [...new Set(sources ?? [])].map((source) => DRAFT_SOURCE_TEXT[source]).filter(Boolean);
  if (!parts.length) return "还没写过 TA 的档案。写下 TA 的样子，确认后 TA 就按这份来。";
  const joined = parts.join("和");
  return `这是按${/^[A-Za-z]/.test(joined) ? " " : ""}${joined}整理的，看看对不对，确认后 TA 就按这份来。`;
}

/** 家人在你读取之后改过共用那部分（409，details.reason = dna_version_conflict）。 */
export function isVersionConflict(error: unknown): boolean {
  return isApiError(error) && error.details?.reason === "dna_version_conflict";
}

/** 没保存上时的一句话（冲突另有提示，不走这里）。 */
export function saveFailureText(error: unknown): string {
  if (!isApiError(error)) return "没保存上，再试一次。";
  if (error.kind === "network" || error.kind === "timeout") return "信号断了一下，没保存上，再试一次。";
  if (error.isAuth) return "登录状态过期了，重新登录后再保存。";
  if (error.code === "VALIDATION_FAILED") return "有一栏写得太长或太多了，改短一点再保存。";
  if (error.code === "NOT_FOUND") return "找不到 TA 的档案了，回到上一页再进来看看。";
  return error.playerMessage || "没保存上，再试一次。";
}

/* ---------------- 行为倾向 ---------------- */

export type LeanTone = "leaf" | "coral" | "neutral";

const TRAIT_STATUS: Record<Exclude<BehaviorTrait["status"], "uncertain">, { text: string; tone: LeanTone; rank: number }> = {
  applied: { text: "是这样", tone: "leaf", rank: 0 },
  negated: { text: "不是这样", tone: "neutral", rank: 1 },
  outweighed: { text: "被别的说法盖过", tone: "neutral", rank: 2 },
};

export interface ShownTrait {
  trait: BehaviorTrait;
  text: string;
  tone: LeanTone;
}

/** 列出来的性子：说不准的不在这里（它们的原话在“还没想明白的”里），用上的在前。 */
export function shownTraits(behavior: PetBehavior): ShownTrait[] {
  return (behavior.traits ?? [])
    .flatMap((trait) => (trait.status === "uncertain" ? [] : [{ trait, ...TRAIT_STATUS[trait.status] }]))
    .sort((a, b) => a.rank - b.rank)
    .map(({ trait, text, tone }) => ({ trait, text, tone }));
}

export function leaning(weight: number): { text: string; tone: LeanTone; rank: number } {
  if (weight > 1) return { text: "更愿意", tone: "leaf", rank: 0 };
  if (weight < 1) return { text: "不太愿意", tone: "coral", rank: 1 };
  return { text: "照常", tone: "neutral", rank: 2 };
}

/** 想做的事、想去的地方：更愿意的在前，其次不太愿意，照常的在最后；同一档保持原来的顺序。只说倾向，不露倍数。 */
export function shownPreferences(behavior: PetBehavior): BehaviorPreference[] {
  return [...(behavior.preferences ?? [])].sort((a, b) => leaning(a.weight).rank - leaning(b.weight).rank);
}

/** 同一栏的同一句只列一次（一句话里可能命中同一种说法两次）。 */
export function uniqueEvidence(items: BehaviorEvidence[] | undefined): BehaviorEvidence[] {
  const seen = new Set<string>();
  return (items ?? []).filter((item) => {
    const key = `${item.field}|${item.phrase}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
