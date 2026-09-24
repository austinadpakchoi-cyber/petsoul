/**
 * 旅行心愿的两个页面，与攻略手账列表里的“想去 / 准备中”（TRV-06，claude-6c2b 分身）。
 * - /guides/wish：当前活动心愿（GET /travel/wish，合同 §23.4，已可接 live）；资料还在查、还没有计划的心愿只能从这里进。
 * - /guides/plan/:planId：某一份计划（GET /travel/plans/{plan_id}，还没落地）：现在只有演示计划；live 只说“还在搭建中”，不造假。
 * - 页面只认 PlanView（./model）；数据从 ./data 来。标题有宠物名字就用名字，拿不到才写“TA”。
 * - 文字负责好用，手账图负责好看：地名、时间、金额、来源全是页面文字；手账图只占一块留白，没有 / 在画 / 没画成 / 结果未确认 / 没有配图时文字照常；
 *   手账这一页上写的字（标题、一句话、站点、提醒、雨天备选）在图外照常可读（TRV-07：屏幕先显示图外文字）；
 *   只有没画成、结果未确认且后端给了重画票时才说“稍后可以重画”——重画命令的路由还没建，这里只是一句说明、不是按钮，不假装能点；
 *   配图被拒的拒绝码、“不画 TA”的原因码只进“技术信息”（平时收起）。
 * - 外链一律新窗口、rel="noopener noreferrer"，只收 http(s)（./model 的 safeHref）：资料来源，和后端给的地图链接 nav_url（不拿 lat/lng 自己拼）。
 */
import { useId, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import { toApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { useOptionalCurrentHousehold } from "@/shared/session/householdContext";
import { Chip, DataOriginBadge, DisabledState, EmptyState, ErrorState, Icon, LoadingState, Page, TopBar } from "@/shared/ui";
import { isPetRequired, isPlanNotFound, useCurrentWish, useDemoPlans, type Read } from "./data";
import { viewOfPlan, viewOfWish, type JournalTextView, type LineView, type PlaceStamp, type PlaceView, type PlanView, type ViewOptions } from "./model";
import "./plan.css";

/** 当前宠物的名字；拿不到（演示世界的家庭上下文没有当前宠物）就是 null，页面写“TA”。 */
export function usePetName(): string | null {
  return useOptionalCurrentHousehold()?.pet?.name ?? null;
}

function useViewOptions(): ViewOptions {
  return { petName: usePetName(), isDemo: env.dataMode === "fixture" };
}

/**
 * 攻略手账列表的“想去 / 准备中”。null＝没有可显示的（还在加载、取不到、live 下没有活动心愿），列表不显示这一块。
 * live 现在只有当前活动心愿（GET /travel/wish）；演示另有几份计划。
 */
export function useShelfViews(): PlanView[] | null {
  const wish = useCurrentWish();
  const plans = useDemoPlans();
  const options = useViewOptions();
  if (wish.state === "loading" || plans.state === "loading") return null;
  const current = wish.state === "ready" && wish.data ? wish.data : null;
  // 当前心愿若已有计划，列表里只放当前心愿那一张（进 /guides/wish），不重复放它的计划。
  const others = plans.state === "ready" ? plans.data.filter((bundle) => bundle.wish.wish_id !== current?.wish_id).map((bundle) => viewOfPlan(bundle, options)) : [];
  const views = [...(current ? [viewOfWish(current, options)] : []), ...others];
  return views.length ? views : null;
}

function PendingTag({ children = "待确认" }: { children?: ReactNode }) {
  return <span className="ps-plan-tag ps-plan-tag--pending">{children}</span>;
}

function Line({ line }: { line: LineView }) {
  return (
    <>
      <span>{line.text}</span>
      {line.pending ? <PendingTag /> : null}
    </>
  );
}

function Stamp({ stamp }: { stamp: PlaceStamp | null }) {
  return stamp ? <span className={`ps-plan-stamp ps-plan-stamp--${stamp.kind}`}>{stamp.label}</span> : null;
}

function PlaceItem({ place }: { place: PlaceView }) {
  return (
    <div className={`ps-plan-place ps-plan-place--${place.role}`} data-place-id={place.id}>
      <div className="ps-plan-place__head">
        <strong>{place.name}</strong>
        {place.role === "suggested" ? <span className="ps-plan-tag">顺路建议</span> : null}
        <Stamp stamp={place.stamp} />
      </div>
      {place.why ? <p>{place.why}</p> : null}
      {place.tip || place.pending ? (
        <p className="ps-plan-place__tip">
          {place.tip ? <span>{place.tip}</span> : null}
          {place.pending ? <PendingTag>资料待确认</PendingTag> : null}
        </p>
      ) : null}
      <div className="ps-plan-place__foot">
        <small>{place.verifyText}</small>
        {/* 后端给的 nav_url（高德、WGS-84、只有核实过的地点才有），新窗口打开；没有就不给，前端不拿坐标自己拼。 */}
        {place.mapUrl ? (
          <a href={place.mapUrl} target="_blank" rel="noopener noreferrer">
            在地图上看 ↗
          </a>
        ) : null}
      </div>
    </div>
  );
}

/**
 * 重画入口：后端给了重画票（只有没画成 / 结果未确认才有）才出现。重画命令的路由还没建，
 * 所以这里只是一句说明，不是按钮——不假装能点。路由建好后换成按钮，由主人自己点（不自动重画）。
 */
function RedrawNote() {
  return (
    <p className="ps-plan-journal__redraw">
      <Icon name="refresh" size={14} />
      <span>稍后可以在这里重画这张手账。</span>
    </p>
  );
}

/** 手账这一页上写的字（图外可读）：标题、一句话、站点（回忆页带章）、提醒、雨天备选。 */
function JournalPage({ text }: { text: JournalTextView }) {
  const id = useId();
  return (
    <div className="ps-plan-journal__page" role="group" aria-labelledby={id}>
      <p className="ps-plan-journal__kicker" id={id}>
        手账上写着
      </p>
      {text.title ? <h3>{text.title}</h3> : null}
      {text.summary ? <p>{text.summary}</p> : null}
      {text.stations.length ? (
        <ol className="ps-plan-journal__stations">
          {text.stations.map((station) => (
            <li key={station.key}>
              <span>{station.name}</span>
              {station.role === "suggested" ? <span className="ps-plan-tag">顺路建议</span> : null}
              <Stamp stamp={station.stamp} />
            </li>
          ))}
        </ol>
      ) : null}
      {text.tips.length ? (
        <ul className="ps-plan-lines">
          {text.tips.map((line, index) => (
            <li key={`${index}-${line.text}`}>
              <Line line={line} />
            </li>
          ))}
        </ul>
      ) : null}
      {text.rain ? <p>雨天备选：{text.rain}</p> : null}
    </div>
  );
}

/** 计划正文（两个页面与测试共用）：先文字、后手账图，来源放最后。 */
export function PlanContent({ view }: { view: PlanView }) {
  const id = useId();
  const h = (name: string) => `${id}-${name}`;
  return (
    <article className="ps-plan" data-stage={view.stage}>
      <header className="ps-plan-hero">
        <div className="ps-plan-hero__tags">
          <Chip tone={view.status.tone}>{view.status.label}</Chip>
          {view.isDemo ? <DataOriginBadge origin="fixture" label="演示计划" /> : null}
        </div>
        <p className="ps-plan-hero__dest">
          <Icon name="pin" size={18} />
          <span>{view.destination}</span>
        </p>
        {view.planTitle ? <p className="ps-plan-hero__plan">{view.planTitle}</p> : null}
        <p className="ps-plan-hero__summary">{view.summary}</p>
      </header>

      <section className="ps-plan-section" aria-labelledby={h("why")}>
        <h2 id={h("why")}>我为什么想去</h2>
        {view.reason ? (
          <blockquote className="ps-plan-quote">
            <p>“{view.reason}”</p>
            <footer>TA 自己说的</footer>
          </blockquote>
        ) : (
          <p className="ps-plan-muted">TA 这次没有写原因。</p>
        )}
      </section>

      {view.stage === "wish" || view.stage === "ready" ? (
        <section className="ps-plan-section" aria-labelledby={h("waiting")}>
          <h2 id={h("waiting")}>还差什么</h2>
          {view.waiting.length ? (
            <ul className="ps-plan-waiting">
              {view.waiting.map((item) => (
                <li key={item.key}>
                  <span className="ps-plan-waiting__icon" aria-hidden="true">
                    <Icon name={item.icon} size={16} />
                  </span>
                  <span>
                    <strong>{item.text}</strong>
                    {item.detail ? <small>{item.detail}</small> : null}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="ps-plan-muted">{view.stage === "ready" ? "都准备好了。出不出发、哪天走，由 TA 自己决定。" : "还在准备。"}</p>
          )}
        </section>
      ) : null}

      {view.preconditions.length ? (
        <section className="ps-plan-section" aria-labelledby={h("pre")}>
          <h2 id={h("pre")}>出发前会再确认</h2>
          <p className="ps-plan-note">出发那一刻，TA 会再确认这几条资料还有效；过期了就先不出发，重新查一遍。</p>
          <ul className="ps-plan-lines ps-plan-pre">
            {view.preconditions.map((item) => (
              <li key={item.key}>
                <span>
                  {item.topic}
                  {item.detail ? `：${item.detail}` : ""}
                </span>
                {item.pendingText ? <PendingTag>{item.pendingText}</PendingTag> : item.until ? <small>{item.until}</small> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="ps-plan-section" aria-labelledby={h("steps")}>
        <h2 id={h("steps")}>行动安排</h2>
        {view.validity ? <p className="ps-plan-note">按这一天的资料安排：{view.validity}</p> : null}
        {view.arrangement ? (
          <p className="ps-plan-arrangement">{view.arrangement}</p>
        ) : view.planLink ? (
          <p className="ps-plan-muted">
            计划已经写好了。<Link to={view.planLink}>看这份计划</Link>
          </p>
        ) : (
          <p className="ps-plan-muted">{view.planWritten ? "这份计划没有写行动安排。" : "TA 查好资料以后，路线和提醒会写在这里。"}</p>
        )}
      </section>

      <section className="ps-plan-section" aria-labelledby={h("main")}>
        <h2 id={h("main")}>主目的地</h2>
        <PlaceItem place={view.main} />
      </section>

      <section className="ps-plan-section" aria-labelledby={h("along")}>
        <h2 id={h("along")}>顺路建议</h2>
        <p className="ps-plan-note">顺路看看的地方，只是建议，不算到访。</p>
        {view.suggestions.length ? (
          <ul className="ps-plan-places">
            {view.suggestions.map((place) => (
              <li key={place.id}>
                <PlaceItem place={place} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="ps-plan-muted">{view.planWritten ? "这份计划没有顺路建议。" : "TA 查好资料以后，再看有没有顺路的地方。"}</p>
        )}
      </section>

      {view.reminders.length ? (
        <section className="ps-plan-section" aria-labelledby={h("tips")}>
          <h2 id={h("tips")}>提醒</h2>
          <ul className="ps-plan-lines">
            {view.reminders.map((line, index) => (
              <li key={`${index}-${line.text}`}>
                <Line line={line} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {view.rainPlan ? (
        <section className="ps-plan-section" aria-labelledby={h("rain")}>
          <h2 id={h("rain")}>雨天备选</h2>
          <p className="ps-plan-rain">{view.rainPlan}</p>
        </section>
      ) : null}

      {view.coins || view.realCosts.length ? (
        <section className="ps-plan-section" aria-labelledby={h("money")}>
          <h2 id={h("money")}>花费</h2>
          <div className="ps-plan-money">
            {view.coins ? (
              <div className="ps-plan-money__item ps-plan-money__item--coins" data-money="coins">
                <span className="ps-plan-money__kind">
                  <Icon name="coin" size={14} />
                  游戏里的星币
                </span>
                <strong>{view.coins.text}</strong>
                {view.coins.detail ? <small>{view.coins.detail}</small> : null}
              </div>
            ) : null}
            {view.realCosts.length ? (
              <div className="ps-plan-money__item ps-plan-money__item--real" data-money="real">
                <span className="ps-plan-money__kind">
                  <Icon name="info" size={14} />
                  现实参考 · 给你看
                </span>
                <ul className="ps-plan-money__list">
                  {view.realCosts.map((cost) => (
                    <li key={cost.key} data-cost={cost.key}>
                      <strong>{cost.text}</strong>
                      <small>{cost.meta}</small>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
          {view.realCosts.length ? <p className="ps-plan-note">现实参考只给你看，不会换算成星币；TA 在星球上只花星币。</p> : null}
        </section>
      ) : null}

      <section className="ps-plan-section" aria-labelledby={h("journal")}>
        <h2 id={h("journal")}>{view.journal.heading}</h2>
        <figure className={`ps-plan-journal ps-plan-journal--${view.journal.state}`} data-journal={view.journal.state}>
          {view.journal.imageUrl ? (
            <img src={view.journal.imageUrl} alt={`${view.journal.heading}的画面`} loading="lazy" />
          ) : (
            <div className="ps-plan-journal__blank" aria-hidden="true">
              <Icon name="bookmark" size={26} />
            </div>
          )}
          <figcaption>
            <strong>{view.journal.caption}</strong>
            {view.journal.staleNote ? <span className="ps-plan-journal__stale">{view.journal.staleNote}</span> : null}
            {view.journal.identity ? <span className="ps-plan-journal__identity">{view.journal.identity}</span> : null}
            {view.journal.state === "ready" ? null : <span>文字都在这一页，照常可以看。</span>}
            {view.journal.tech ? <TechLine text={view.journal.tech} /> : null}
          </figcaption>
        </figure>
        {view.journal.canRedraw ? <RedrawNote /> : null}
        {view.journal.text ? <JournalPage text={view.journal.text} /> : null}
      </section>

      <section className="ps-plan-section" aria-labelledby={h("sources")}>
        <h2 id={h("sources")}>资料来源</h2>
        {view.sources.length ? (
          <ul className="ps-plan-sources">
            {view.sources.map((source) => (
              <li key={source.id} data-pending={source.pendingText ? "true" : "false"}>
                <div className="ps-plan-sources__head">
                  <span>{source.topic}</span>
                  {source.pendingText ? <PendingTag>{source.pendingText}</PendingTag> : <span className="ps-plan-tag ps-plan-tag--ok">已核对</span>}
                </div>
                {source.detail ? <p className="ps-plan-sources__value">{source.detail}</p> : null}
                {source.refs.map((ref) => (
                  <div key={ref.key} className="ps-plan-sources__ref">
                    <p>
                      来源：
                      {ref.href ? (
                        <a href={ref.href} target="_blank" rel="noopener noreferrer">
                          {ref.publisher}
                        </a>
                      ) : (
                        ref.publisher
                      )}
                    </p>
                    {ref.times.map((time) => (
                      <small key={time}>{time}</small>
                    ))}
                  </div>
                ))}
                {source.times.map((time) => (
                  <small key={time}>{time}</small>
                ))}
              </li>
            ))}
          </ul>
        ) : (
          <p className="ps-plan-muted">{view.planWritten ? "这份计划没有列出资料来源。" : "还没有资料来源：TA 正在准备。"}</p>
        )}
      </section>
    </article>
  );
}

/**
 * 读的几种状态：读不了（默认说还在搭建中，不造假；whenUnavailable 可以换成专门的说法）、加载中、
 * 出错（可重试；whenError 可以把某些错误换成专门的说法）、读到了。
 */
function ReadGate<T>({
  read,
  found,
  empty,
  whenUnavailable,
  whenError,
  onRetry,
  children,
}: {
  read: Read<T>;
  found: boolean;
  empty: ReactNode;
  whenUnavailable?: ReactNode;
  whenError?: (error: unknown) => ReactNode | null;
  onRetry?: () => void;
  children: ReactNode;
}) {
  if (read.state === "unavailable") {
    if (whenUnavailable) return <>{whenUnavailable}</>;
    return (
      <DisabledState title="这里还在搭建中">
        <p className="ps-plan-muted">TA 的旅行计划接上以后，会在这里出现。</p>
      </DisabledState>
    );
  }
  if (read.state === "loading") return <LoadingState lines={3} label="正在翻开 TA 的计划…" />;
  if (read.state === "error") return <>{whenError?.(read.error) ?? <ErrorState error={read.error} onRetry={onRetry} />}</>;
  return <>{found ? children : empty}</>;
}

/** “技术信息”那一行：错误码 · 原因码 · request_id（平时收起，反馈问题时展开）。 */
function techLine(error: unknown): string {
  const e = toApiError(error);
  const reason = typeof e.details?.reason === "string" ? e.details.reason : null;
  return [e.code, reason, e.requestId ? `request_id ${e.requestId}` : null].filter(Boolean).join(" · ");
}

/** 默认收起的“技术信息”（样式沿用共享的 ps-state__tech）。 */
function TechLine({ text }: { text: string }) {
  return (
    <details className="ps-state__tech">
      <summary>技术信息</summary>
      <div className="ps-state__meta">{text}</div>
    </details>
  );
}

/**
 * 这份计划不在了：演示里没有这份计划；或者（第③期接上 GET /travel/plans/{plan_id} 以后）后端答 404 plan_not_found——
 * 找不到、或不属于这只宠物（I 已定）。原因码只收进“技术信息”，玩家只看人话。
 */
export function PlanMissing({ error }: { error?: unknown }) {
  const tech = error === undefined ? "" : techLine(error);
  return (
    <EmptyState icon="bookmark" title="这份计划不在了">
      它可能已经换了一版，或者不是这只宠物的计划。回到手账列表看看。
      {tech ? <TechLine text={tech} /> : null}
    </EmptyState>
  );
}

/**
 * 定不了是哪只宠物：后端答 409 pet_required（§29.5），或者 live 下这一页拿不到当前宠物（不拿 null 让后端去推）。
 * 说要先选一只，不白屏、不一直转；有原因码时只进“技术信息”。
 */
export function PetRequired({ error }: { error?: unknown }) {
  return (
    <EmptyState icon="user" title="需要先选一只宠物">
      先选好要看的是哪一只，再回来看 TA 想去哪里。
      {error === undefined ? null : <TechLine text={techLine(error)} />}
    </EmptyState>
  );
}

/** /guides/wish：当前活动心愿（GET /travel/wish）。 */
export function WishPage() {
  const wish = useCurrentWish();
  const options = useViewOptions();
  const view = wish.state === "ready" && wish.data ? viewOfWish(wish.data, options) : null;
  return (
    <Page className="ps-plan-page">
      <TopBar title={<h1 className="ps-plan-title">{view?.title ?? "旅行心愿"}</h1>} back="/guides" />
      <ReadGate
        read={wish}
        found={Boolean(view)}
        empty={
          <EmptyState icon="bookmark" title={`${options.petName ?? "TA"} 现在没有惦记的地方`}>
            有了想去的地方，会在这里写下为什么想去、还差什么。
          </EmptyState>
        }
        whenUnavailable={<PetRequired />}
        whenError={(error) => (isPetRequired(error) ? <PetRequired error={error} /> : null)}
      >
        {view ? <PlanContent view={view} /> : null}
      </ReadGate>
    </Page>
  );
}

/** /guides/plan/:planId：某一份计划（GET /travel/plans/{plan_id} 还没落地：只有演示计划）。 */
export function PlanPage() {
  const { planId } = useParams();
  const plans = useDemoPlans();
  const options = useViewOptions();
  const bundle = plans.state === "ready" ? (plans.data.find((candidate) => candidate.plan.plan_id === planId) ?? null) : null;
  const view = bundle ? viewOfPlan(bundle, options) : null;
  return (
    <Page className="ps-plan-page">
      <TopBar title={<h1 className="ps-plan-title">{view?.title ?? "旅行计划"}</h1>} back="/guides" />
      <ReadGate
        read={plans}
        found={Boolean(view)}
        empty={<PlanMissing />}
        whenError={(error) => (isPlanNotFound(error) ? <PlanMissing error={error} /> : null)}
      >
        {view ? <PlanContent view={view} /> : null}
      </ReadGate>
    </Page>
  );
}

function PlanCard({ view }: { view: PlanView }) {
  return (
    <Link to={view.href} className="ps-plan-card" data-plan-id={view.key}>
      <span className="ps-plan-card__top">
        <Chip tone={view.status.tone}>{view.status.label}</Chip>
        {view.isDemo ? <DataOriginBadge origin="fixture" label="演示" /> : null}
      </span>
      <strong className="ps-plan-card__title">{view.title}</strong>
      <span className="ps-plan-card__line">{view.cardLine}</span>
      <span className="ps-plan-card__open">
        看计划 <Icon name="chevron" size={15} />
      </span>
    </Link>
  );
}

/**
 * 攻略手账列表里的“想去 / 准备中”。只列想去和可以出发的；出发之后、放下的放在下面“后来怎样”，不和“想去”混在一起
 * （主窗口定：先留着，真实情况等接口定）。演示时把几种状态放在一起，所以明写“真实情况下 TA 同一时间只惦记一个地方”。
 */
export function PlanShelf({ views }: { views: PlanView[] }) {
  const id = useId();
  const wishing = views.filter((view) => view.stage === "wish" || view.stage === "ready");
  const after = views.filter((view) => view.stage !== "wish" && view.stage !== "ready");
  const demo = views.some((view) => view.isDemo);
  return (
    <section className="ps-plan-shelf" aria-labelledby={`${id}-wishing`} data-shelf="wishing">
      <div className="ps-plan-shelf__head">
        <h2 id={`${id}-wishing`}>想去 / 准备中</h2>
        {demo ? <DataOriginBadge origin="fixture" label="演示" /> : null}
      </div>
      {demo ? <p className="ps-plan-shelf__note">演示：几种状态放在一起给你看；真实情况下，TA 同一时间只惦记一个地方。</p> : null}
      {wishing.length ? (
        <ul className="ps-plan-cards">
          {wishing.map((view) => (
            <li key={view.key}>
              <PlanCard view={view} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="ps-plan-muted">TA 现在没有惦记的地方。</p>
      )}
      {after.length ? (
        <>
          <h3 className="ps-plan-shelf__sub">后来怎样{demo ? "（演示）" : ""}</h3>
          <ul className="ps-plan-cards ps-plan-cards--after">
            {after.map((view) => (
              <li key={view.key}>
                <PlanCard view={view} />
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
