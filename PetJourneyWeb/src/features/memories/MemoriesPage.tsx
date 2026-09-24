/**
 * 回忆（/memories）：新版三栏（地图 · 通讯器 · 回忆）的第三栏。全屏页，自带 WorldGate，底部挂新版三栏预览
 * （方案 docs/product/PETSOUL-PLAYER-UI-MAP-FIRST-PLAN-2026-09-24.md 第 2、7.2、19 节）。
 * - 只放现在就有后端能力的入口：生活片段、证件卡包、打工记录、明信片与小收藏、相册、旅程与攻略手账；不放“即将开放”之类的占位。
 *   生活片段（/timeline）排最前、横跨两列（方案 7.2 把它列在回忆的第一条）；它的入口不带一句话，不为这句话多发一次请求。
 * - 入口上的一句话只来自对应服务的结果；请求失败（包括演示模式没有这项数据）时只隐藏这句话，入口照常，不写错误文字。
 * - 查询键与各目的页共用（queryKeys），进到二级页时不必重取。
 * - 标题旁的头像一律是 TA 自己的样子（PetPortrait），不写名字首字。
 */
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import type { JobRecord } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { ErrorState, Icon, LoadingState, Page, type IconName } from "@/shared/ui";
import { credentialListKey } from "@/features/life/data";
import { PetPortrait } from "@/features/pets/PetPortrait";
import { PreviewTabBar } from "@/features/world_map/PreviewTabBar";
import { WorldGate } from "@/features/world_map/WorldGate";
import { useCurrentPet, type CurrentPet } from "./currentPet";
import { heldCredentialCount, jobStatusText, latestJob, photoCounts } from "./facts";
import "./memories.css";

type Tone = "leaf" | "sun" | "coral" | "sky";
/** 入口上的事实：粗体一句（数字用衬线体），需要时再加一行小字。 */
type Fact = { main: ReactNode; detail?: string };

export function MemoriesPage() {
  return (
    <WorldGate>
      <MemoriesBody />
    </WorldGate>
  );
}

function MemoriesBody() {
  const current = useCurrentPet();
  const pet = current.status === "ready" ? current.pet : null;
  return (
    <>
      <Page className="ps-mem">
        <header className="ps-mem-head">
          <div className="ps-mem-head__text">
            <h1>回忆</h1>
            {current.status === "ready" ? <p>{pet?.name ?? "TA "}的日子，都攒在这里。</p> : null}
          </div>
          {pet ? <PetPortrait petId={pet.petId} name={pet.name} species={pet.species} photoUrl={pet.photoUrl} size={52} /> : null}
        </header>
        {current.status === "pending" ? (
          <LoadingState lines={3} label="正在翻开回忆…" />
        ) : current.status === "error" ? (
          <ErrorState error={current.error} onRetry={current.retry} />
        ) : (
          <MemoryEntries pet={pet} userId={current.userId} />
        )}
      </Page>
      <div className="ps-mem-dock">
        <PreviewTabBar />
      </div>
    </>
  );
}

function MemoryEntries({ pet, userId }: { pet: CurrentPet | null; userId: string | null }) {
  const facts = useMemoryFacts(pet?.petId ?? null, userId);
  return (
    <nav className="ps-mem-grid" aria-label="回忆里的入口">
      <EntryCard wide to="/timeline" icon="sparkle" tone="coral" title="生活片段" desc="TA 走过的日子，都按时间记着" fact={null} />
      <EntryCard
        wide
        to="/life"
        icon="user"
        tone="leaf"
        title="证件卡包"
        desc="星球发给 TA 的证件"
        fact={facts.credentials}
        aside={facts.heldCredentials ? <Wallet count={facts.heldCredentials} /> : null}
      />
      <EntryCard to="/life?tab=jobs" icon="coin" tone="sun" title="打工记录" desc="TA 出门打过的工" fact={facts.jobs} />
      <EntryCard to="/collection" icon="gift" tone="coral" title="明信片与小收藏" desc="旅途上带回来的" fact={facts.collection} />
      <EntryCard to="/photos" icon="camera" tone="sky" title="相册" desc="给 TA 拍的照片" fact={facts.photos} />
      <EntryCard to="/guides" icon="journey" tone="leaf" title="旅程与攻略手账" desc="TA 出门前写的小攻略" fact={facts.guides} />
    </nav>
  );
}

/** 五个入口各自的一句话。没有结果（还在读、读失败、演示模式没有这项数据）时为 null：页面只隐藏这句话。 */
function useMemoryFacts(petId: string | null, userId: string | null) {
  const services = useServices();
  const live = env.dataMode === "live";
  const owner = userId ?? "-";
  const pet = petId ?? "-";
  const enabled = Boolean(petId) && (!live || Boolean(userId));
  // 与证件卡包同一个键（挂在 queryKeys.credentials 前缀下）：驾校领证时失效的正是这个前缀，“已持有 N 张”跟着刷新，也不重复请求。
  const credentials = useQuery({ queryKey: credentialListKey(owner, pet), queryFn: ({ signal }) => services.life.credentials(pet, signal), enabled });
  const jobs = useQuery({ queryKey: queryKeys.jobsFor(owner, pet), queryFn: ({ signal }) => services.life.jobs(pet, signal), enabled });
  const collection = useQuery({
    // 与收藏页同一个键：fixture 用演示收藏的公共键，live 按账号与宠物分开。
    queryKey: live ? queryKeys.collectionFor(owner, pet) : queryKeys.collection,
    queryFn: ({ signal }) => services.economy.collection(petId, signal),
    enabled,
  });
  const photos = useQuery({ queryKey: queryKeys.photoRequestsFor(owner, pet), queryFn: ({ signal }) => services.pets.photoRequests(pet, signal), enabled });
  const guides = useQuery({ queryKey: queryKeys.guidesFor(owner, pet), queryFn: ({ signal }) => services.transport.guides(petId, signal), enabled });

  const held = credentials.data ? heldCredentialCount(credentials.data) : null;
  const shots = photos.data ? photoCounts(photos.data) : null;
  const count = (n: number, unit: string, none: string): Fact => ({ main: n > 0 ? <><b>{n}</b> {unit}</> : none });
  return {
    heldCredentials: held,
    credentials: held === null ? null : held > 0 ? { main: <>已持有 <b>{held}</b> 张</> } : { main: "还没有拿到证件" },
    jobs: jobs.data ? jobFact(jobs.data) : null,
    collection: collection.data ? count(collection.data.length, "件", "还空着") : null,
    photos: shots
      ? shots.ready > 0
        ? { main: <><b>{shots.ready}</b> 张</>, detail: shots.drawing > 0 ? `还有 ${shots.drawing} 张在画` : undefined }
        : shots.drawing > 0
          ? { main: <><b>{shots.drawing}</b> 张还在画</> }
          : { main: "还没有照片" }
      : null,
    guides: guides.data ? count(guides.data.length, "份", "还没有手账") : null,
  };
}

/** 最近一条打工：状态在前（去上班的路上 / 在干活 / 干完了），岗位名作小字；不认识的状态不猜，只说“最近一份工”。 */
function jobFact(list: JobRecord[]): Fact {
  const latest = latestJob(list);
  if (!latest) return { main: "还没有打工记录" };
  return { main: jobStatusText(latest.status) ?? "最近一份工", detail: latest.title };
}

function EntryCard({ to, icon, tone, title, desc, fact, wide = false, aside = null }: {
  to: string;
  icon: IconName;
  tone: Tone;
  title: string;
  desc: string;
  fact: Fact | null;
  wide?: boolean;
  aside?: ReactNode;
}) {
  return (
    <Link to={to} className={`ps-mem-card${wide ? " ps-mem-card--wide" : ""}`} data-tone={tone}>
      <span className="ps-mem-stamp" aria-hidden="true">
        <Icon name={icon} size={22} />
      </span>
      <span className="ps-mem-card__body">
        <span className="ps-mem-card__title">{title}</span>
        <span className="ps-mem-card__desc">{desc}</span>
        {fact ? (
          <span className="ps-mem-card__fact">
            <span className="ps-mem-card__main">{fact.main}</span>
            {fact.detail ? <span className="ps-mem-card__detail">{fact.detail}</span> : null}
          </span>
        ) : null}
      </span>
      {aside}
      <Icon name="chevron" size={16} className="ps-mem-card__go" />
    </Link>
  );
}

/** 卡包的小插图：叠几张空白卡片，张数跟着已持有的数量（最多叠三张）；只是装饰，不画卡面信息。 */
function Wallet({ count }: { count: number }) {
  const cards = Math.min(count, 3);
  return (
    <span className="ps-mem-wallet" aria-hidden="true" data-cards={cards}>
      {Array.from({ length: cards }, (_, index) => (
        <i key={index} />
      ))}
    </span>
  );
}
