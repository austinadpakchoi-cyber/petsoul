/**
 * /school/subject/:subject：上课（分步教学、扣分项与红线）、练习（不限次数，科二可单项练）、约正式考试。
 * 开考前的确认写清楚：这是本轮首次考试还是补考、每轮两次机会、两次不过要等 7 天、点“开始”才计次、放弃计为不通过。
 */
import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import type { SchoolSubject, SessionCreateRequest, SubjectCurriculum, SubjectStatus } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { toApiError } from "@/shared/api/errors";
import { useServices } from "@/shared/services/registry";
import { useNow } from "@/shared/time/clock";
import { Button, Card, Chip, LoadingState, Page, Sheet, TopBar } from "@/shared/ui";
import { useCurriculum, useInvalidateSchool, useSchoolStatus } from "../hooks";
import { attemptText, formatDateTime, formatWait, isSubject, STATE_TEXT, STATE_TONE, SUBJECT_SHORT } from "../text";

function Lessons({ info }: { info: SubjectCurriculum }) {
  return (
    <section aria-labelledby="ds-lessons">
      <h2 id="ds-lessons" className="ps-section-title">
        上课 · {info.duration}
      </h2>
      <Card flat className="ds-lessons">
        {info.lessons.map((lesson, i) => (
          <details key={lesson.title} open={i === 0}>
            <summary>{lesson.title}</summary>
            <p>{lesson.body}</p>
          </details>
        ))}
      </Card>
    </section>
  );
}

function Rules({ info }: { info: SubjectCurriculum }) {
  return (
    <section aria-labelledby="ds-deductions">
      <h2 id="ds-deductions" className="ps-section-title">
        怎么算分
      </h2>
      <Card flat className="ps-stack">
        <p style={{ margin: 0 }}>
          {info.format}。<strong>{info.pass_rule}。</strong>
        </p>
        <ul className="ds-list ds-deduction-list">
          {info.deductions.map((d) => (
            <li key={d.label}>
              <span>{d.label}</span>
              <span className="ds-points">−{d.points}</span>
            </li>
          ))}
        </ul>
        {info.red_lines.length ? (
          <div className="ds-redlines">
            <strong>红线（自动制动，本次不通过）</strong>
            <ul className="ds-list">
              {info.red_lines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </Card>
    </section>
  );
}

function ExamConfirm({ subject, info, cooldownHours, onClose }: { subject: SubjectStatus; info: SubjectCurriculum; cooldownHours: number; onClose: () => void }) {
  const { driving } = useServices();
  const navigate = useNavigate();
  const invalidate = useInvalidateSchool();
  const keyRef = useRef(newIdempotencyKey("school-exam"));
  const create = useMutation({
    mutationFn: () => driving.createSession({ subject: subject.subject, mode: "formal", item: null }, keyRef.current),
    onSuccess: (session) => {
      keyRef.current = newIdempotencyKey("school-exam");
      invalidate();
      navigate(`/school/session/${session.session_id}`);
    },
  });
  const days = Math.round(cooldownHours / 24);
  return (
    <Sheet title={`约${SUBJECT_SHORT[subject.subject]}正式考试`} subtitle={`本轮${attemptText(subject.next_attempt)}`} onClose={onClose}>
      <div className="ps-stack">
        <ul className="ds-list">
          <li>
            这是本轮的<strong>{attemptText(subject.next_attempt)}</strong>。每轮有首次考试和一次补考，共两次机会{subject.attempts_used ? `，已经用了 ${subject.attempts_used} 次` : ""}。
          </li>
          <li>两次都没通过，要等 {days} 天（从第二次结算的时间算起）才能再约；练习随时可以。</li>
          <li>下一步加载考场；加载完成、点“开始考试”才算一次考试。中途断线可以回来接着考。</li>
          <li>中途主动放弃会计为这一次没通过。</li>
          <li>
            {info.pass_rule}
            {info.red_lines.length ? `；红线：${info.red_lines.join("、")}` : ""}。
          </li>
        </ul>
        {create.error ? (
          <p className="ds-error" role="alert">
            {toApiError(create.error).message}
          </p>
        ) : null}
        <Button variant="primary" block loading={create.isPending} onClick={() => create.mutate()}>
          去考场
        </Button>
        <Button variant="ghost" block onClick={onClose}>
          再练练
        </Button>
      </div>
    </Sheet>
  );
}

function Practice({ subject, info }: { subject: SchoolSubject; info: SubjectCurriculum }) {
  const { driving } = useServices();
  const navigate = useNavigate();
  const keyRef = useRef(newIdempotencyKey("school-practice"));
  const start = useMutation({
    mutationFn: (item: string | null) => {
      const body: SessionCreateRequest = { subject, mode: "practice", item };
      return driving.createSession(body, keyRef.current);
    },
    onSuccess: (session) => {
      keyRef.current = newIdempotencyKey("school-practice");
      navigate(`/school/session/${session.session_id}`);
    },
  });
  return (
    <section aria-labelledby="ds-practice">
      <h2 id="ds-practice" className="ps-section-title">
        练习（不计成绩，不限次数）
      </h2>
      <Card flat className="ps-stack">
        {info.kind === "drive" && info.practice_items.length > 1 ? (
          <div className="ds-practice-grid">
            {info.practice_items.map((item) => (
              <Button key={item.item} onClick={() => start.mutate(item.item)} disabled={start.isPending}>
                {item.title}
              </Button>
            ))}
          </div>
        ) : null}
        <Button variant="leaf" block loading={start.isPending} onClick={() => start.mutate(null)}>
          {info.kind === "drive" ? (info.items.length > 1 ? "整科连着练一遍" : "练一遍路线") : "做一套练习题"}
        </Button>
        <p className="ps-muted" style={{ margin: 0 }}>
          练习时有{info.kind === "drive" ? "预测轨迹、目标车位和分步提示" : "答完马上讲解"}；正式考试取消这些提示。
        </p>
        {start.error ? (
          <p className="ds-error" role="alert">
            {toApiError(start.error).message}
          </p>
        ) : null}
      </Card>
    </section>
  );
}

function ExamCard({ subject, onBook }: { subject: SubjectStatus; onBook: () => void }) {
  const now = useNow(30_000);
  return (
    <Card className="ps-stack ds-exam-card">
      <div className="ps-row" style={{ justifyContent: "space-between" }}>
        <strong>正式考试</strong>
        <Chip tone={STATE_TONE[subject.state]}>{STATE_TEXT[subject.state]}</Chip>
      </div>
      {subject.state === "passed" ? (
        <p className="ps-muted">{subject.legacy ? "旧版驾考已通过，不用再考。" : `${subject.passed_score} 分通过（${formatDateTime(subject.passed_at)}），成绩一直保留。`}</p>
      ) : subject.state === "cooldown" ? (
        <p className="ps-muted">
          这一轮两次都没通过。{formatWait(subject.cooldown_until!, now)}（{formatDateTime(subject.cooldown_until)} 后可以再约）。这段时间可以不限次数地练习。
        </p>
      ) : subject.state === "locked" ? (
        <p className="ps-muted">{subject.unlock_hint}，才能约这一科的正式考试。现在就可以上课和练习。</p>
      ) : subject.state === "in_exam" ? (
        <>
          <p className="ps-muted">这一科有一场正式考试还没结束，回去从保存的位置接着考。</p>
          <Link className="ps-btn ps-btn--primary ps-btn--block" to={`/school/session/${subject.open_session_id}`}>
            回去接着考
          </Link>
        </>
      ) : (
        <>
          <p className="ps-muted">
            第 {subject.round_no} 轮 · 还有 {subject.attempts_left} 次机会 · 下一次是{attemptText(subject.next_attempt)}
          </p>
          <Button variant="primary" block onClick={onBook}>
            约{attemptText(subject.next_attempt)}
          </Button>
        </>
      )}
      {subject.last_result ? (
        <Link className="ds-link" to={`/school/result/${subject.last_result.session_id}`}>
          上一次正式考试：{subject.last_result.score ?? "—"} 分，{subject.last_result.passed ? "通过" : "没通过"} · 看成绩单
        </Link>
      ) : null}
    </Card>
  );
}

export function SubjectPage() {
  const params = useParams();
  const status = useSchoolStatus();
  const curriculum = useCurriculum();
  const [booking, setBooking] = useState(false);
  if (!isSubject(params.subject)) return <Navigate to="/school" replace />;
  const key = params.subject;
  const info = curriculum.data?.subjects.find((s) => s.subject === key);
  const subject = status.data?.subjects.find((s) => s.subject === key);
  const enrolled = status.data && status.data.stage !== "none" && status.data.stage !== "wish";
  return (
    <Page>
      <TopBar title={info ? info.title.split("：")[0] : SUBJECT_SHORT[key]} subtitle={info?.theme} back="/school" />
      {!info || !subject ? (
        status.isError || curriculum.isError ? (
          <p className="ds-error" role="alert">
            {toApiError(status.error ?? curriculum.error).message}
          </p>
        ) : (
          <LoadingState />
        )
      ) : (
        <div className="ps-stack">
          <h1 className="ps-h1">{info.title.split("：")[1]}</h1>
          {enrolled ? (
            <ExamCard subject={subject} onBook={() => setBooking(true)} />
          ) : (
            <Card flat>
              <p className="ps-muted" style={{ margin: 0 }}>
                先回驾校首页陪 TA 报名，报名后就能练习和约考试。
              </p>
              <Link className="ps-btn ps-btn--primary ps-btn--block" to="/school">
                去报名
              </Link>
            </Card>
          )}
          <Lessons info={info} />
          <Rules info={info} />
          {enrolled ? <Practice subject={key} info={info} /> : null}
          {info.kind === "drive" && curriculum.data ? (
            <details className="ds-controls-help">
              <summary>怎么操作</summary>
              <ul className="ds-list">
                {curriculum.data.controls.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>
      )}
      {booking && info && subject && curriculum.data ? (
        <ExamConfirm subject={subject} info={info} cooldownHours={curriculum.data.cooldown_hours} onClose={() => setBooking(false)} />
      ) : null}
    </Page>
  );
}
