import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import type { PublicResident } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { routeAfterSession, useSessionState } from "@/shared/session/onboarding";
import { DataOriginBadge, ErrorState, Icon, LoadingState, Page } from "@/shared/ui";
import { ResidentPortrait } from "./ResidentPortrait";
import { WorldHero } from "./WorldHero";
import { ResidentHome } from "./ResidentHome";
import { agoText, extraPosts, nowLine, presenceGroup, presenceSummary, speciesName } from "./residentView";
import "./planet.css";

// 居民公开主页 2026-09-24 第二批整页重做，挪到 ResidentPage.tsx；从这里转出，路由（module.tsx）的引用不用改。
export { PublicPetPage } from "./ResidentPage";

/**
 * 一位居民：谁（照片或同物种插画、名字、物种、性格）、此刻在做什么、住在哪、梦想、最近一条公开小事。
 * “认识 TA”是卡片唯一的链接（整张卡都能点）；读屏先读到名字，链接名里也带着名字。
 */
function ResidentCard({ resident, nowMs }: { resident: PublicResident; nowMs: number }) {
  const post = resident.recent_posts[0] ?? null;
  const titleId = `world-resident-${resident.pet_id}`;
  return (
    <li>
      <article className="ps-world-resident" aria-labelledby={titleId} data-testid="resident-card">
        <div className="ps-world-resident__head">
          <ResidentPortrait name={resident.name} species={resident.species} photoUrl={resident.avatar_url} origin={resident.origin} size={64} />
          <div className="ps-world-resident__who">
            <div className="ps-world-resident__name">
              <h3 id={titleId}>{resident.name}</h3>
              <span className="ps-world-resident__species">{speciesName(resident.species)}</span>
            </div>
            <p>{resident.personality}</p>
          </div>
        </div>
        <dl className="ps-world-resident__facts">
          <div className={`ps-world-resident__now is-${presenceGroup(resident.presence)}`}>
            <dt>此刻</dt>
            <dd>{nowLine(resident)}</dd>
          </div>
          <div>
            <dt>住在</dt>
            <dd>
              <ResidentHome resident={resident} />
            </dd>
          </div>
          {resident.dream ? (
            <div>
              <dt>梦想</dt>
              <dd>{resident.dream}</dd>
            </div>
          ) : null}
        </dl>
        {post ? (
          <blockquote className="ps-world-resident__post">
            <p>{post.text}</p>
            <footer>{agoText(post.created_at, nowMs)}</footer>
          </blockquote>
        ) : null}
        <Link className="ps-world-resident__more" to={`/world/residents/${encodeURIComponent(resident.pet_id)}`} aria-label={`认识 TA：${resident.name}`}>
          认识 TA <Icon name="chevron" size={16} />
        </Link>
      </article>
    </li>
  );
}

/**
 * 访客星球（/world，不登录也能看）：一进来先看到居民——此刻在做什么、住在哪、梦想、最近的公开小事；
 * 主要动作是“认识 TA”（进居民主页）和“寻找我的 TA”（注册，登录后由你确认才领养），另有“已经有 TA 了？登录”。
 * 头图是装饰插画而不是地图：公开接口没有居民坐标，不画假位置（见 PlanetMap.tsx）。
 */
export function PublicWorldPage() {
  const { pets } = useServices();
  const session = useSessionState();
  const world = useQuery({ queryKey: queryKeys.publicWorld, queryFn: () => pets.publicWorld(), staleTime: 30_000 });
  const signedIn = env.dataMode === "live" && Boolean(session.data?.authenticated);
  const residents = world.data?.residents ?? [];
  const canRegister = world.data?.entries.some((entry) => entry.route === "own_pet") ?? false;
  const back = signedIn && session.data ? routeAfterSession(session.data) : "/welcome";
  const stillLooking = signedIn && session.data?.onboarding?.step === "needs_companion";
  const serverNow = world.data ? Date.parse(world.data.server_time) : Number.NaN;
  const nowMs = Number.isFinite(serverNow) ? serverNow : Date.now();
  const summary = presenceSummary(residents);
  const morePosts = world.data ? extraPosts(world.data.recent_posts, residents) : [];
  const title = world.isPending
    ? "星球正在亮起来…"
    : world.isError
      ? "暂时看不到星球上的居民"
      : residents.length
        ? `此刻有 ${world.data?.living_residents ?? residents.length} 位居民在星球上生活`
        : "今天暂时没有可认识的居民";
  return (
    <Page bare className="ps-world-page">
      <WorldHero back={back} species={residents.map((resident) => resident.species)} />
      <section className="ps-world-sheet" aria-labelledby="world-title">
        <div className="ps-world-sheet__head">
          <h1 id="world-title">{title}</h1>
          {residents.length ? <p>他们住在星球居民驿站，各自过着自己的一天，也在等一个家。</p> : null}
          {summary.length ? (
            <ul className="ps-world-now" aria-label="大家此刻在哪">
              {summary.map((item) => (
                <li key={item.group} className={`is-${item.group}`}>{item.text}</li>
              ))}
            </ul>
          ) : null}
        </div>
        {world.isPending ? (
          <LoadingState lines={3} label="正在看星球上的今天…" />
        ) : world.isError ? (
          <ErrorState error={world.error} onRetry={() => void world.refetch()} />
        ) : residents.length ? (
          <>
            {/* 读屏的标题层级：页面 h1 → 居民列表 h2（只给读屏）→ 每位居民 h3 */}
            <h2 className="visually-hidden" id="world-residents-title">星球上的居民</h2>
            <ul className="ps-world-residents" id="residents" aria-labelledby="world-residents-title">
              {residents.map((resident) => (
                <ResidentCard key={resident.pet_id} resident={resident} nowMs={nowMs} />
              ))}
            </ul>
          </>
        ) : (
          <p className="ps-world-empty">居民们回来后，会出现在这里。</p>
        )}
        {morePosts.length ? (
          <section className="ps-world-posts" aria-labelledby="world-posts-title">
            <h2 id="world-posts-title">星球上最近的小事</h2>
            <ul>
              {morePosts.map((post) => (
                <li key={post.post_id}>
                  <strong>{post.author.display_name}</strong>
                  <p>{post.text}</p>
                  <small>{agoText(post.created_at, nowMs)}</small>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        {/* 写给访客的话：已登录的人不显示 */}
        {world.data && !signedIn ? <p className="ps-world-sheet__note">注册不会自动领养，也不会自动加入别人的家；每一步都由你确认。</p> : null}
        {world.data ? <DataOriginBadge origin={world.data.data_origin} label="演示居民" /> : null}
      </section>
      <footer className="ps-world-cta">
        {signedIn ? (
          <Link className="ps-btn ps-btn--leaf ps-btn--block" to={back}>
            {stillLooking ? "继续寻找我的 TA" : "回到我的家"}
          </Link>
        ) : canRegister ? (
          <Link className="ps-btn ps-btn--leaf ps-btn--block" to="/register">
            寻找我的 TA
          </Link>
        ) : null}
        {!signedIn ? (
          <Link className="ps-world-cta__login" to="/login">
            已经有 TA 了？登录
          </Link>
        ) : null}
      </footer>
    </Page>
  );
}
