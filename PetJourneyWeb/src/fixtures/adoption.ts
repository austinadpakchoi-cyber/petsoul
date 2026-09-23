/**
 * 专属领养 fixture：原创伙伴（明确标注原创，不编造真实原型背景）。
 * 已领养/保留中的候选不可再领（演示“同一只只属于一个家庭”）。
 */
import type { AdoptionCandidate, AdoptResult } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { fixturePet } from "./world";

const pool: AdoptionCandidate[] = [
  { candidate_id: "fx-adopt-1", name: "小岚", species: "cat", personality: "慢热、爱在高处看风景", dream: "想去看一次真正的海", origin: "adopted_original", source_note: "PetSoul 原创伙伴（演示）", background_available: false, availability: "available", data_origin: "fixture" },
  { candidate_id: "fx-adopt-2", name: "栗子", species: "dog", personality: "热情、走路会蹦", dream: "想当一次小小飞行员", origin: "adopted_original", source_note: "PetSoul 原创伙伴（演示）", background_available: false, availability: "available", data_origin: "fixture" },
  { candidate_id: "fx-adopt-3", name: "阿绒", species: "rabbit", personality: "安静、喜欢收集叶子", dream: "开一家小小植物店", origin: "adopted_original", source_note: "PetSoul 原创伙伴（演示）", background_available: false, availability: "adopted", data_origin: "fixture" },
];

const adoptedByKey = new Map<string, AdoptResult>();

export function fixtureCandidates(): AdoptionCandidate[] {
  return pool;
}

export function fixtureAdopt(candidateId: string, key: string): AdoptResult {
  const replay = adoptedByKey.get(key);
  if (replay) return replay;
  const candidate = pool.find((c) => c.candidate_id === candidateId);
  if (!candidate) throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有找到这位伙伴。" });
  if (candidate.availability !== "available") {
    throw new ApiError({ kind: "http", status: 409, code: "ADOPTION_TAKEN", message: `${candidate.name} 刚刚有了自己的家。每一位伙伴只属于一个家庭。` });
  }
  candidate.availability = "adopted";
  const result: AdoptResult = { pet_id: "fx-adopt-pet", candidate_id: candidateId, adopted_at: new Date().toISOString() };
  adoptedByKey.set(key, result);
  lastAdoptedName = candidate.name;
  return result;
}

let lastAdoptedName = "小岚";

export function fixturePetName(petId: string): string {
  return petId === "fx-adopt-pet" ? lastAdoptedName : fixturePet.name;
}
