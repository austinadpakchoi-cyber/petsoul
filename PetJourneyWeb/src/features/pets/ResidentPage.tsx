import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import type { PublicPetView } from "@/shared/contracts";
import { toApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { routeAfterSession, useSessionState } from "@/shared/session/onboarding";
import { DataOriginBadge, ErrorState, Icon, LoadingState, Page } from "@/shared/ui";
import { AdoptFlow } from "./adoptFlow";
import { ResidentPortrait } from "./ResidentPortrait";
import { WorldHero } from "./WorldHero";
import { ResidentHome } from "./ResidentHome";
import { agoText, nowLine, presenceGroup, speciesName } from "./residentView";
import "./planet.css";

/**
 * 居民公开主页（/world/residents/:petId，不登录也能看）。和访客星球同一套样子：头图、叠上来的面板、贴底的行动区。
 * 只写后台给的公开事实：头像（公开照片，或同物种插画）、名字、物种、来自哪里（未知就不写）、此刻、住在哪、性格、梦想、最近的公开小事。
 * 领养：访客注册 / 登录时带上“想领养这一位”，登录后仍由本人确认；已登录、TA 可以领养时用共用的“迎接 TA”（adoptFlow.tsx：
 * 没家新建、一个家直接迎进、几个家先选、不是管理员说清楚；点了先确认，确认后才领养）。已登录的出口始终有“回到我的家”和“再看看其他居民”。
 */
function ResidentProfile({ view }: { view: PublicPetView }) {
  const { profile, resident, posts } = view;
  const name = profile.display_name;
  const source = resident?.source_note?.trim() || profile.origin_label?.trim() || null;
  const personality = resident?.personality?.trim() || null;
  const bio = profile.bio?.trim() && profile.bio.trim() !== personality ? profile.bio.trim() : null;
  const nowMs = Date.now();
  return (
    <>
      <div className="ps-resident-page__head">
        {/* 来历只有居民数据里有（公开主页的 profile 不带 origin）：不是居民时按照片读 */}
        <ResidentPortrait name={name} species={profile.species} photoUrl={profile.avatar_url ?? resident?.avatar_url ?? null} origin={resident?.origin ?? null} size={116} />
        <div className="ps-world-resident__name ps-resident-page__name">
          <h1 id="resident-title">{name}</h1>
          <span className="ps-world-resident__species">{speciesName(profile.species)}</span>
        </div>
        {source ? <p className="ps-resident-page__source">来自：{source}</p> : null}
      </div>
      {resident ? (
        <section className={`ps-resident-page__now is-${presenceGroup(resident.presence)}`} aria-labelledby="resident-now">
          <h2 id="resident-now">此刻</h2>
          <p className="ps-resident-page__doing">{nowLine(resident)}</p>
          <p className="ps-resident-page__home">
            住在<ResidentHome resident={resident} />
          </p>
        </section>
      ) : null}
      {personality || bio ? (
        <section className="ps-resident-page__section" aria-labelledby="resident-trait">
          <h2 id="resident-trait">{personality ? "TA 的性格" : "关于 TA"}</h2>
          {personality ? <p className="ps-resident-page__trait">{personality}</p> : null}
          {bio ? <p>{bio}</p> : null}
        </section>
      ) : null}
      {resident?.dream ? (
        <section className="ps-resident-page__section" aria-labelledby="resident-dream">
          <h2 id="resident-dream">TA 的梦想</h2>
          <p className="ps-resident-page__dream">{resident.dream}</p>
        </section>
      ) : null}
      <section className="ps-resident-page__section" aria-labelledby="resident-posts">
        <h2 id="resident-posts">TA 最近的小事</h2>
        {posts.length ? (
          <ul className="ps-resident-page__posts">
            {posts.map((post) => (
              <li key={post.post_id}>
                <p>{post.text}</p>
                <small>{agoText(post.created_at, nowMs)}</small>
              </li>
            ))}
          </ul>
        ) : (
          <p className="ps-resident-page__quiet">TA 还没有公开的小事。</p>
        )}
      </section>
    </>
  );
}

/**
 * 领养说明：放在面板里（不挤贴底的行动区）。只给访客说“注册后由你确认才领养”；已登录的人不看写给访客的话，
 * 迎接的说明由共用的“迎接 TA”自己给（按钮、确认框、不是管理员时的一句话），这里不再重复，也不写“仍在接入中”这类过时的说法。
 */
function AdoptNote({ adoptable, signedIn }: { adoptable: boolean; signedIn: boolean }) {
  if (!adoptable) return <p className="ps-resident-page__note">TA 暂时不能被领养。</p>;
  if (!signedIn) return <p className="ps-resident-page__note">注册后由你确认才领养，不会自动领养；刚才选中的伙伴会被记住。</p>;
  return null;
}

export function PublicPetPage() {
  const { petId } = useParams();
  const { pets } = useServices();
  const session = useSessionState();
  const pet = useQuery({ queryKey: queryKeys.publicPet(petId ?? "-"), queryFn: () => pets.publicPet(petId!), enabled: Boolean(petId), staleTime: 30_000 });
  const data = pet.data;
  const signedIn = env.dataMode === "live" && Boolean(session.data?.authenticated);
  const needsCompanion = signedIn && session.data?.onboarding?.step === "needs_companion";
  const home = signedIn && session.data ? routeAfterSession(session.data) : "/welcome";
  const notFound = !petId || (pet.isError && toApiError(pet.error).status === 404);
  const name = data?.profile.display_name ?? "";
  const entry = petId ? `entry=adopt&pet_id=${encodeURIComponent(petId)}` : "";
  const canWelcome = Boolean(data?.adoptable && data.resident);
  return (
    <Page bare className="ps-world-page ps-resident-page">
      <WorldHero back="/world" species={[]} historyBack />
      <section className="ps-world-sheet ps-resident-page__sheet" aria-labelledby="resident-title">
        {notFound ? (
          <div className="ps-resident-page__missing">
            <h1 id="resident-title">没有找到这位居民的公开主页</h1>
            <p>TA 可能已经有了自己的家，或者主页没有公开。</p>
          </div>
        ) : pet.isPending ? (
          <>
            <h1 id="resident-title" className="visually-hidden">正在打开居民主页</h1>
            <LoadingState lines={3} label="正在打开居民主页…" />
          </>
        ) : pet.isError ? (
          <>
            <h1 id="resident-title" className="ps-resident-page__error-title">暂时打不开这位居民的主页</h1>
            <ErrorState error={pet.error} onRetry={() => void pet.refetch()} />
          </>
        ) : data ? (
          <>
            <ResidentProfile view={data} />
            <AdoptNote adoptable={data.adoptable} signedIn={signedIn} />
            <DataOriginBadge origin={data.profile.data_origin} label="演示居民" />
          </>
        ) : null}
        <Link className="ps-resident-page__more" to="/world">
          再看看其他居民 <Icon name="chevron" size={16} />
        </Link>
      </section>
      {data || notFound ? (
        <footer className="ps-world-cta">
          {signedIn ? (
            <>
              {/* 已登录、TA 可以领养：共用的“迎接 TA”，本人已经入住的也用它迎进自己的家 */}
              {canWelcome && data?.resident ? <AdoptFlow candidateId={data.resident.candidate_id} petId={petId} name={name} adoptable={data.adoptable} block /> : null}
              <Link className={canWelcome ? "ps-world-cta__home" : "ps-btn ps-btn--leaf ps-btn--block"} to={home}>
                {needsCompanion ? "继续寻找我的 TA" : "回到我的家"}
              </Link>
            </>
          ) : data?.adoptable ? (
            <>
              <Link className="ps-btn ps-btn--leaf ps-btn--block" to={`/register?${entry}`}>
                领养 {name}
              </Link>
              <Link className="ps-world-cta__login" to={`/login?${entry}`}>
                已经有账号？登录后继续
              </Link>
            </>
          ) : (
            <>
              <Link className="ps-btn ps-btn--leaf ps-btn--block" to="/register">
                寻找我的 TA
              </Link>
              <Link className="ps-world-cta__login" to="/login">
                已经有 TA 了？登录
              </Link>
            </>
          )}
        </footer>
      ) : null}
    </Page>
  );
}
