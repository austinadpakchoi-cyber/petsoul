import type { PhotoRequestCommand, PhotoRequestResult, PhotoScene } from "@/shared/contracts";
import { isApiError } from "@/shared/api/errors";
import type { PetsService } from "@/shared/services/types";

export interface PendingPhotoIntent {
  userId: string;
  petId: string;
  key: string;
  body: PhotoRequestCommand;
}

function storageKey(userId: string, petId: string): string {
  return `petsoul:photo-intent:${encodeURIComponent(userId)}:${encodeURIComponent(petId)}`;
}

function valid(value: unknown, userId: string, petId: string): value is PendingPhotoIntent {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<PendingPhotoIntent>;
  return candidate.userId === userId && candidate.petId === petId && typeof candidate.key === "string" && candidate.key.length > 0 &&
    Boolean(candidate.body) && ["home", "train", "flight_adventure"].includes(String(candidate.body?.scene)) &&
    candidate.body?.narrative === (candidate.body?.scene === "flight_adventure" ? "fictional_adventure" : "daily_life");
}

export function readPhotoIntent(userId: string, petId: string): PendingPhotoIntent | null {
  try {
    const raw = sessionStorage.getItem(storageKey(userId, petId));
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return valid(parsed, userId, petId) ? parsed : null;
  } catch { return null; }
}

export function beginPhotoIntent(userId: string, petId: string, scene: PhotoScene, existing?: PendingPhotoIntent | null): PendingPhotoIntent {
  const pending = existing && valid(existing, userId, petId) ? existing : readPhotoIntent(userId, petId);
  if (pending) return pending;
  const intent: PendingPhotoIntent = { userId, petId, key: crypto.randomUUID(), body: { scene, narrative: scene === "flight_adventure" ? "fictional_adventure" : "daily_life" } };
  try { sessionStorage.setItem(storageKey(userId, petId), JSON.stringify(intent)); } catch { /* 当前页面仍持有 intent */ }
  return intent;
}

export function clearPhotoIntent(intent: PendingPhotoIntent): void {
  try { sessionStorage.removeItem(storageKey(intent.userId, intent.petId)); } catch { /* 无本地存储时只清当前页面 */ }
}

/** 只在明确收到受理或确定的客户端拒绝后释放键；网络/超时/5xx 仍可能已在服务端建任务。 */
export async function sendPhotoIntent(pets: PetsService, intent: PendingPhotoIntent): Promise<PhotoRequestResult> {
  try {
    const result = await pets.requestPhoto(intent.petId, intent.body, intent.key);
    clearPhotoIntent(intent);
    return result;
  } catch (error) {
    if (isApiError(error) && error.status !== null && error.status >= 400 && error.status < 500 &&
      error.status !== 408 && error.status !== 429 && error.code !== "IDEMPOTENCY_IN_PROGRESS") clearPhotoIntent(intent);
    throw error;
  }
}

export function photoIntentStillUncertain(error: unknown): boolean {
  return !isApiError(error) || error.status === null || error.status >= 500 || error.status === 408 || error.status === 429 || error.code === "IDEMPOTENCY_IN_PROGRESS";
}
