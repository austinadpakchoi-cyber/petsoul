/**
 * 我的 · TA 的形象（/me/look）：从“我的”进来的全屏页，左上角回 /me，不挂底栏（方案第 9 节“TA 的形象（调整形象）”），
 * 写法照 /me/dna、/me/reports（WorldGate 守）。
 * - 复用小窝的 usePetCharacter（纯读形象）与 AdjustCharacter（“调整形象”，里面已带证件照一节 IdPhotoAdjust），
 *   只读引用 home/PetFigure.tsx，不改它。按钮出不出现全由它们按能力表与服务端的 can_regenerate、证件照状态决定，这里不另加按钮。
 * - 顶部是 TA 现在的样子：头像一律 PetPortrait（有照片用照片，演示用演示小灰猫，live 没照片是爪印，不写名字首字）；
 *   已有生效的星球形象时，下面再放那张站姿图（只放 sceneAsset 认可、验过透明的那张，按中性站姿的身体高度落位）。
 * - 一句说明：形象和证件照都照着 TA 的照片画；这一页真有“生成证件照”按钮时，才顺带说老伙伴在这里补第一张证件照
 *   （能力表里证件照没开、服务端这会儿不让发起时，这句不提按钮）；没有照片的伙伴（no_reference_photo）这句只说照片是来源
 *   （画不了由下面两节各说一次），不许诺页面上没有的按钮。
 * - 补一张照片（PUT /pets/{id}/photo，只补不换）：只在这只宠物一张照片都没有、而且是自己的宠物时出现，见 canAddPhoto；
 *   上传本身不生图，成功后刷新相关缓存，页面换成照片；证件照照现有规则由主人自己在下面点，这里不替主人发起。
 * - 读的状态分清：能力表说形象没开 → 说暂时看不了，不发形象请求；还在读 → 等一等；读失败 → 统一错误态可重试，
 *   不当成“没有形象”。演示模式没有真实形象：温和说明，不编数据、不放按钮。
 */
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import type { CharacterAsset, CharacterState, PetOrigin } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { toApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useOptionalCurrentHousehold } from "@/shared/session/householdContext";
import { Button, ErrorState, Icon, LoadingState, Page } from "@/shared/ui";
import { AdjustCharacter, characterNote, referenceBodyHeight, sceneAsset, usePetCharacter } from "@/features/home/PetFigure";
import { PetPortrait } from "@/features/pets/PetPortrait";
import { WorldGate } from "@/features/world_map/WorldGate";
import { useCurrentPet, type CurrentPet } from "@/features/memories/currentPet";
import "./me.css";
import "./look.css";

/** 页面上那一句说明：这一页真的会出现“生成证件照”按钮时，才顺带告诉老伙伴在哪儿补第一张证件照。 */
export const LOOK_INTRO_WITH_ID_PHOTO = "TA 在星球上的样子和证件照，都照着 TA 的照片来画；早些住进来、还没有证件照的伙伴，在这里点“生成证件照”补一张最方便。";
export const LOOK_INTRO = "TA 在星球上的样子照着 TA 的照片来画；画好以后觉得不像，可以在这里调整。";
/**
 * 没有照片（服务端 blocked_reason = no_reference_photo）：这句只说照片是形象和证件照的来源；“现在画不了”由下面形象、证件照
 * 两节各自那句（“还没有 TA 的照片，暂时没法准备形象 / 证件照。”）说，这里不再说第三遍。
 * 不提“生成证件照”；补照片的入口是上面单独的一张卡（AddPhoto），这句不重复说它（2026-09-24 巡检 P1 → 接口 add_pet_photo 落地后加入口）。
 */
export const LOOK_INTRO_NO_PHOTO = "TA 在星球上的样子和证件照，都要照着 TA 的照片来画。";

export const ADD_PHOTO_PRIVACY = "照片只有家里人看得到。";
export const ADD_PHOTO_DONE = "照片放好了，只有家里人看得到。";

/**
 * 补一张照片的入口出不出现。依据是 /households 里这只宠物的事实（和 PetPrivateSummary 同一处来的 photo_url、origin），不猜：
 * - photo_url 为空才出现。没照片时服务端生成的那张形象照也放在同一个照片位上（PetPrivateSummary.photo_generated = true，
 *   photo_url 不为空），所以它在就不算“没有照片”——换掉它是“替换”，要等用户拍板；
 * - origin 必须是 own_pet：领养来的伙伴用的是 TA 在星球上的样子；
 * - 只在 live：演示模式不上传照片。
 */
export function canAddPhoto(photoUrl: string | null, origin: PetOrigin | null): boolean {
  return env.dataMode === "live" && origin === "own_pet" && !photoUrl;
}

/** 补照片失败说人话：服务端的三种原因各配一句，其余用统一的玩家说法（不露错误码）。 */
export function addPhotoFailureText(error: unknown): string {
  const err = toApiError(error);
  const reason = typeof err.details?.reason === "string" ? err.details.reason : null;
  if (reason === "photo_exists") return "TA 已经有照片了。";
  if (reason === "not_own_pet") return "领养来的伙伴用的是 TA 在星球上的样子。";
  if (err.code === "MEDIA_REJECTED") return "这张图用不了，换一张试试。";
  return err.playerMessage;
}

/** 这一页会不会出现“生成证件照”：和证件照那一节（home/PetFigure.tsx 的 IdPhotoAdjust）同一组条件——能力开着、服务端允许、还没有证件照或上次没画成。 */
function offersIdPhotoButton(state: CharacterState, idPhotoOn: boolean): boolean {
  const status = state.id_photo?.status ?? "absent";
  return idPhotoOn && state.can_regenerate === true && (status === "absent" || status === "failed");
}

type Look =
  | { phase: "demo" }
  | { phase: "checking" }
  | { phase: "off" }
  | { phase: "loading" }
  | { phase: "error"; error: unknown; retry: () => void }
  | { phase: "ready"; state: CharacterState; idPhotoOn: boolean };

export function LookPage() {
  return (
    <WorldGate>
      <LookBody />
    </WorldGate>
  );
}

function LookBody() {
  const current = useCurrentPet();
  return (
    <Page bare className="ps-look">
      <header className="ps-me-top">
        <Link className="ps-me-back" to="/me" aria-label="返回我的">
          <Icon name="back" size={20} />
        </Link>
        <h1>TA 的形象</h1>
      </header>
      {current.status === "pending" ? (
        <LoadingState lines={2} label="正在找到 TA…" />
      ) : current.status === "error" ? (
        <ErrorState error={current.error} onRetry={current.retry} />
      ) : current.pet ? (
        <LookForPet key={current.pet.petId} pet={current.pet} />
      ) : (
        <p className="ps-look-quiet" role="status">
          还没有住进来的伙伴。
        </p>
      )}
    </Page>
  );
}

/**
 * 形象读到哪一步了。数据只从 usePetCharacter 拿（它按能力表决定发不发请求）；能力表与小窝判断能力用的是同一个键、
 * 同一个请求（缓存共用，不多发）。另挂一个不自己发请求的旁观者（enabled: false）看同一条缓存，
 * 只为分清“还在读 / 读失败”——usePetCharacter 只交出数据，读失败时也是 null。
 */
function useLook(petId: string): Look {
  const { platform, pets } = useServices();
  const userId = useOptionalCurrentHousehold()?.userId ?? null;
  const live = env.dataMode === "live";
  const meta = useQuery({ queryKey: queryKeys.meta, queryFn: () => platform.meta(), staleTime: 60_000, enabled: live });
  const state = usePetCharacter(petId);
  const watch = useQuery({ queryKey: queryKeys.characterFor(userId ?? "-", petId), queryFn: ({ signal }) => pets.character(petId, signal), enabled: false, retry: false });
  if (!live) return { phase: "demo" };
  if (meta.isPending) return { phase: "checking" };
  if (meta.isError) return { phase: "error", error: meta.error, retry: () => void meta.refetch() };
  const capabilities = meta.data.capabilities;
  const on = (key: string) => capabilities.some((capability) => capability.key === key && capability.status === "available");
  if (!on("character.state")) return { phase: "off" };
  if (state) return { phase: "ready", state, idPhotoOn: on("character.id_photo") };
  if (watch.isError) return { phase: "error", error: watch.error, retry: () => void watch.refetch() };
  return { phase: "loading" };
}

function LookForPet({ pet }: { pet: CurrentPet }) {
  const look = useLook(pet.petId);
  // 来历只有家庭里的宠物简介有（CurrentPet 只搬名字和照片）；live 下当前宠物就是这一只
  const brief = useOptionalCurrentHousehold()?.pet ?? null;
  const origin = brief && brief.pet_id === pet.petId ? brief.origin : null;
  const [photoNote, setPhotoNote] = useState<string | null>(null);
  const asset = look.phase === "ready" ? sceneAsset(look.state) : null;
  const line = look.phase !== "ready" ? null : asset ? "星球上的 TA 就是下面这个样子" : (characterNote(look.state) ?? (pet.photoUrl ? "星球上暂时用 TA 的照片" : "还没有星球形象"));
  return (
    <>
      <section className="ps-me-hero ps-look-hero" aria-label="TA 现在的样子">
        <PetPortrait petId={pet.petId} name={pet.name} species={pet.species} photoUrl={pet.photoUrl} size={68} />
        <div className="ps-me-hero__text">
          <h2>{pet.name}</h2>
          {line ? <p>{line}</p> : null}
        </div>
      </section>

      {canAddPhoto(pet.photoUrl, origin) ? (
        <AddPhoto petId={pet.petId} name={pet.name} onSettled={setPhotoNote} />
      ) : photoNote ? (
        <p className="ps-look-photo-note" role="status">
          {photoNote}
        </p>
      ) : null}

      {look.phase === "checking" || look.phase === "loading" ? <LoadingState lines={1} label="正在看看 TA 现在的样子…" /> : null}
      {look.phase === "error" ? <ErrorState error={look.error} onRetry={look.retry} /> : null}
      {look.phase === "demo" ? (
        <LookNote title="演示模式没有 TA 的星球形象">住进来以后，TA 在星球上的样子和证件照都照着 TA 的照片来画，可以在这里调整。</LookNote>
      ) : null}
      {look.phase === "off" ? <LookNote title="TA 的星球形象暂时看不了">过一阵再来看看。</LookNote> : null}
      {look.phase === "ready" ? (
        <>
          {asset ? <LookFigure state={look.state} asset={asset} name={pet.name} /> : null}
          <section className="ps-look-card" aria-label="调整形象与证件照">
            <LookIntro state={look.state} idPhotoOn={look.idPhotoOn} />
            <AdjustCharacter petId={pet.petId} state={look.state} />
          </section>
        </>
      ) : null}
    </>
  );
}

/**
 * 补一张照片：选图 → 预览 → 确认才上传；上传中两个按钮都不能点（不连发）。换一张图就换一把幂等键；
 * 同一张图重试沿用原来那把（服务端按幂等键认出是同一次）。
 * 成功后刷新家庭（头像换成照片、入口消失）、会话、这只的形象（“画不了”随之消失，证件照按钮照现有规则出现）、家园与公开页缓存。
 * 上传后不生成证件照：要不要生成由主人在下面“生成证件照”自己点（这页原有的按钮，按能力与服务端状态出现）。
 */
function AddPhoto({ petId, name, onSettled }: { petId: string; name: string; onSettled: (note: string) => void }) {
  const { pets } = useServices();
  const queryClient = useQueryClient();
  const userId = useOptionalCurrentHousehold()?.userId ?? null;
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const keyRef = useRef(newIdempotencyKey("pet-photo"));
  useEffect(() => {
    if (!file) {
      setPreview(null);
      return undefined;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["households"] }),
      queryClient.invalidateQueries({ queryKey: queryKeys.session }),
      queryClient.invalidateQueries({ queryKey: queryKeys.characterFor(userId ?? "-", petId) }),
      queryClient.invalidateQueries({ queryKey: ["world", "home"] }),
      queryClient.invalidateQueries({ queryKey: ["public"] }),
    ]);
  const upload = useMutation({
    mutationFn: (photo: File) => pets.addPhoto(petId, photo, keyRef.current),
    onSuccess: async () => {
      onSettled(ADD_PHOTO_DONE);
      await refresh();
    },
    onError: async (error) => {
      // 已经有照片 / 其实是领养来的：这个入口本不该出现。说一句，再刷新，页面换成 TA 真实的样子（入口随之消失，这句留着）
      const reason = toApiError(error).details?.reason;
      if (reason === "photo_exists" || reason === "not_own_pet") {
        onSettled(addPhotoFailureText(error));
        await refresh();
      }
    },
  });
  return (
    <section className="ps-look-card ps-look-photo" aria-labelledby="look-photo-title" data-testid="add-photo">
      <h3 id="look-photo-title">补一张 TA 的照片</h3>
      <p className="ps-look-photo__lead">入住时没放照片也没关系，现在可以补一张。</p>
      {preview ? <img className="ps-look-photo__preview" src={preview} alt={`准备放上的${name}的照片`} /> : null}
      <div className="ps-look-photo__actions">
        <label className={`ps-btn ps-btn--secondary ps-look-photo__pick${upload.isPending ? " is-disabled" : ""}`}>
          {file ? "换一张" : "选一张照片"}
          <input
            type="file"
            accept="image/*"
            className="visually-hidden"
            disabled={upload.isPending}
            onChange={(event) => {
              const next = event.target.files?.[0] ?? null;
              event.target.value = "";
              if (!next) return;
              setFile(next);
              keyRef.current = newIdempotencyKey("pet-photo");
              upload.reset();
            }}
          />
        </label>
        {file ? (
          <Button variant="primary" loading={upload.isPending} disabled={upload.isPending} onClick={() => upload.mutate(file)}>
            放上这张照片
          </Button>
        ) : null}
      </div>
      <p className="ps-look-photo__privacy">{ADD_PHOTO_PRIVACY}</p>
      {upload.isError ? (
        <p className="ps-form-error" role="alert">
          {addPhotoFailureText(upload.error)}
        </p>
      ) : null}
    </section>
  );
}

/** 那一句说明；按钮名“生成证件照”连着引号不拆行（窄屏上不会断成“生成证 / 件照”）。页面上没有那个按钮时，一个字都不提它。 */
function LookIntro({ state, idPhotoOn }: { state: CharacterState; idPhotoOn: boolean }) {
  if (state.blocked_reason === "no_reference_photo") return <p className="ps-look-intro">{LOOK_INTRO_NO_PHOTO}</p>;
  if (!offersIdPhotoButton(state, idPhotoOn)) return <p className="ps-look-intro">{LOOK_INTRO}</p>;
  const quoted = "“生成证件照”";
  const [before, after] = LOOK_INTRO_WITH_ID_PHOTO.split(quoted);
  return (
    <p className="ps-look-intro">
      {before}
      <span className="ps-look-keep">{quoted}</span>
      {after}
    </p>
  );
}

/** 生效形象的站姿图：与小窝同一套落位（中性站姿的身体高度占满舞台，落地点对准底边中点）。 */
function LookFigure({ state, asset, name }: { state: CharacterState; asset: CharacterAsset; name: string }) {
  const round = (value: number) => Math.round(value * 100) / 100;
  const heightPct = round((asset.height / referenceBodyHeight(state, asset)) * 100);
  return (
    <figure className="ps-look-stage">
      <span className="ps-look-stage__body">
        <span className="ps-look-stage__shadow" aria-hidden="true" />
        <img
          src={asset.url}
          alt={`${name}的星球形象`}
          style={{ height: `${heightPct}%`, aspectRatio: `${asset.width} / ${asset.height}`, transform: `translate(${round(-asset.anchor.x * 100)}%, ${round((1 - asset.anchor.y) * 100)}%)` }}
        />
      </span>
      <figcaption>星球上的 TA</figcaption>
    </figure>
  );
}

function LookNote({ title, children }: { title: string; children: string }) {
  return (
    <div className="ps-look-card ps-look-note" role="note">
      <span className="ps-look-note__icon" aria-hidden="true">
        <Icon name="sparkle" size={22} />
      </span>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
