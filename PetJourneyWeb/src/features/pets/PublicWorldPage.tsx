import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import type { PublicResident } from "@/shared/contracts";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useSessionState } from "@/shared/session/onboarding";
import { DataOriginBadge, ErrorState, LoadingState, Page, TopBar } from "@/shared/ui";
import publicWorldScene from "./assets/public-world-v1.webp";
import homeKey from "./assets/entry-home-key-v1.webp";
import residentBook from "./assets/entry-resident-book-v1.webp";
import invitationLetter from "./assets/entry-invitation-letter-v1.webp";
import "./pets.css";

const SPECIES_NAMES: Record<string, string> = { cat: "猫", dog: "狗", rabbit: "兔子", hamster: "仓鼠", bird: "鸟", parrot: "鹦鹉", other: "动物" };

function ResidentCard({ resident, index }: { resident: PublicResident; index: number }) {
  return (
    <Link className="ps-public-resident" to={`/world/residents/${encodeURIComponent(resident.pet_id)}`}>
      <span className="ps-public-resident__portrait" aria-label={`${resident.name}暂无公开照片`}>
        <span>{resident.name.slice(0, 1)}</span>
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

export function PublicWorldPage() {
  const { pets } = useServices();
  const world = useQuery({ queryKey: queryKeys.publicWorld, queryFn: () => pets.publicWorld(), staleTime: 30_000 });
  return (
    <Page bare className="ps-entry-page ps-public-page">
      <TopBar title="星球漫游" subtitle="不用登录，也能先看看" back="/welcome" />
      <section className="ps-public-hero" aria-label="PetSoul 平行世界">
        <img src={publicWorldScene} alt="" />
        <div className="ps-public-hero__copy">
          <span>PetSoul · A LIVING WORLD</span>
          <h1>走进来，<br />看看他们的今天。</h1>
          <p>这里的家和旅途，都有自己的时间。</p>
        </div>
      </section>
      {world.isPending ? <LoadingState lines={3} label="正在看星球上的今天…" /> : world.isError ? <ErrorState error={world.error} onRetry={() => void world.refetch()} /> : (
        <div className="ps-public-content">
          <div className="ps-public-intro">
            <span className="ps-public-kicker">01 / 先认识这里</span>
            <h2>今天有 {world.data.living_residents} 位居民在生活</h2>
            <p>他们还住在星球居民驿站。点开一位，看看 TA 此刻在哪、想着什么。</p>
            <DataOriginBadge origin={world.data.data_origin} label={world.data.data_origin === "fixture" ? "内部演示居民与场景" : "居民资料与活动来自当前公开接口；背景为虚构场景"} />
          </div>
          {world.data.residents.length ? (
            <div className="ps-public-residents" id="residents">
              {world.data.residents.map((resident, index) => <ResidentCard key={resident.pet_id} resident={resident} index={index} />)}
            </div>
          ) : <p className="ps-public-empty">今天暂时没有可认识的居民，过一会儿再来看看。</p>}
          {world.data.recent_posts.length ? (
            <section className="ps-public-posts">
              <span className="ps-public-kicker">02 / 星球来信</span>
              <h2>最近发生的小事</h2>
              {world.data.recent_posts.map((post) => <article key={post.post_id}><strong>{post.author.display_name}</strong><p>{post.text}</p></article>)}
            </section>
          ) : null}
          <section className="ps-public-invite">
            <span className="ps-public-kicker">03 / 留下来的方式</span>
            <h2>从喜欢的方式开始</h2>
            <div className="ps-public-entry-options">
              {world.data.entries.some((entry) => entry.route === "own_pet") ? <Link className="ps-public-entry-option" to="/register?entry=own_pet">
                <img src={homeKey} alt="" />
                <span><strong>带我的宠物来</strong><small>先建立属于 TA 的家</small></span><span aria-hidden="true">↗</span>
              </Link> : null}
              {world.data.entries.some((entry) => entry.route === "adopt" || entry.route === "browse") ? <Link className="ps-public-entry-option" to="#residents">
                <img src={residentBook} alt="" />
                <span><strong>认识星球居民</strong><small>先看看，再决定是否迎接</small></span><span aria-hidden="true">↗</span>
              </Link> : null}
              {world.data.entries.some((entry) => entry.route === "invite") ? <div className="ps-public-entry-option ps-public-entry-option--quiet">
                <img src={invitationLetter} alt="" />
                <span><strong>从家人邀请进入</strong><small>请打开收到的专属链接</small></span>
              </div> : null}
            </div>
            <p>注册不会自动领养或加入家庭；邀请仍需在登录后确认。</p>
          </section>
        </div>
      )}
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
            {data.profile.avatar_url ? <img src={data.profile.avatar_url} alt={data.profile.display_name} /> : <div><strong>{data.profile.display_name.slice(0, 1)}</strong><span>暂无公开照片</span></div>}
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
