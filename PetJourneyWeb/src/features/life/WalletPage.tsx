/**
 * 证件卡包（回忆 → 证件卡包，二级页，全屏不挂底栏）：卡包封面 + “证件 | 打工记录”（/life?tab=jobs 直达打工记录）。
 * 已获得的证件画成小卡面叠在一起，点开看单张；还没有的放最后，只是虚线空卡位——写怎样获得，不画卡面、不写号码。
 * 驾照还没有时，空卡位里给“陪 TA 去驾校”（方案 8.1）；驾照在办（学车中）时，空卡位里写四科进度，整块点进驾校（方案 8.2）。
 */
import { useRef, type KeyboardEvent } from "react";
import { Link, useSearchParams } from "react-router";
import type { UseQueryResult } from "@tanstack/react-query";
import type { CredentialSummary, JobRecord } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { PetPortrait } from "@/features/pets/PetPortrait";
import { DataOriginBadge, EmptyState, ErrorState, Icon, LoadingState, Page, TopBar } from "@/shared/ui";
import { useSchoolStatus } from "@/features/driving_school/hooks";
import { jobStatus, jobWhen, payText, schoolEntry, schoolProgress, splitWallet, statusText, type SchoolProgress } from "./copy";
import { useCredentialList, useJobList, useWalletPet, type WalletPet } from "./data";
import { MiniCard } from "./faces";
import { KindMark } from "./glyphs";
import { coverAvatarIsAi, coverAvatarUrl } from "./parts";
import "./life.css";

type Tab = "cards" | "jobs";
const TABS: Array<[Tab, string]> = [
  ["cards", "证件"],
  ["jobs", "打工记录"],
];

export function WalletPage() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "jobs" ? "jobs" : "cards";
  const pet = useWalletPet();
  const credentials = useCredentialList();
  const jobs = useJobList();
  const select = (next: Tab) => {
    const nextParams = new URLSearchParams(params);
    if (next === "jobs") nextParams.set("tab", "jobs");
    else nextParams.delete("tab");
    setParams(nextParams, { replace: true });
  };
  const bank = credentials.data?.find((item) => item.kind === "bank_card" && item.credential_id) ?? null;
  return (
    <Page bare className="ps-wallet-page">
      <TopBar title="证件卡包" back="/memories" right={env.dataMode === "fixture" ? <DataOriginBadge origin="fixture" /> : undefined} />
      <div className="ps-wallet">
        {pet.ready ? <WalletCover pet={pet} list={credentials.data} /> : <div className="ps-wallet-cover ps-skeleton" aria-hidden="true" />}
        <WalletTabs tab={tab} onSelect={select} />
        <section className="ps-wallet-panel" role="tabpanel" id={`wallet-panel-${tab}`} aria-labelledby={`wallet-tab-${tab}`}>
          {tab === "cards" ? <CardsPanel query={credentials} pet={pet} /> : <JobsPanel query={jobs} bankId={bank?.credential_id ?? null} />}
        </section>
      </div>
    </Page>
  );
}

/**
 * 卡包封面：UI-ASSET-005 v1 的 wallet-cover（深绿皮夹、爪印扣，合上的样子，透明底）。
 * TA 的头像与名字压在翻盖上半条——实测扣带在翻盖中下部偏右（x 52–61%、y 53–68%），翻盖上半条（y 18–42%）是空的。
 */
function WalletCover({ pet, list }: { pet: WalletPet; list: CredentialSummary[] | undefined }) {
  const obtained = list ? splitWallet(list).obtained : [];
  // 圆头像：有证件照裁出的 256×256 头像就用它，没有照旧 PetPortrait(photo_url)；“AI 生成”规则与证件照相同（见 parts.tsx）
  const avatar = coverAvatarUrl(pet);
  const ai = coverAvatarIsAi(pet);
  return (
    <header className="ps-wallet-cover" data-testid="wallet-cover">
      <div className="ps-wallet-cover__art">
        <div className="ps-wallet-cover__overlay">
          <span className="ps-wallet-cover__portrait" data-testid="cover-avatar" data-source={avatar ? "id-photo-avatar" : "photo"}>
            <PetPortrait name={pet.name} photoUrl={avatar ?? pet.photoUrl} size={48} />
            {ai ? <span className="ps-wallet-cover__ai">AI 生成</span> : null}
          </span>
          <div className="ps-wallet-cover__text">
            <span className="ps-wallet-cover__kicker">PetSoul 星球证件</span>
            <h1 className="ps-wallet-cover__name">{pet.name}</h1>
            <p className="ps-wallet-cover__count">{list ? (obtained.length ? `${obtained.length} 张证件` : "卡包还空着") : " "}</p>
          </div>
        </div>
      </div>
    </header>
  );
}

function WalletTabs({ tab, onSelect }: { tab: Tab; onSelect: (tab: Tab) => void }) {
  const refs = useRef<Partial<Record<Tab, HTMLButtonElement | null>>>({});
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const next: Tab = tab === "cards" ? "jobs" : "cards";
    onSelect(next);
    refs.current[next]?.focus();
  };
  return (
    <div className="ps-wallet-tabs" role="tablist" aria-label="卡包里的内容" onKeyDown={onKeyDown}>
      {TABS.map(([id, label]) => (
        <button
          key={id}
          ref={(element) => {
            refs.current[id] = element;
          }}
          type="button"
          role="tab"
          id={`wallet-tab-${id}`}
          aria-selected={tab === id}
          aria-controls={`wallet-panel-${id}`}
          tabIndex={tab === id ? 0 : -1}
          onClick={() => onSelect(id)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function CardsPanel({ query, pet }: { query: UseQueryResult<CredentialSummary[]>; pet: WalletPet }) {
  if (query.isPending) return <LoadingState label="正在打开卡包…" lines={3} />;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const { obtained, missing } = splitWallet(query.data);
  if (!obtained.length && !missing.length) {
    return (
      <EmptyState icon="bookmark" title="卡包还空着">
        TA 的证件会在入住和出行时签发，签发后放在这里。
      </EmptyState>
    );
  }
  return (
    <div className="ps-wallet-cards">
      {obtained.length ? (
        <ol className="ps-wallet-stack" aria-label="已有的证件">
          {obtained.map((item) => (
            <li key={item.credential_id}>
              <Link className="ps-wallet-stack__link" to={`/credentials/${encodeURIComponent(item.credential_id)}`}>
                <MiniCard summary={item} pet={pet} />
              </Link>
            </li>
          ))}
        </ol>
      ) : (
        <p className="ps-wallet-note">还没有签发下来的证件。</p>
      )}
      {missing.length ? (
        <section className="ps-wallet-missing" aria-labelledby="wallet-missing-title">
          <h2 id="wallet-missing-title">还没有的证件</h2>
          <ul>
            {missing.map((item, index) => (
              <MissingSlot key={`${item.kind}-${index}`} summary={item} />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function MissingSlot({ summary }: { summary: CredentialSummary }) {
  if (summary.kind === "driver_license" && summary.status === "in_progress") return <LearningLicenseSlot summary={summary} />;
  return <SlotView summary={summary} progress={null} />;
}

/**
 * 驾照“办理中”（想学、已报名、在考、待领证）：读驾校状态，能说清楚就把进度写进空卡位（方案 8.2）。
 * 直接复用驾校模块的 useSchoolStatus（只读引用）：查询键、查询函数、启用条件都和驾校、地图面板一致，共用一份缓存。
 * 只有这张空卡位出现时才读，不加轮询（后端 GET /driving 会顺带补签、作废超时考局）。读不到、出错、字段不够时照原来的样子。
 */
function LearningLicenseSlot({ summary }: { summary: CredentialSummary }) {
  const school = useSchoolStatus();
  const progress = school.data ? schoolProgress(school.data) : null;
  return <SlotView summary={summary} progress={progress} />;
}

function SlotView({ summary, progress }: { summary: CredentialSummary; progress: SchoolProgress | null }) {
  const entry = schoolEntry(summary);
  const status = statusText(summary);
  const inner = (
    <>
      <span className="ps-wallet-slot__frame" aria-hidden="true">
        <KindMark summary={summary} size={16} />
      </span>
      <div className="ps-wallet-slot__text">
        <p className="ps-wallet-slot__head">
          <strong>{summary.label}</strong>
          {status ? <span>{status}</span> : null}
        </p>
        <p className="ps-wallet-slot__how">{summary.condition}</p>
        {progress ? (
          <SchoolProgressView progress={progress} />
        ) : entry ? (
          <Link className="ps-btn ps-btn--secondary ps-btn--sm ps-wallet-slot__go" to={entry.to}>
            {entry.text}
          </Link>
        ) : null}
      </div>
    </>
  );
  if (progress) {
    // 有学车进度时整块都是驾校入口（里面不再放单独的按钮，免得链接套链接）
    return (
      <li className={`ps-wallet-slot ps-wallet-slot--school ps-cred--${summary.kind}`} data-testid="wallet-slot" data-kind={summary.kind}>
        <Link className="ps-wallet-slot__link" to="/school" data-testid="school-progress">
          {inner}
        </Link>
      </li>
    );
  }
  return (
    <li className={`ps-wallet-slot ps-cred--${summary.kind}`} data-testid="wallet-slot" data-kind={summary.kind}>
      {inner}
    </li>
  );
}

function SchoolProgressView({ progress }: { progress: SchoolProgress }) {
  return (
    <div className="ps-school-progress">
      {progress.kind === "subjects" ? (
        <ul className="ps-school-progress__tags" aria-label="四科进度">
          {progress.subjects.map((tag) => (
            <li key={tag.subject} className={`ps-school-tag is-${tag.tone}`} data-testid="school-subject">
              <b>{tag.name}</b>
              <span className="visually-hidden">：</span>
              <span>{tag.text}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="ps-school-progress__line" data-testid="school-line">
          {progress.kind === "pending" ? "四科都过了，驾照正在签发" : progress.wishText ? `TA 说想学开车：“${progress.wishText}”` : "TA 说想学开车"}
        </p>
      )}
      <span className="ps-school-progress__go">{progress.kind === "wish" ? "陪 TA 去驾校" : "去驾校看看"}</span>
    </div>
  );
}

function JobsPanel({ query, bankId }: { query: UseQueryResult<JobRecord[]>; bankId: string | null }) {
  if (query.isPending) return <LoadingState label="正在翻打工记录…" lines={2} />;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  if (!query.data.length) {
    return (
      <EmptyState icon="bookmark" title="还没有打工记录">
        哪天 TA 自己去上班了，会记在这里。
      </EmptyState>
    );
  }
  return (
    <div className="ps-wallet-jobs">
      <p className="ps-wallet-note">
        工钱在收工后进 TA 的星球银行卡。
        {bankId ? <Link to={`/credentials/${encodeURIComponent(bankId)}`}>看银行卡</Link> : null}
      </p>
      <ol className="ps-jobs">
        {query.data.map((job) => (
          <JobRow key={`${job.journey_id}-${job.job_key}`} job={job} />
        ))}
      </ol>
    </div>
  );
}

function JobRow({ job }: { job: JobRecord }) {
  const status = jobStatus(job.status);
  return (
    <li className={`ps-job ps-job--${status.tone}`} data-testid="job-row" data-paid={job.paid ? "true" : "false"}>
      <div className="ps-job__top">
        <span className="ps-job__status" data-testid="job-status">
          {status.text}
        </span>
        <time dateTime={job.starts_at}>{jobWhen(job)}</time>
      </div>
      <strong className="ps-job__title">{job.title}</strong>
      <span className="ps-job__place">
        <Icon name="pin" size={14} />
        {job.place ?? "地点没有记下"}
      </span>
      <div className="ps-job__pay">
        <span>
          <b>{job.pay}</b> 星币
        </span>
        <em data-testid="job-pay">{payText(job)}</em>
      </div>
    </li>
  );
}
