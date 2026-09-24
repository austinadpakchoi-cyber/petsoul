/**
 * 证件卡包的查询：live 用登记好的 queryKeys（按用户 + 宠物隔离）；fixture 只有一只演示宠物，用固定的 "fixture" 段。
 * 页面不自己决定“连不上就用演示数据”：fixture / live 由服务注册表按模式选。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { CharacterIdPhoto } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useActiveHome, useCurrentHousehold } from "@/shared/session/householdContext";
import { usePetCharacter } from "@/features/home/PetFigure";

const FIXTURE_SCOPE = "fixture";

function useScope() {
  const fixture = env.dataMode === "fixture";
  const { userId, pet } = useCurrentHousehold();
  const petId = pet?.pet_id ?? null;
  return {
    petId,
    enabled: fixture || Boolean(userId && petId),
    user: fixture ? FIXTURE_SCOPE : userId ?? "-",
    pet: fixture ? FIXTURE_SCOPE : petId ?? "-",
  };
}

/**
 * 卡包列表挂在 queryKeys.credentials（["credentials","list"]）前缀下：驾校领证时按 MODULE-MAP 失效的正是这个前缀，
 * 所以领证后卡包会自动重新读，不用改驾校模块。
 */
export function credentialListKey(user: string, pet: string) {
  return [...queryKeys.credentials, user, pet] as const;
}

export function useCredentialList() {
  const { life } = useServices();
  const scope = useScope();
  return useQuery({
    queryKey: credentialListKey(scope.user, scope.pet),
    queryFn: ({ signal }) => life.credentials(scope.petId ?? "", signal),
    enabled: scope.enabled,
  });
}

export function useJobList() {
  const { life } = useServices();
  const scope = useScope();
  return useQuery({
    queryKey: queryKeys.jobsFor(scope.user, scope.pet),
    queryFn: ({ signal }) => life.jobs(scope.petId ?? "", signal),
    enabled: scope.enabled,
  });
}

export function useCredentialDetail(credentialId: string | undefined) {
  const { life } = useServices();
  const scope = useScope();
  return useQuery({
    queryKey: queryKeys.credentialFor(scope.user, scope.pet, credentialId ?? "-"),
    queryFn: ({ signal }) => life.credential(credentialId!, signal),
    enabled: scope.enabled && Boolean(credentialId),
  });
}

export interface WalletPet {
  name: string;
  /** 物种代码（dog / cat …），护照底部代号行用；读不到时为 null。 */
  species: string | null;
  /** 服务端给的照片（主人上传的，或服务端生成的写实证件照）；没有时由 petPortraitUrl 决定用什么（不写名字首字）。 */
  photoUrl: string | null;
  /** 照片是服务端生成的形象：照片位标“AI 生成”（后端契约要求标注）。只有家园快照带这个标记。 */
  photoGenerated: boolean;
  /** 角色状态里的证件照（CharacterState.id_photo）；能力没开、读不到、出错、演示模式时为 null。用不用它由 credentialPhotoUrl / coverAvatarUrl 决定。 */
  idPhoto: CharacterIdPhoto | null;
  /** fixture 下宠物名来自演示家园快照，读到之前不渲染卡包封面。 */
  ready: boolean;
}

export function useWalletPet(): WalletPet {
  const fixture = env.dataMode === "fixture";
  const { pet: selected } = useCurrentHousehold();
  const home = useActiveHome({ staleTime: 60_000 });
  const snapshot = home.data?.pet ?? null;
  // 证件照：直接复用小窝的 usePetCharacter（只读引用 home/PetFigure.tsx）——先看 meta 里 character.state 是否 available，
  // 没开就不发这次读取；只在 live 下读；纯读，绝不触发生成；查询键 queryKeys.characterFor 与小窝同一个，缓存共用。出错一律当作没有证件照。
  const character = usePetCharacter(fixture ? (snapshot?.pet_id ?? null) : (selected?.pet_id ?? null));
  const idPhoto = character?.id_photo ?? null;
  if (fixture) {
    return {
      name: snapshot?.name ?? "TA",
      species: snapshot?.species ?? null,
      photoUrl: snapshot?.photo_url ?? null,
      photoGenerated: snapshot?.photo_generated === true,
      idPhoto,
      ready: !home.isLoading,
    };
  }
  // live：名字和照片用当前选中的宠物（马上就有）；家园快照必须就是这一只，才拿它的“生成形象”标记（切宠物的瞬间不串）。
  const matched = snapshot && selected && snapshot.pet_id === selected.pet_id ? snapshot : null;
  const photoUrl = selected?.photo_url ?? matched?.photo_url ?? null;
  return {
    name: selected?.name ?? matched?.name ?? "TA",
    species: selected?.species ?? matched?.species ?? null,
    photoUrl,
    photoGenerated: Boolean(photoUrl && matched?.photo_generated && matched.photo_url === photoUrl),
    idPhoto,
    ready: true,
  };
}

function prefersReducedMotion(): boolean {
  try {
    return typeof window.matchMedia !== "function" || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return true;
  }
}

export const FLIP_OUT_MS = 170;
export const FLIP_IN_MS = 230;

/**
 * 正反翻转：转到侧面（看不见）时换面，再转回来——正反两面高度不同也不会跳。
 * 用户要求减少动效（或环境不支持查询）时直接换面，不做 3D 动画。
 */
export function useFlip() {
  const [face, setFace] = useState<"front" | "back">("front");
  const [phase, setPhase] = useState<"idle" | "out" | "in">("idle");
  const timers = useRef<number[]>([]);
  useEffect(() => () => timers.current.forEach((timer) => window.clearTimeout(timer)), []);
  const flip = useCallback(() => {
    if (phase !== "idle") return;
    const next = face === "front" ? "back" : "front";
    if (prefersReducedMotion()) {
      setFace(next);
      return;
    }
    setPhase("out");
    timers.current.push(
      window.setTimeout(() => {
        setFace(next);
        setPhase("in");
        timers.current.push(window.setTimeout(() => setPhase("idle"), FLIP_IN_MS));
      }, FLIP_OUT_MS),
    );
  }, [face, phase]);
  return { face, phase, flip };
}

export { prefersReducedMotion };
