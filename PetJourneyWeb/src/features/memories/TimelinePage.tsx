/**
 * 生活片段（/timeline）：回忆 → 生活片段。全屏二级页，左上角回 /memories，不挂底栏
 * （方案 docs/product/PETSOUL-PLAYER-UI-MAP-FIRST-PLAN-2026-09-24.md 第 2.2、7.2、11 节）。
 * - 读 pets.timeline（GET /timeline?pet_id=…，纯读）：旅行、打工、证件、驾考、朋友、明信片……全部是已经发生的记录。
 * - 当前宠物走 useCurrentPet（它读的就是 useCurrentHousehold：live 用家庭上下文里已校验的宠物；fixture 用演示家园的样板宠物）。
 *   查询键带账号与宠物；切换宠物时换 key 重新读，旧宠物的结果不会落到新宠物名下。
 * - 按本地日期分组（今天 / 昨天 / 9 月 22 日），组内新的在前；每条照原文显示标题与小字，图标按 kind 选，
 *   认不出的 kind 用中性图标，kind 的原始代码不出现在页面上。能确定页面的（证件、攻略）才做成链接，其余只显示文字。
 * - 空：一句温和的话；出错：统一错误态，可重试；演示模式（服务报能力未接入）：说明演示里没有生活片段，不编数据。
 * - 头像一律是 TA 自己的样子（PetPortrait），不写名字首字。
 */
import type { CSSProperties } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { isApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { useServices } from "@/shared/services/registry";
import { ErrorState, Icon, LoadingState, Page } from "@/shared/ui";
import { PetPortrait } from "@/features/pets/PetPortrait";
import { WorldGate } from "@/features/world_map/WorldGate";
import { useCurrentPet, type CurrentPet } from "./currentPet";
import { clockText, groupTimeline, timelineDetail, timelineHref, timelineKey, timelineLook, type TimelineEntry, type TimelineGroup, type TimelineLook } from "./timeline";
import "./timeline.css";

export function TimelinePage() {
  return (
    <WorldGate>
      <TimelineBody />
    </WorldGate>
  );
}

function TimelineBody() {
  const current = useCurrentPet();
  const pet = current.status === "ready" ? current.pet : null;
  return (
    <Page bare className="ps-tl">
      <header className="ps-tl-top">
        <Link className="ps-tl-back" to="/memories" aria-label="返回回忆">
          <Icon name="back" size={20} />
        </Link>
        <div className="ps-tl-top__text">
          <h1>生活片段</h1>
          {pet ? <p>{pet.name}走过的日子，都按时间记着。</p> : null}
        </div>
        {pet ? <PetPortrait petId={pet.petId} name={pet.name} species={pet.species} photoUrl={pet.photoUrl} size={44} /> : null}
      </header>
      {current.status === "pending" ? (
        <LoadingState lines={3} label="正在找到 TA…" />
      ) : current.status === "error" ? (
        <ErrorState error={current.error} onRetry={current.retry} />
      ) : pet ? (
        <PetTimeline key={pet.petId} pet={pet} userId={current.userId} />
      ) : (
        <p className="ps-tl-quiet" role="status">
          还没有住进来的伙伴。
        </p>
      )}
    </Page>
  );
}

function PetTimeline({ pet, userId }: { pet: CurrentPet; userId: string | null }) {
  const services = useServices();
  const timeline = useQuery({
    queryKey: timelineKey(userId ?? "-", pet.petId),
    queryFn: ({ signal }) => services.pets.timeline(pet.petId, signal),
    enabled: env.dataMode !== "live" || Boolean(userId),
  });
  if (timeline.isPending) return <LoadingState lines={3} label="正在翻开生活片段…" />;
  if (timeline.isError) return <TimelineFailure error={timeline.error} onRetry={() => void timeline.refetch()} />;
  if (timeline.data.length === 0) return <TimelineEmpty name={pet.name} />;
  return <TimelineDays groups={groupTimeline(timeline.data, new Date())} />;
}

function TimelineDays({ groups }: { groups: TimelineGroup[] }) {
  return (
    <div className="ps-tl-days">
      {groups.map((group) => (
        <section className="ps-tl-day" key={group.key} aria-labelledby={`ps-tl-day-${group.key}`}>
          <h2 id={`ps-tl-day-${group.key}`}>{group.label}</h2>
          <ol className="ps-tl-list">
            {group.entries.map((entry) => (
              <TimelineRow key={entry.index} entry={entry} />
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}

function TimelineRow({ entry }: { entry: TimelineEntry }) {
  const { item, at } = entry;
  const look = timelineLook(item.kind);
  const href = timelineHref(item);
  const detail = timelineDetail(item);
  const body = (
    <>
      <KindMark look={look} />
      <span className="ps-tl-card">
        <span className="ps-tl-card__title">{item.title}</span>
        {at ? (
          <time className="ps-tl-card__time" dateTime={item.at}>
            {clockText(at)}
          </time>
        ) : null}
        {detail ? <span className="ps-tl-card__detail">{detail}</span> : null}
        {href ? <Icon name="chevron" size={16} className="ps-tl-card__go" /> : null}
      </span>
    </>
  );
  return (
    <li className="ps-tl-item">
      {href ? (
        <Link className="ps-tl-row is-link" to={href}>
          {body}
        </Link>
      ) : (
        <div className="ps-tl-row">{body}</div>
      )}
    </li>
  );
}

/** 小印章：色调与图标都来自前端自己的对照表（data-icon 是图标名，不是 kind）。 */
function KindMark({ look }: { look: TimelineLook }) {
  const { icon } = look;
  return (
    <span className="ps-tl-mark" data-tone={look.tone} data-icon={icon.name} aria-hidden="true">
      {icon.set === "ui" ? (
        <Icon name={icon.name} size={18} />
      ) : (
        <span className="ps-tl-mark__asset" style={{ "--ps-tl-icon": `url("/ui-assets/UI-ASSET-005/v1/icon-${icon.name}.svg")` } as CSSProperties} />
      )}
    </span>
  );
}

function TimelineEmpty({ name }: { name: string }) {
  return (
    <div className="ps-tl-note" role="status">
      <span className="ps-tl-note__icon" data-tone="leaf" aria-hidden="true">
        <Icon name="sprout" size={22} />
      </span>
      <h2>{name}的生活片段还空着</h2>
      <p>等{name}出门走走、打一份工、认识新朋友，这些已经发生的日子会一条条记在这里。</p>
    </div>
  );
}

/** 读不到：演示模式（能力未接入）温和说明、不编数据；其余走统一错误态，可重试。 */
function TimelineFailure({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  if (isApiError(error) && error.isCapabilityUnavailable) {
    const demo = env.dataMode === "fixture";
    return (
      <div className="ps-tl-note" role="note">
        <span className="ps-tl-note__icon" data-tone="sun" aria-hidden="true">
          <Icon name="bookmark" size={22} />
        </span>
        <h2>{demo ? "演示模式没有生活片段" : "生活片段暂时打不开"}</h2>
        <p>{demo ? "等你的伙伴住进来，TA 出门旅行、打工、拿到证件、认识新朋友……这些已经发生的事，会按日子收在这里。" : "过一会儿再来看看。"}</p>
      </div>
    );
  }
  return <ErrorState error={error} onRetry={onRetry} />;
}
