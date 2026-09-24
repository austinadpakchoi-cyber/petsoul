/**
 * /school/result/:sessionId：成绩单。先给结论（过没过、得分、及格线），再说错在哪（红线、扣分项，每条能跳到讲解或回放），
 * 最后给下一步（补考、等到几点、去练习、去领证）；回放与错题讲解放在最后。不露判定代码、英文与技术词。
 * 成绩只来自服务端结算（规则与复算），页面不自己算分。
 */
import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, Navigate, useParams } from "react-router";
import type { Deduction, SchoolSession, SessionResult } from "@/shared/contracts";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useNow } from "@/shared/time/clock";
import { Card, Chip, ErrorState, Icon, LoadingState, Page, PetAvatar, TopBar } from "@/shared/ui";
import { SCHOOL_ART } from "../assets";
import { ReplayViewer, type ReplaySeek } from "../drive/ReplayViewer";
import { useCurriculum, usePet, useSchoolPetId } from "../hooks";
import { describeAnswer } from "../quiz/QuizRunner";
import { attemptText, formatClock, formatMoment, formatSpan, formatWait, reducedMotion, SUBJECT_SHORT } from "../text";

const ITEM_STATUS: Record<string, string> = { done: "完成", failed: "没完成", running: "没考完", pending: "没开始" };

/** 结束原因的说法（文字本身来自服务端的 label）。 */
function fatalTitle(kind: string): string {
  if (kind === "abandoned") return "中途放弃";
  if (kind === "timeout") return "超时";
  if (kind === "out_of_bounds") return "开出了场地";
  return "红线";
}

/** 结论卡里的一句“为什么没通过”：碰了红线、超时、出界、放弃时分数不算（措辞避开“中途放弃”，那是下面红线卡的标题）。 */
function whyNot(kind: string, label: string, practice: boolean): string {
  const tail = practice ? "这次练习不算达标" : "这一场不通过";
  if (kind === "abandoned") return `没考完就放弃了，${practice ? "这次练习结束" : "这一场按没通过算"}。`;
  if (kind === "timeout") return `超时了，${tail}。`;
  if (kind === "out_of_bounds") return `车开出了场地，${tail}。`;
  return `碰了红线（${label}），${tail}。`;
}

/** 跳到这一页的某一处（错题讲解、回放），并把焦点移过去。 */
function jumpTo(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  if (el instanceof HTMLDetailsElement) el.open = true;
  el.scrollIntoView?.({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });
  el.focus({ preventScroll: true });
}

function Verdict({ session, result }: { session: SchoolSession; result: SessionResult }) {
  const { pet, name } = usePet();
  const practice = session.mode === "practice";
  const verdict = practice ? (result.passed ? "练习达标" : "练习没达标") : result.passed ? "通过了" : "这次没通过";
  // 碰了红线（或超时、出界、放弃）：分数不算，大号分数灰掉、划掉，旁边写“这次不计分”，不再是醒目的彩色大字
  const voided = !result.passed && result.fatal !== null;
  return (
    <section aria-labelledby="ds-conclusion-title" className={`ps-card ds-conclusion ${result.passed ? "is-pass" : "is-fail"}`} data-testid="ds-conclusion">
      <h2 id="ds-conclusion-title" className="ds-conclusion__title">
        {verdict}
      </h2>
      <p className={`ds-conclusion__score${voided ? " is-void" : ""}`}>
        {voided ? (
          <>
            <strong aria-hidden="true">{result.score}</strong>
            <span className="visually-hidden">得分 {result.score}，</span>
            <span className="ds-conclusion__void">这次不计分</span>
          </>
        ) : (
          <>
            <strong>{result.score}</strong> 分<span className="ps-muted"> / 满分 {result.max_score}</span>
          </>
        )}
      </p>
      <p className="ds-conclusion__line">
        及格线 {result.pass_score} 分{practice ? " · 练习不计成绩、不算次数" : ""}
        {session.settled_at ? ` · ${formatClock(session.settled_at)}` : ""}
      </p>
      {!result.passed && result.fatal ? (
        <p className="ds-conclusion__line">
          <strong>{whyNot(result.fatal.kind, result.fatal.label, practice)}</strong>
        </p>
      ) : null}
      <div className="ds-pet-says">
        {pet ? <PetAvatar petId={pet.pet_id} name={name} species={pet.species} photoUrl={pet.photo_url} size={40} /> : null}
        <p>
          <strong>{name}：</strong>
          {result.pet_says}
        </p>
      </div>
    </section>
  );
}

/** 扣分 / 红线发生在回放里的哪一处：有项目、有 tick、而且那一项有保存下来的操作可以回放，才给“看回放”。 */
function replaySpot(d: Deduction, replayable: Set<string>): { item: string; tick: number } | null {
  return d.item && d.t !== null && replayable.has(d.item) ? { item: d.item, tick: d.t } : null;
}

type OnReplay = (spot: { item: string; tick: number }) => void;

/** 一条扣分：哪一项、第几秒、扣几分；答题类跳到那道题的讲解，驾驶类跳到回放里那一刻。 */
function DeductionRow({ d, titles, replayable, hasReview, onReplay }: { d: Deduction; titles: Map<string, string>; replayable: Set<string>; hasReview: boolean; onReplay: OnReplay }) {
  const itemTitle = d.item ? titles.get(d.item) : undefined;
  const review = d.question_id && hasReview ? `ds-q-${d.question_id}` : null;
  const spot = review ? null : replaySpot(d, replayable);
  return (
    <li>
      <span className="ds-wrong__what">
        {d.label}
        {itemTitle ? <span className="ps-muted"> · {itemTitle}</span> : null}
        {d.t !== null ? <span className="ps-muted"> · {formatMoment(d.t)}</span> : null}
        {review ? (
          <button type="button" className="ds-jump" onClick={() => jumpTo(review)}>
            看讲解
          </button>
        ) : spot ? (
          <button type="button" className="ds-jump" data-item={spot.item} data-tick={spot.tick} onClick={() => onReplay(spot)}>
            看回放
          </button>
        ) : null}
      </span>
      <span className="ds-points">−{d.points}</span>
    </li>
  );
}

function WhatWentWrong({ session, result, replayable, onReplay }: { session: SchoolSession; result: SessionResult; replayable: Set<string>; onReplay: OnReplay }) {
  const titles = new Map((session.drive?.items ?? []).map((it) => [it.item, it.title]));
  const fatalSpot = result.fatal ? replaySpot(result.fatal, replayable) : null;
  const hasReview = result.review.some((r) => !r.correct);
  const nothing = !result.fatal && !result.deductions.length;
  const allRight = result.review.length > 0 && !hasReview;
  return (
    <section aria-labelledby="ds-wrong" className="ps-stack ds-wrong">
      <h2 id="ds-wrong" className="ps-section-title">
        {nothing ? "扣分" : "错在哪"}
      </h2>
      {result.fatal ? (
        <Card className="ds-fatal" role="note">
          <strong className="ds-fatal__title">
            <Icon name="alert" size={18} />
            {fatalTitle(result.fatal.kind)}：{result.fatal.label}
          </strong>
          <span className="ds-fatal__when">
            {result.fatal.t !== null ? `${formatMoment(result.fatal.t)}，已自动制动；这一场到这里结束。` : "这一场到这里结束。"}
            {fatalSpot ? (
              <button type="button" className="ds-jump" data-item={fatalSpot.item} data-tick={fatalSpot.tick} onClick={() => onReplay(fatalSpot)}>
                看回放
              </button>
            ) : null}
          </span>
        </Card>
      ) : null}
      <Card flat>
        {result.deductions.length ? (
          <ul className="ds-list ds-deduction-list ds-wrong__list">
            {result.deductions.map((d, i) => (
              <DeductionRow key={`${d.kind}-${i}`} d={d} titles={titles} replayable={replayable} hasReview={hasReview} onReplay={onReplay} />
            ))}
          </ul>
        ) : (
          <p className="ps-muted" style={{ margin: 0 }}>
            {result.fatal ? "结束之前没有扣分。" : allRight ? `${result.review.length} 道题全部答对，没有扣分。` : "没有扣分。"}
          </p>
        )}
        {result.items.length ? (
          <ul className="ds-list ds-deduction-list ds-items">
            {result.items.map((it) => (
              <li key={it.item}>
                <span>
                  {it.title} · {ITEM_STATUS[it.status] ?? "没考完"}
                  <span className="ps-muted"> · 用了 {formatSpan(it.ticks)}</span>
                </span>
                <span className="ds-points">{it.deducted ? `−${it.deducted}` : "0"}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </Card>
    </section>
  );
}

/** 素材图：只作装饰（alt=""，旁边的文字写了教练名字）；加载失败就不画（这里原来没有图）。 */
function Art({ src, size, className }: { src: string; size: number; className?: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) return null;
  return <img className={className} src={src} alt="" width={size} height={size} loading="lazy" decoding="async" onError={() => setFailed(true)} />;
}

/** 龟教练的一句鼓励：通过时鼓掌，没通过时讲解（不责怪谁，只说接下来怎么练）。 */
function CoachWord({ passed, coachName }: { passed: boolean; coachName: string }) {
  return (
    <div className="ds-result-coach" data-testid="ds-result-coach">
      <Art src={passed ? SCHOOL_ART.coach.cheer : SCHOOL_ART.coach.explain} size={72} />
      <p>
        <strong>{coachName}</strong>：{passed ? "稳稳当当，做得真好！" : "没关系，把要练的地方再练几遍，下次会更稳。"}
      </p>
    </div>
  );
}

function NextStepCard({ session, result, coachName }: { session: SchoolSession; result: SessionResult; coachName: string }) {
  const now = useNow(30_000);
  const next = result.next;
  if (!next) return null;
  const subjectLink = `/school/subject/${session.subject}`;
  return (
    <section aria-labelledby="ds-next-title" className="ps-card ps-stack ds-next">
      <h2 id="ds-next-title" className="ds-next__eyebrow">
        下一步
      </h2>
      <CoachWord passed={result.passed} coachName={coachName} />
      <strong>{next.message}</strong>
      {next.kind === "cooldown" && next.cooldown_until ? (
        <p className="ps-muted">
          {formatClock(next.cooldown_until)} 后可以再约考试（{formatWait(next.cooldown_until, now)}）。这段时间可以不限次数地练习，TA 的生活和旅行照常。
        </p>
      ) : null}
      {next.kind === "licensed" ? (
        <Link className="ps-btn ps-btn--primary ps-btn--block" to="/school/ceremony">
          去领爪爪驾照
        </Link>
      ) : next.kind === "passed" ? (
        <Link className="ps-btn ps-btn--primary ps-btn--block" to="/school">
          看看下一科
        </Link>
      ) : (
        <Link className="ps-btn ps-btn--primary ps-btn--block" to={subjectLink}>
          {next.kind === "retake" ? "先练一练，再约补考" : next.kind === "practice" ? "再练一次" : "去练习"}
        </Link>
      )}
    </section>
  );
}

/** 只讲答错（或没答）的题；序号仍是原来的第几题。全对时不出现这一段（“错在哪”里已经写了没有扣分）。 */
function Review({ session, result }: { session: SchoolSession; result: SessionResult }) {
  const views = new Map((session.quiz?.questions ?? []).map((q) => [q.question_id, q]));
  return (
    <div className="ps-stack">
      {result.review.map((r, i) => {
        if (r.correct) return null;
        const view = views.get(r.question_id);
        return (
          <details key={r.question_id} id={`ds-q-${r.question_id}`} tabIndex={-1} className={`ds-review ${r.correct ? "is-right" : "is-wrong"}`} open={!r.correct}>
            <summary>
              <span>
                {i + 1}. {r.prompt}
              </span>
              <Chip tone={r.correct ? "leaf" : "coral"}>{r.correct ? "对" : "错"}</Chip>
            </summary>
            {view ? (
              <>
                <p>你的答案：{describeAnswer(view, r.your_answer)}</p>
                {!r.correct ? <p>正确答案：{describeAnswer(view, r.correct_answer)}</p> : null}
              </>
            ) : null}
            <p className="ps-muted">{r.explanation}</p>
          </details>
        );
      })}
    </div>
  );
}

export function ResultPage() {
  const { sessionId = "" } = useParams();
  const { driving } = useServices();
  const curriculum = useCurriculum();
  const petId = useSchoolPetId();
  // 这一场属于打开成绩单时的那只宠物。切到别的宠物后，不再拿新宠物去读上一只的这一场（后端会 404），直接回驾校总览。
  // 查询键仍用共享的 queryKeys.drivingSession：考局页交卷后往这个键里放了结算结果，成绩单打开就能直接用，不能拆开。
  const openedFor = useRef(petId);
  const samePet = petId === openedFor.current;
  const query = useQuery({ queryKey: queryKeys.drivingSession(sessionId), queryFn: () => driving.session(sessionId, petId), enabled: samePet });
  // “看回放”点到的那一刻（哪一项、第几个 tick）：先滚到回放区，再把定位交给回放组件（切到那一项、跳到事发前一点、停住）。
  // nonce 每点一次加一，同一处可以重复点；同一份定位也挂在回放卡的 data-seek-* 上，供自动化核对。
  const [seek, setSeek] = useState<ReplaySeek | null>(null);
  const onReplay = (spot: { item: string; tick: number }) => {
    jumpTo("ds-replay");
    setSeek((prev) => ({ ...spot, nonce: (prev?.nonce ?? 0) + 1 }));
  };
  if (!samePet) return <Navigate to="/school" replace />;
  if (query.isPending) {
    return (
      <Page>
        <TopBar title="成绩单" back="/school" />
        <LoadingState />
      </Page>
    );
  }
  if (query.isError) {
    return (
      <Page>
        <TopBar title="成绩单" back="/school" />
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      </Page>
    );
  }
  const session = query.data;
  const result = session.result;
  if (session.state !== "settled" || !result) {
    return (
      <Page>
        <TopBar title="成绩单" back="/school" />
        <Card className="ps-stack">
          <strong>{session.state === "void" ? "这场考试已经作废，不算次数。" : "这场还没考完，暂时没有成绩。"}</strong>
          {session.state === "running" || session.state === "preparing" ? (
            <Link className="ps-btn ps-btn--primary ps-btn--block" to={`/school/session/${sessionId}`}>
              回去接着考
            </Link>
          ) : (
            <Link className="ps-btn ps-btn--primary ps-btn--block" to={`/school/subject/${session.subject}`}>
              回到{SUBJECT_SHORT[session.subject]}
            </Link>
          )}
        </Card>
      </Page>
    );
  }
  const practice = session.mode === "practice";
  const replayItems = (session.drive?.items ?? []).filter((it) => it.committed_tick > 0);
  const hasReplay = replayItems.length > 0;
  const replayable = new Set(replayItems.map((it) => it.item));
  return (
    <Page>
      <TopBar title="成绩单" subtitle={`${session.title} · ${practice ? "练习" : attemptText(session.attempt_kind)}`} back={`/school/subject/${session.subject}`} />
      <div className="ps-stack">
        <Verdict session={session} result={result} />
        <WhatWentWrong session={session} result={result} replayable={replayable} onReplay={onReplay} />
        <NextStepCard session={session} result={result} coachName={curriculum.data?.coach.name ?? "龟教练"} />

        {hasReplay ? (
          <section aria-labelledby="ds-replay-title">
            <h2 id="ds-replay-title" className="ps-section-title">
              回放：把这次的操作重新演一遍
            </h2>
            <Card flat id="ds-replay" tabIndex={-1} className="ds-replay-card" data-seek-item={seek?.item} data-seek-tick={seek?.tick} data-seek-nonce={seek?.nonce}>
              <ReplayViewer items={replayItems} reasons={curriculum.data?.reasons ?? {}} seek={seek} />
            </Card>
          </section>
        ) : null}

        {result.review.some((r) => !r.correct) ? (
          <section aria-labelledby="ds-review">
            <h2 id="ds-review" className="ps-section-title">
              错题讲解
            </h2>
            <Review session={session} result={result} />
          </section>
        ) : null}
      </div>
    </Page>
  );
}
