import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import type { PublicResident } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { PawMark, petPortraitUrl } from "./PetPortrait";
import { routeAfterSession, useSessionState } from "@/shared/session/onboarding";
import { DataOriginBadge, ErrorState, Icon, LoadingState, Page, Sheet, TopBar } from "@/shared/ui";
import { BrandLogo } from "@/shared/ui/BrandLogo";
import { EncounterCard, PlanetMap } from "./PlanetMap";
import "./pets.css";
import "./planet.css";

const SPECIES_NAMES: Record<string, string> = { cat: "猫", dog: "狗", rabbit: "兔子", hamster: "仓鼠", bird: "鸟", parrot: "鹦鹉", other: "动物" };

function ResidentCard({ resident, index }: { resident: PublicResident; index: number }) {
  return (
    <Link className="ps-public-resident" to={`/world/residents/${encodeURIComponent(resident.pet_id)}`}>
      {/* 居民还没有公开照片字段：演示模式用授权小灰猫，live 用爪印占位；不写名字首字。 */}
      <span className="ps-public-resident__portrait" aria-label={`${resident.name}暂无公开照片`}>
        <span>{petPortraitUrl(null) ? <img src={petPortraitUrl(null)!} alt="" /> : <PawMark size={22} />}</span>
        <small>暂无公开照片</small>
      </span>
      <span className="ps-public-resident__body">
        <small className="ps-public-resident__number">居民 / {String(index + 1).padStart(2, "0")} · {SPECIES_NAMES[resident.species] ?? "动物"}</small>
        <strong>{resident.name}</strong>
        <span>{resident.personality}</span>
        <em>{resident.doing} · {resident.city}</em>
      </span>
      <span className="ps-public-resident__arrow" aria-hidden="true">↗</span>
    </Link>
  );
}

/**
 * 星球（访客“先去星球上逛逛”）：几乎全屏的地图，居民在各自生活；每隔一会儿有一位冒出此刻的状态。
 * 点中只弹一张轻量相遇卡，不直接进领养页。列表作为地图之外的无障碍入口放在“看全部居民”。
 * 访客没有底图权限（/map/basemap 需要登录），显示示意图；登录后才尝试真实底图。
 */
export function PublicWorldPage() {
  const { pets } = useServices();
  const session = useSessionState();
  const world = useQuery({ queryKey: queryKeys.publicWorld, queryFn: () => pets.publicWorld(), staleTime: 30_000 });
  const [encounter, setEncounter] = useState<PublicResident | null>(null);
  const [listOpen, setListOpen] = useState(false);
  const signedIn = env.dataMode === "live" && Boolean(session.data?.authenticated);
  const residents = world.data?.residents ?? [];
  const canRegister = world.data?.entries.some((entry) => entry.route === "own_pet") ?? false;
  const back = signedIn && session.data ? routeAfterSession(session.data) : "/welcome";
  return (
    <Page bare className="ps-planet-page">
      <div className="ps-planet-map" data-testid="planet-map">
        {world.isPending ? (
          <div className="ps-planet-map__state"><LoadingState lines={2} label="正在看星球上的今天…" /></div>
        ) : world.isError ? (
          <div className="ps-planet-map__state"><ErrorState error={world.error} onRetry={() => void world.refetch()} /></div>
        ) : (
          <PlanetMap residents={residents} onEncounter={setEncounter} paused={Boolean(encounter) || listOpen} realBasemap={signedIn} />
        )}
        <header className="ps-planet-top">
          <Link to={back} className="ps-planet-top__back" aria-label="返回"><Icon name="back" size={20} /></Link>
          <div className="ps-planet-top__title">
            <BrandLogo size="compact" />
            <span>{world.data ? (residents.length ? `今天有 ${world.data.living_residents} 位居民在星球上生活` : "今天暂时没有可认识的居民") : "星球正在亮起来…"}</span>
          </div>
        </header>
      </div>
      <section className="ps-planet-dock" aria-label="在星球上">
        <p className="ps-planet-dock__note">{residents.length ? "点一位居民，和 TA 打个照面。居民画在所住驿站一带，不是实时定位。" : "居民回来后，会出现在地图上。"}</p>
        <div className="ps-planet-dock__actions">
          <button type="button" className="ps-btn ps-btn--secondary" disabled={!residents.length} onClick={() => setListOpen(true)}>
            看全部居民{residents.length ? ` · ${residents.length}` : ""}
          </button>
          {signedIn ? (
            <Link className="ps-btn ps-btn--primary" to={back}>回到我的家</Link>
          ) : canRegister ? (
            <Link className="ps-btn ps-btn--primary" to="/register">寻找我的 TA</Link>
          ) : null}
        </div>
        {!signedIn ? <Link className="ps-planet-dock__login" to="/login">已经找到 TA 了？登录</Link> : null}
        {world.data ? <DataOriginBadge origin={world.data.data_origin} label="内部演示居民与场景" /> : null}
      </section>
      {encounter ? <EncounterCard resident={encounter} onClose={() => setEncounter(null)} /> : null}
      {listOpen && world.data ? (
        <Sheet title="星球上的居民" subtitle="此刻在做什么，来自公开状态" onClose={() => setListOpen(false)} className="ps-planet-list">
          <div className="ps-public-residents" id="residents">
            {residents.map((resident, index) => <ResidentCard key={resident.pet_id} resident={resident} index={index} />)}
          </div>
          {world.data.recent_posts.length ? (
            <section className="ps-public-posts">
              <span className="ps-public-kicker">星球来信</span>
              <h2>最近发生的小事</h2>
              {world.data.recent_posts.map((post) => <article key={post.post_id}><strong>{post.author.display_name}</strong><p>{post.text}</p></article>)}
            </section>
          ) : null}
          <p className="ps-planet-list__note">注册不会自动领养或加入家庭；邀请仍需在登录后确认。</p>
        </Sheet>
      ) : null}
    </Page>
  );
}

export function PublicPetPage() {
  const { petId } = useParams();
  const { pets } = useServices();
  const session = useSessionState();
  const pet = useQuery({ queryKey: queryKeys.publicPet(petId ?? "-"), queryFn: () => pets.publicPet(petId!), enabled: Boolean(petId), staleTime: 30_000 });
  if (!petId) return <Page bare><p>没有找到这位居民。</p></Page>;
  const data = pet.data;
  const canContinue = session.data?.authenticated && session.data.onboarding?.step === "needs_companion";
  const entryQuery = `entry=adopt&pet_id=${encodeURIComponent(petId)}`;
  return (
    <Page bare className="ps-entry-page ps-public-page">
      <TopBar title="认识居民" back="/world" />
      {pet.isPending ? <LoadingState lines={3} label="正在打开居民手账…" /> : pet.isError ? <ErrorState error={pet.error} onRetry={() => void pet.refetch()} /> : data ? (
        <div className="ps-public-profile">
          <div className="ps-public-profile__image">
            {petPortraitUrl(data.profile.avatar_url) ? <img src={petPortraitUrl(data.profile.avatar_url)!} alt={data.profile.display_name} /> : <div><PawMark size={40} /><span>暂无公开照片</span></div>}
          </div>
          <span className="ps-public-kicker">星球居民 / {SPECIES_NAMES[data.profile.species] ?? "动物"}</span>
          <h1>{data.profile.display_name}</h1>
          {data.resident ? <p className="ps-public-profile__living">{data.resident.doing} · {data.resident.residence}</p> : null}
          {data.profile.bio ? <p className="ps-public-profile__bio">{data.profile.bio}</p> : null}
          {data.resident ? <div className="ps-public-profile__dream"><span>TA 的小愿望</span><strong>{data.resident.dream}</strong></div> : null}
          {data.resident?.source_note ? <p className="ps-public-profile__source">来源：{data.resident.source_note}</p> : null}
          {data.posts.length ? <section className="ps-public-posts"><h2>TA 最近的小事</h2>{data.posts.map((post) => <article key={post.post_id}><p>{post.text}</p></article>)}</section> : <p className="ps-public-profile__quiet">TA 还没有公开的生活手账，不能替 TA 编造一段旅程。</p>}
          {data.adoptable ? (
            <div className="ps-public-profile__actions">
              {canContinue ? <Link className="ps-btn ps-btn--primary ps-btn--block" to={`/onboarding/choice?pet_id=${encodeURIComponent(petId)}`}>继续认识 {data.profile.display_name}</Link> : !session.data?.authenticated ? <>
                <Link className="ps-btn ps-btn--primary ps-btn--block" to={`/register?${entryQuery}`}>注册后，确认迎接 TA</Link>
                <Link className="ps-public-profile__login" to={`/login?${entryQuery}`}>已经有账号？登录后继续</Link>
              </> : <p className="ps-public-profile__quiet">为已有家庭迎接新伙伴的入口仍在接入中；这里不会自动领养 TA。</p>}
              <p>选择会被记住；是否领养，登录后仍由你确认。</p>
            </div>
          ) : <p className="ps-public-profile__quiet">TA 暂时不能被领养。你仍可以继续看看星球。</p>}
          <Link className="ps-public-profile__back" to="/world">← 再看看其他居民</Link>
        </div>
      ) : null}
    </Page>
  );
}
