import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { CharacterAsset, CharacterIdPhoto, CharacterPose, CharacterReason, CharacterState, PetPrivateSummary } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { toApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useOptionalCurrentHousehold } from "@/shared/session/householdContext";
import { Button } from "@/shared/ui";
import { PetPortrait, petPortraitUrl } from "@/features/pets/PetPortrait";
import "./id-photo.css";

/**
 * TA 的专属世界形象（CR-PLAYER-CHARACTER-01，契约 `GET /pets/{pet_id}/character`）。
 * 上传照片后自动排队（用户 2026-09-23 决定不再逐次询问授权）；这里只读状态，正常路径没有任何“生成”或“确认”按钮。
 * - `active` 与 `candidate` 分开：新版本在建或失败时，旧的生效形象照常显示。
 * - `absent` 是“还没有任务”，不转圈；`unknown` 是“结果还没确认”，不写成没生成、不自动重发。
 * - 只把实际验证过 alpha 的姿态图放进场景；按 `content_box` 与 `anchor` 落位，不按画布尺寸摆。
 */

/**
 * 能放进场景的姿态图：alpha 实测可用，且不透明占比不在两端——接近 1 基本是背景没抠掉的方图，
 * 接近 0 可能主体被裁没了（阈值只是前端兜底，发布质量由后端校验负责）。
 */
function usable(asset: CharacterAsset): boolean {
  const box = asset.content_box;
  return asset.has_alpha && asset.opaque_ratio > 0.02 && asset.opaque_ratio < 0.95 && asset.width > 0 && asset.height > 0 && box.bottom > box.top && box.right > box.left;
}

export function sceneAsset(state: CharacterState | null, pose: CharacterPose = "neutral_full"): CharacterAsset | null {
  const assets = state?.active?.assets.filter(usable) ?? [];
  return assets.find((asset) => asset.pose === pose) ?? assets.find((asset) => asset.pose === "neutral_full") ?? null;
}

/**
 * 同一套形象里各姿态按中性站姿的身体高度定比例（与 A 约定的渲染规则）：
 * 容器高度 = 中性站姿主体高度，其他姿态用同一像素比例画——趴着睡的不会被放大成“站着那么高”。
 * 这一套里没有可用的中性站姿时，才按这张图自己的主体高度撑满。
 */
export function referenceBodyHeight(state: CharacterState | null, asset: CharacterAsset): number {
  const neutral = state?.active?.assets.find((a) => a.pose === "neutral_full" && usable(a));
  const box = (neutral ?? asset).content_box;
  return box.bottom - box.top;
}

/**
 * 后端 `blocked_reason` / `candidate.reason` / 调整结果 `reason` 给的是原因码。下面对契约 `CharacterReason` 穷举
 * （漏一个就编译不过）；字段本身仍是 string，表外的新码显示泛化说法，**绝不把原始码显示给主人**。
 * 先写成普通对象再赋给 Record：契约增减 `already_queued` 这类码时，多出的键不报错、缺的键照样报错。
 */
const REASON_COPY = {
  // 排队前就挡住（consent_missing / consent_revoked 已随“不再询问授权”从契约删除）
  no_reference_photo: "还没有 TA 的照片，暂时没法准备形象。",
  pet_has_no_household: "TA 还没有加入家庭，暂时没法准备形象。",
  species_unsupported: "这个物种的形象暂时还画不了。",
  provider_unavailable: "形象服务暂时不可用，稍后再看看。",
  not_configured: "形象服务暂时不可用，稍后再看看。",
  // 执行中途停下
  generated_reference_only: "现在只有 AI 生成的基准照，需要一张你上传的真实照片。",
  reference_changed: "你换了照片，这一版没有用上，会按新照片来。",
  budget_denied: "今天准备形象的次数用完了，明天再看看。",
  daily_cap: "今天准备形象的次数用完了，明天再看看。",
  rejected: "这次图片服务没有接下这个请求，没有画成。",
  timeout: "这次等了太久没有回音，结果还没确认。",
  unconfirmed: "上一次的结果还没确认。",
  unknown_result: "上一次的结果还没确认。",
  transparency_not_requested: "这一版背景没能去干净，没有用上。",
  attempts_exhausted: "试了几次都没有通过检查。",
  // 画出来了但不能用（图像校验）
  not_png: "这一版图片格式有问题，没有用上。",
  undecodable: "这一版图片格式有问题，没有用上。",
  interlaced_unsupported: "这一版图片格式有问题，没有用上。",
  palette_unsupported: "这一版图片格式有问题，没有用上。",
  bit_depth_unsupported: "这一版图片格式有问题，没有用上。",
  too_large_to_check: "这一版图片格式有问题，没有用上。",
  no_alpha_channel: "这一版背景没能去干净，没有用上。",
  opaque_background: "这一版背景没能去干净，没有用上。",
  // 透明背景在上游被压平成灰白格子（validate.py）；对玩家就是“背景没去干净”
  checkerboard_drawn: "这一版背景没能去干净，没有用上。",
  empty_subject: "这一版没画出 TA，没有用上。",
  multiple_subjects: "这一版画里不止 TA 一个，没有用上。",
  subject_cut_off: "这一版把 TA 画得不完整，没有用上。",
  subject_too_large: "这一版 TA 的大小不合适，没有用上。",
  subject_too_small: "这一版 TA 的大小不合适，没有用上。",
  // 证件照自己的校验（CR-6C2B-IDPHOTO，validate.py / id_photo.py）；和形象共用这张码表
  photo_not_to_bottom: "这一版证件照没拍成头和上半身，没有用上。",
  photo_headroom_off: "这一版证件照头顶留得太挤或太空，没有用上。",
  photo_head_cut_off: "这一版证件照 TA 的头太靠边，做头像会被裁掉，没有用上。",
  photo_too_small: "这一版证件照尺寸太小，没有用上。",
  photo_wrong_shape: "这一版证件照比例不对，没有用上。",
  photo_blank: "这一版证件照是空白的，没有用上。",
  // 调整形象时已有一版在排队/生成（`web_character/service.py` regenerate）
  already_queued: "新的形象已经在准备了。",
};
const REASON_TEXT: Record<CharacterReason, string> = REASON_COPY;

export function reasonText(code: string | null | undefined): string | null {
  if (!code) return null;
  return Object.prototype.hasOwnProperty.call(REASON_TEXT, code) ? (REASON_TEXT as Record<string, string>)[code] : "这一次没有准备好。";
}

/** 没有可放进场景的形象时，写给主人的真实状态。 */
export function characterNote(state: CharacterState | null): string | null {
  if (!state || sceneAsset(state)) return null;
  if (state.status === "queued" || state.status === "running") return "正在准备 TA 的形象";
  if (state.status === "failed") return "形象这次没画成";
  if (state.status === "unknown") return "形象结果还没确认";
  if (state.status === "absent") return state.blocked_reason ? "还没有星球形象" : null;
  return null;
}

function useCapability(key: string): boolean {
  const { platform } = useServices();
  const meta = useQuery({ queryKey: queryKeys.meta, queryFn: () => platform.meta(), staleTime: 60_000, enabled: env.dataMode === "live" });
  return meta.data?.capabilities.some((capability) => capability.key === key && capability.status === "available") ?? false;
}

/** 纯读；接口未上线（meta 报 not_implemented）时不发请求，页面退回原照肖像。有在建任务时有界只读复查。 */
export function usePetCharacter(petId: string | null | undefined): CharacterState | null {
  const { pets } = useServices();
  const userId = useOptionalCurrentHousehold()?.userId ?? null;
  const available = useCapability("character.state");
  const state = useQuery({
    queryKey: queryKeys.characterFor(userId ?? "-", petId ?? "-"),
    queryFn: ({ signal }) => pets.character(petId!, signal),
    enabled: env.dataMode === "live" && available && Boolean(petId),
    staleTime: 15_000,
    retry: false,
    refetchInterval: (query) => (query.state.data?.status === "queued" || query.state.data?.status === "running" ? 20_000 : false),
  });
  return state.data ?? null;
}

/**
 * 宠物面板里的形象说明与可选入口。原因只显示玩家说法；“没开生成照片许可”给去家庭设置的路。
 * 入口只在接口可用且服务端允许（`can_regenerate`）时出现；网络回执不确定时保留同一幂等键（走请求头）。
 * 注意：新账号第一只宠物上传时家庭许可必然还是关着的，后端不会自动排队——这是当前产品顺序的真实状态，
 * 这里不伪造 queued，只如实说明并在许可打开后提供可选入口。
 */
export function AdjustCharacter({ petId, state }: { petId: string; state: CharacterState }) {
  const { pets } = useServices();
  const queryClient = useQueryClient();
  const userId = useOptionalCurrentHousehold()?.userId ?? null;
  const available = useCapability("character.regenerate");
  const keyRef = useRef(newIdempotencyKey("character-regenerate"));
  const adjust = useMutation({
    mutationFn: () => pets.regenerateCharacter(petId, { pose: "neutral_full", note: null }, keyRef.current),
    onSuccess: () => {
      keyRef.current = newIdempotencyKey("character-regenerate");
      void queryClient.invalidateQueries({ queryKey: queryKeys.characterFor(userId ?? "-", petId) });
    },
  });
  const pending = state.candidate?.status === "queued" || state.candidate?.status === "running";
  const code = state.candidate?.reason ?? state.blocked_reason;
  const why = pending ? "新的形象正在准备。" : reasonText(code);
  const label = state.active ? "调整形象" : state.status === "failed" || state.status === "unknown" ? "重新准备 TA 的形象" : "为 TA 准备形象";
  return (
    <div className="ps-character-adjust" data-testid="character-adjust">
      {why ? <p className="ps-character-adjust__note">{why}</p> : null}
      {available && state.can_regenerate ? (
        <Button variant="ghost" size="sm" loading={adjust.isPending} onClick={() => adjust.mutate()}>{label}</Button>
      ) : null}
      {adjust.data && !adjust.data.accepted ? <p className="ps-character-adjust__note" role="status">{reasonText(adjust.data.reason) ?? "这次没有排上。"}</p> : null}
      {adjust.isError ? <p className="ps-character-adjust__note" role="alert">提交结果还没确认：{toApiError(adjust.error).message} 再点一次会沿用同一次请求，不会重复扣费。</p> : null}
      <IdPhotoAdjust petId={petId} idPhoto={state.id_photo} canRequest={state.can_regenerate === true} blockedReason={state.blocked_reason} characterBusy={pending} />
    </div>
  );
}

/** 证件照的原因用证件照的说法：和形象共用一张码表（CharacterReason），这里把“形象”换成“证件照”。 */
export function idPhotoReasonText(code: string | null | undefined): string | null {
  if (code === "already_queued") return "新的证件照已经在准备了。";
  return reasonText(code)?.replaceAll("形象", "证件照") ?? null;
}

/**
 * 证件照（CR-6C2B-IDPHOTO）：护照、居民证、驾照都用这一张。
 * - 用户定了存量宠物不批量补，老宠物只能在这里拿到第一张：没有生效的证件照时写“生成证件照”，已有生成的才写“重画证件照”。
 * - 在排、在画时不给按钮；结果还没确认（unknown）时也不给——那可能已经发出去了，再点会让主人再付一次。
 * - 用的是 TA 现有照片（companion_portrait：没有真实照片的宠物）时，后端会如实拒绝重画，这里不给按钮。
 * - 能不能发起听服务端的 `can_regenerate`（上层传进来的 canRequest）：没有原照、物种画不了、没有家、图片服务不可用时它是 false，
 *   后端证件照入口（web_character/id_photo.py 的 request_in）挡的正是这一组前置条件，点了必然被拒——不给这种死路按钮，
 *   按 `blocked_reason` 用人话说为什么；没有照片的宠物就写“还没有 TA 的照片”，不承诺补传照片的入口。
 *   形象（整套角色）在排、在画时 can_regenerate 也是 false、blocked_reason 为空，证件照入口其实不看它：这里偏保守，说“等形象好了再来”、不给按钮。
 * 入口只在 meta 报 `character.id_photo` 可用时出现；网络回执不确定时沿用同一个幂等键。
 */
export function IdPhotoAdjust({ petId, idPhoto, canRequest, blockedReason = null, characterBusy = false }: {
  petId: string;
  idPhoto: CharacterIdPhoto | null | undefined;
  /** 服务端此刻允不允许发起：`CharacterState.can_regenerate === true` */
  canRequest: boolean;
  /** 不允许时服务端给的原因：`CharacterState.blocked_reason` */
  blockedReason?: string | null;
  /** 形象（整套角色）正在排或在画——can_regenerate 因此为 false 时，用来说明为什么这会儿不给按钮 */
  characterBusy?: boolean;
}) {
  const { pets } = useServices();
  const queryClient = useQueryClient();
  const userId = useOptionalCurrentHousehold()?.userId ?? null;
  const available = useCapability("character.id_photo");
  const keyRef = useRef(newIdempotencyKey("id-photo"));
  const request = useMutation({
    mutationFn: () => pets.regenerateIdPhoto(petId, keyRef.current),
    onSuccess: () => {
      keyRef.current = newIdempotencyKey("id-photo");
      void queryClient.invalidateQueries({ queryKey: queryKeys.characterFor(userId ?? "-", petId) });
    },
  });
  if (!available) return null;
  const status = idPhoto?.status ?? "absent";
  const photoUrl = status === "ready" ? idPhoto?.url ?? null : null;
  const generated = Boolean(photoUrl) && idPhoto?.source === "generated";
  const ownPhoto = Boolean(photoUrl) && idPhoto?.source === "companion_portrait";
  const busy = status === "queued" || status === "running";
  const note = busy
    ? "证件照正在准备。"
    : status === "unknown"
      ? "上一次证件照的结果还没确认，先别重复点。"
      : status === "failed"
        ? idPhotoReasonText(idPhoto?.reason) ?? "证件照这次没画成。"
        : ownPhoto
          ? "证件照先用 TA 现在的照片。"
          : photoUrl
            ? null
            : "还没有证件照：护照、居民证、驾照都会用它。";
  // 证件照自己不在忙、结果已确认、也不是用 TA 现在的照片：本来可以发起，再看服务端此刻允不允许。
  const eligible = !busy && status !== "unknown" && !ownPhoto;
  const canAsk = eligible && canRequest;
  const verb = generated ? "重画" : "生成";
  const blocked = eligible && !canRequest
    ? idPhotoReasonText(blockedReason) ?? (characterBusy ? `形象正在准备，好了以后再来${verb}证件照。` : `现在还不能${verb}证件照。`)
    : null;
  return (
    <div className="ps-idphoto-adjust" data-testid="id-photo-adjust">
      {photoUrl ? <img className="ps-idphoto-adjust__photo" src={photoUrl} alt="TA 的证件照" /> : null}
      <div className="ps-idphoto-adjust__body">
        {note ? <p className="ps-character-adjust__note">{note}</p> : null}
        {blocked ? <p className="ps-character-adjust__note" data-testid="id-photo-blocked">{blocked}</p> : null}
        {canAsk ? (
          <Button variant="ghost" size="sm" loading={request.isPending} onClick={() => request.mutate()}>
            {generated ? "重画证件照" : "生成证件照"}
          </Button>
        ) : null}
        {request.data?.accepted ? <p className="ps-character-adjust__note" role="status">证件照已经在准备了。</p> : null}
        {request.data && !request.data.accepted ? <p className="ps-character-adjust__note" role="status">{idPhotoReasonText(request.data.reason) ?? "这次没有排上。"}</p> : null}
        {request.isError ? <p className="ps-character-adjust__note" role="alert">提交结果还没确认：{toApiError(request.error).message} 再点一次会沿用同一次请求，不会重复扣费。</p> : null}
      </div>
    </div>
  );
}

export function PetFigure({ pet, state, pose = "neutral_full" }: { pet: PetPrivateSummary; state: CharacterState | null; pose?: CharacterPose }) {
  const asset = sceneAsset(state, pose);
  if (asset && state?.active) {
    const round = (value: number) => Math.round(value * 100) / 100;
    // 中性站姿的主体高度正好占满容器；落地点对准容器底边中点。
    const heightPct = round((asset.height / referenceBodyHeight(state, asset)) * 100);
    return (
      <span className="ps-pet-figure is-character" data-testid="pet-character" data-revision={state.active.revision} data-anchor-measured={asset.anchor.measured ? "true" : "false"}>
        <span className="ps-pet-figure__shadow" aria-hidden="true" />
        <img
          src={asset.url}
          alt={`${pet.name}的星球形象`}
          style={{ height: `${heightPct}%`, aspectRatio: `${asset.width} / ${asset.height}`, transform: `translate(${round(-asset.anchor.x * 100)}%, ${round((1 - asset.anchor.y) * 100)}%)` }}
        />
      </span>
    );
  }
  const portrait = petPortraitUrl(pet.photo_url);
  // 形象在准备时（真实 queued/running）才有光晕与光点；absent/failed/unknown 不放任何“在忙”的动效。
  // 场景里 TA 身下不再挂状态小牌（2026-09-24 巡检：小窝里一直挂着“还没有星球形象”）。PetFigure 只画在小窝场景里（HomeScene）；
  // 状态照样说得出：TA 的无障碍名称、点 TA 冒出的气泡和“陪 TA 待一会儿”面板都带 characterNote，“TA 的形象”页（/me/look）照旧写一行。
  const preparing = state?.status === "queued" || state?.status === "running";
  return (
    <span className={`ps-pet-figure is-portrait${preparing ? " is-preparing" : ""}`}>
      {preparing ? <span className="ps-pet-figure__halo" aria-hidden="true" /> : null}
      {/* 不用名字首字（用户 2026-09-24）：有照片用照片；演示模式没照片用授权的测试小灰猫；live 没照片显示爪印占位。 */}
      <span className={`ps-living-pet__identity${portrait ? " has-photo" : ""}`}>
        {portrait ? <img src={portrait} alt="" /> : <PetPortrait name={pet.name} photoUrl={null} size={56} />}
        <small>{pet.photo_generated ? "AI 生成形象" : portrait ? pet.name : "暂无照片"}</small>
      </span>
      {preparing ? (
        <span className="ps-pet-figure__magic" aria-hidden="true" data-testid="pet-character-preparing">
          <b /><b /><b /><b />
          <i /><i /><i /><i /><i />
        </span>
      ) : null}
    </span>
  );
}
