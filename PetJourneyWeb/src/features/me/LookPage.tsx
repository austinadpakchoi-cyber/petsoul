/**
 * 我的 · TA 的形象（/me/look）：从“我的”进来的全屏页，左上角回 /me，不挂底栏（方案第 9 节“TA 的形象（调整形象）”），
 * 写法照 /me/dna、/me/reports（WorldGate 守）。
 * - 复用小窝的 usePetCharacter（纯读形象）与 AdjustCharacter（“调整形象”，里面已带证件照一节 IdPhotoAdjust），
 *   只读引用 home/PetFigure.tsx，不改它。按钮出不出现全由它们按能力表与服务端的 can_regenerate、证件照状态决定，这里不另加按钮。
 * - 顶部是 TA 现在的样子：头像一律 PetPortrait（有照片用照片，演示用演示小灰猫，live 没照片是爪印，不写名字首字）；
 *   已有生效的星球形象时，下面再放那张站姿图（只放 sceneAsset 认可、验过透明的那张，按中性站姿的身体高度落位）。
 * - 一句说明：形象和证件照都照着 TA 的照片画；早些住进来、还没有证件照的伙伴，在这里点“生成证件照”补一张最方便
 *   （能力表里证件照没开时，这句不提按钮）。
 * - 读的状态分清：能力表说形象没开 → 说暂时看不了，不发形象请求；还在读 → 等一等；读失败 → 统一错误态可重试，
 *   不当成“没有形象”。演示模式没有真实形象：温和说明，不编数据、不放按钮。
 */
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import type { CharacterAsset, CharacterState } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useOptionalCurrentHousehold } from "@/shared/session/householdContext";
import { ErrorState, Icon, LoadingState, Page } from "@/shared/ui";
import { AdjustCharacter, characterNote, referenceBodyHeight, sceneAsset, usePetCharacter } from "@/features/home/PetFigure";
import { PetPortrait } from "@/features/pets/PetPortrait";
import { WorldGate } from "@/features/world_map/WorldGate";
import { useCurrentPet, type CurrentPet } from "@/features/memories/currentPet";
import "./me.css";
import "./look.css";

/** 页面上那一句说明：证件照能力开着时，顺带告诉老伙伴在哪儿补第一张证件照。 */
export const LOOK_INTRO_WITH_ID_PHOTO = "TA 在星球上的样子和证件照，都照着 TA 的照片来画；早些住进来、还没有证件照的伙伴，在这里点“生成证件照”补一张最方便。";
export const LOOK_INTRO = "TA 在星球上的样子照着 TA 的照片来画；画好以后觉得不像，可以在这里调整。";

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
            <LookIntro withIdPhoto={look.idPhotoOn} />
            <AdjustCharacter petId={pet.petId} state={look.state} />
          </section>
        </>
      ) : null}
    </>
  );
}

/** 那一句说明；按钮名“生成证件照”连着引号不拆行（窄屏上不会断成“生成证 / 件照”）。 */
function LookIntro({ withIdPhoto }: { withIdPhoto: boolean }) {
  if (!withIdPhoto) return <p className="ps-look-intro">{LOOK_INTRO}</p>;
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
