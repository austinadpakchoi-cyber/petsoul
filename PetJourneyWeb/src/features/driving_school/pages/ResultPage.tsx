/**
 * /school/result/:sessionId：成绩单——分数与通过线、红线原因、扣分明细（第几秒、哪一项）、回放与标记、错题回顾、TA 的话、下一步。
 * 成绩只来自服务端结算（规则与复算），页面不自己算分。
 */
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import type { SchoolSession, SessionResult } from "@/shared/contracts";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useNow } from "@/shared/time/clock";
import { Card, Chip, ErrorState, LoadingState, Page, PetAvatar, TopBar } from "@/shared/ui";
import { ReplayViewer } from "../drive/ReplayViewer";
import { useCurriculum, usePet, useSchoolPetId } from "../hooks";
import { describeAnswer } from "../quiz/QuizRunner";
import { attemptText, formatDateTime, formatTicks, formatWait, SUBJECT_SHORT } from "../text";

function NextStepCard({ session, result }: { session: SchoolSession; result: SessionResult }) {
  const now = useNow(30_000);
  const next = result.next;
  if (!next) return null;
  const subjectLink = `/school/subject/${session.subject}`;
  return (
    <Card className="ps-stack ds-next">
      <strong>{next.message}</strong>
      {next.kind === "cooldown" && next.cooldown_until ? (
        <p className="ps-muted">
          {formatWait(next.cooldown_until, now)}，{formatDateTime(next.cooldown_until)} 后可以再约考试。这段时间可以不限次数地练习，TA 的生活和旅行照常。
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
    </Card>
  );
}

function Deductions({ session, result }: { session: SchoolSession; result: SessionResult }) {
  const titles = new Map((session.drive?.items ?? []).map((it) => [it.item, it.title]));
  if (!result.deductions.length) return <p className="ps-muted">没有扣分。</p>;
  return (
    <ul className="ds-list ds-deduction-list">
      {result.deductions.map((d, i) => (
        <li key={`${d.kind}-${i}`}>
          <span>
            {d.label}
            {d.item ? <span className="ps-muted"> · {titles.get(d.item) ?? d.item}</span> : null}
            {d.t !== null ? <span className="ps-muted"> · 第 {formatTicks(d.t)}</span> : null}
          </span>
          <span className="ds-points">−{d.points}</span>
        </li>
      ))}
    </ul>
  );
}

function Review({ session, result }: { session: SchoolSession; result: SessionResult }) {
  const views = new Map((session.quiz?.questions ?? []).map((q) => [q.question_id, q]));
  return (
    <div className="ps-stack">
      {result.review.map((r, i) => {
        const view = views.get(r.question_id);
        return (
          <details key={r.question_id} className={`ds-review ${r.correct ? "is-right" : "is-wrong"}`} open={!r.correct}>
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
  const { pet, name } = usePet();
  const petId = useSchoolPetId();
  const query = useQuery({ queryKey: queryKeys.drivingSession(sessionId), queryFn: () => driving.session(sessionId, petId) });
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
          <strong>{session.state === "void" ? "这场考局已经作废，不计次。" : "这场还没结束，暂时没有成绩。"}</strong>
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
  return (
    <Page>
      <TopBar title="成绩单" subtitle={`${session.title} · ${practice ? "练习" : attemptText(session.attempt_kind)}`} back={`/school/subject/${session.subject}`} />
      <div className="ps-stack">
        <Card className={`ds-score ${result.passed ? "is-pass" : "is-fail"}`}>
          <div className="ds-score__num">
            <strong>{result.score}</strong>
            <span>/ {result.max_score}</span>
          </div>
          <div className="ps-stack" style={{ gap: 4 }}>
            <Chip tone={result.passed ? "leaf" : practice ? "sky" : "coral"}>{practice ? (result.passed ? "练习达标" : "练习未达标") : result.passed ? "通过" : "没通过"}</Chip>
            <span className="ps-muted">
              通过线 {result.pass_score} 分{practice ? " · 练习不计成绩" : ""} · {formatDateTime(session.settled_at)}
            </span>
          </div>
        </Card>
        {result.fatal ? (
          <Card className="ds-fatal" role="note">
            <strong>{result.fatal.kind === "abandoned" ? "中途放弃" : result.fatal.kind === "timeout" ? "超时" : "红线"}：{result.fatal.label}</strong>
            {result.fatal.t !== null ? <span className="ps-muted">第 {formatTicks(result.fatal.t)}，已自动制动</span> : null}
          </Card>
        ) : null}
        <Card flat className="ds-pet-says">
          {pet ? <PetAvatar petId={pet.pet_id} name={name} species={pet.species} photoUrl={pet.photo_url} size={40} /> : null}
          <p>
            <strong>{name}：</strong>
            {result.pet_says}
          </p>
        </Card>
        <NextStepCard session={session} result={result} />

        {result.items.length ? (
          <section aria-labelledby="ds-items">
            <h2 id="ds-items" className="ps-section-title">
              各项
            </h2>
            <Card flat>
              <ul className="ds-list ds-deduction-list">
                {result.items.map((it) => (
                  <li key={it.item}>
                    <span>
                      {it.title} · {it.status === "done" ? "完成" : it.status === "failed" ? "没完成" : "没开始"}
                      <span className="ps-muted"> · 用时 {formatTicks(it.ticks)}</span>
                    </span>
                    <span className="ds-points">{it.deducted ? `−${it.deducted}` : "0"}</span>
                  </li>
                ))}
              </ul>
            </Card>
          </section>
        ) : null}

        <section aria-labelledby="ds-deduct">
          <h2 id="ds-deduct" className="ps-section-title">
            扣分明细
          </h2>
          <Card flat>
            <Deductions session={session} result={result} />
          </Card>
        </section>

        {session.drive && session.drive.items.some((it) => it.committed_tick > 0) ? (
          <section aria-labelledby="ds-replay">
            <h2 id="ds-replay" className="ps-section-title">
              回放（按服务器保存的操作重新演一遍）
            </h2>
            <Card flat>
              <ReplayViewer items={session.drive.items.filter((it) => it.committed_tick > 0)} reasons={curriculum.data?.reasons ?? {}} />
            </Card>
          </section>
        ) : null}

        {result.review.length ? (
          <section aria-labelledby="ds-review">
            <h2 id="ds-review" className="ps-section-title">
              错题回顾
            </h2>
            <Review session={session} result={result} />
          </section>
        ) : null}
      </div>
    </Page>
  );
}
