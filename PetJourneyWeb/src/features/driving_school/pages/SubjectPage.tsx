/**
 * /school/subject/:subject：一科的三个入口——上课（分步教学）、练习（不计成绩，不限次数，科二可单项练）、正式考试。
 * 顶上三个入口各写一句现在的状态，点了跳到那一段；正式考试那段写清这是第几次机会、没过会怎样、冷却到本地几点、通过的样子。
 * 开考前的确认写清楚：这是本轮首次考试还是补考、每轮两次机会、两次不过要等 7 天、点“开始”才计次、放弃计为不通过。
 */
import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import type { CoachInfo, SchoolSubject, SessionCreateRequest, SubjectCurriculum, SubjectStatus } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { toApiError } from "@/shared/api/errors";
import { useServices } from "@/shared/services/registry";
import { useNow } from "@/shared/time/clock";
import { Button, Card, Chip, Icon, LoadingState, Page, Sheet, TopBar, type IconName } from "@/shared/ui";
import { SCHOOL_ART } from "../assets";
import { useCurriculum, useInvalidateSchool, useSchoolPetId, useSchoolStatus } from "../hooks";
import { attemptText, formatClock, formatWait, isSubject, reducedMotion, STATE_TEXT, STATE_TONE, SUBJECT_SHORT } from "../text";

/** 跳到这一页的某一段，并把焦点移到那一段的标题上（键盘、读屏跟着走）。 */
function jumpTo(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView?.({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });
  el.focus({ preventScroll: true });
}

/** 正式考试入口上的一句话状态。 */
function examShort(subject: SubjectStatus, enrolled: boolean): string {
  if (!enrolled) return "报名后开放";
  switch (subject.state) {
    case "passed":
      return subject.legacy ? "旧版已通过" : `已通过 · ${subject.passed_score ?? "—"} 分`;
    case "cooldown": {
      const until = formatClock(subject.cooldown_until);
      return until ? `${until} 后可约` : "等待中";
    }
    case "locked":
      return subject.unlock_hint ?? "未解锁";
    case "in_exam":
      return "还没考完";
    default:
      return `可以约${attemptText(subject.next_attempt)}`;
  }
}

function Entry({ target, icon, title, note, className = "" }: { target: string; icon: IconName; title: string; note: string; className?: string }) {
  return (
    <button type="button" className={`ds-entry ${className}`} onClick={() => jumpTo(target)} aria-describedby={`${target}-note`}>
      <Icon name={icon} size={18} />
      <strong>{title}</strong>
      <span id={`${target}-note`}>{note}</span>
    </button>
  );
}

function Entries({ info, subject, enrolled }: { info: SubjectCurriculum; subject: SubjectStatus; enrolled: boolean }) {
  return (
    <nav className="ds-entries" aria-label="这一科的三个入口">
      <Entry target="ds-lessons" icon="bookmark" title="上课" note={info.duration} />
      <Entry target="ds-practice" icon="refresh" title="练习" note={enrolled ? (subject.practice_count ? `已练 ${subject.practice_count} 次` : "不计成绩") : "报名后开放"} />
      <Entry target="ds-exam" icon="check" title="正式考试" note={examShort(subject, enrolled)} className={`ds-entry--exam is-${enrolled ? subject.state : "locked"}`} />
    </nav>
  );
}

/** 素材图：只作装饰（alt=""，旁边的文字写了教练名字）；加载失败就不画（这里原来没有图）。 */
function Art({ src, size, className }: { src: string; size: number; className?: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) return null;
  return <img className={className} src={src} alt="" width={size} height={size} loading="lazy" decoding="async" onError={() => setFailed(true)} />;
}

function Lessons({ info, coach }: { info: SubjectCurriculum; coach: CoachInfo | null }) {
  return (
    <section aria-labelledby="ds-lessons">
      <h2 id="ds-lessons" className="ps-section-title ds-jump-target" tabIndex={-1}>
        上课 · {info.duration}
      </h2>
      <Card flat className="ds-lessons">
        {coach ? (
          <div className="ds-lesson-coach">
            <Art src={SCHOOL_ART.coach.explain} size={72} />
            <p>
              <strong>{coach.name}</strong>：“{coach.line}”
            </p>
          </div>
        ) : null}
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
    <Card flat className="ps-stack">
      <strong>怎么算分</strong>
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
  );
}

function ExamConfirm({ subject, info, cooldownHours, onClose }: { subject: SubjectStatus; info: SubjectCurriculum; cooldownHours: number; onClose: () => void }) {
  const { driving } = useServices();
  const navigate = useNavigate();
  const invalidate = useInvalidateSchool();
  const petId = useSchoolPetId();
  const keyRef = useRef(newIdempotencyKey("school-exam"));
  const create = useMutation({
    mutationFn: () => driving.createSession({ subject: subject.subject, mode: "formal", item: null }, keyRef.current, petId),
    onSuccess: (session) => {
      keyRef.current = newIdempotencyKey("school-exam");
      invalidate();
      navigate(`/school/session/${session.session_id}`);
    },
  });
  const days = Math.round(cooldownHours / 24);
  const retake = subject.next_attempt === "retake";
  return (
    <Sheet title={`约${SUBJECT_SHORT[subject.subject]}正式考试`} subtitle={`本轮${attemptText(subject.next_attempt)}`} onClose={onClose}>
      <div className="ps-stack">
        <ul className="ds-list">
          <li>
            这是本轮的<strong>{attemptText(subject.next_attempt)}</strong>。每轮有首次考试和一次补考，共两次机会{subject.attempts_used ? `，已经用了 ${subject.attempts_used} 次` : ""}。
          </li>
          <li>
            {retake
              ? `这是本轮最后一次机会：这次也没通过，要等 ${days} 天（从这次结算的时间算起）才能再约；练习随时可以。`
              : `这次没通过也没关系，还有一次补考；两次都没通过，要等 ${days} 天（从第二次结算的时间算起）才能再约；练习随时可以。`}
          </li>
          <li>下一步加载考场；加载完成、点“开始考试”才算一次考试。中途断线可以回来接着考。</li>
          <li>中途主动放弃会计为这一次没通过。</li>
          <li>
            {info.pass_rule}
            {info.red_lines.length ? `；红线：${info.red_lines.join("、")}` : ""}。
          </li>
        </ul>
        {create.error ? (
          <p className="ds-error" role="alert">
            {toApiError(create.error).playerMessage}
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

function Practice({ subject, info, enrolled }: { subject: SchoolSubject; info: SubjectCurriculum; enrolled: boolean }) {
  const { driving } = useServices();
  const navigate = useNavigate();
  const petId = useSchoolPetId();
  const keyRef = useRef(newIdempotencyKey("school-practice"));
  const start = useMutation({
    mutationFn: (item: string | null) => {
      const body: SessionCreateRequest = { subject, mode: "practice", item };
      return driving.createSession(body, keyRef.current, petId);
    },
    onSuccess: (session) => {
      keyRef.current = newIdempotencyKey("school-practice");
      navigate(`/school/session/${session.session_id}`);
    },
  });
  return (
    <section aria-labelledby="ds-practice">
      <h2 id="ds-practice" className="ps-section-title ds-jump-target" tabIndex={-1}>
        练习（不计成绩，不限次数）
      </h2>
      <Card flat className="ps-stack">
        {!enrolled ? (
          <p className="ps-muted" style={{ margin: 0 }}>
            报名以后就能练习；练多少次都不算考试次数。
          </p>
        ) : (
          <>
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
              {info.kind === "drive" ? "练习时有预测轨迹、目标车位和分步提示；正式考试取消这些提示。" : "练习时每道题答完马上讲解；正式考试交卷前不给任何提示。"}
            </p>
          </>
        )}
        {start.error ? (
          <p className="ds-error" role="alert">
            {toApiError(start.error).playerMessage}
          </p>
        ) : null}
      </Card>
    </section>
  );
}

function ExamCard({ subject, cooldownHours, onBook }: { subject: SubjectStatus; cooldownHours: number | null; onBook: () => void }) {
  const now = useNow(30_000);
  const until = formatClock(subject.cooldown_until);
  return (
    <Card className={`ps-stack ds-exam-card is-${subject.state}`} data-testid="ds-exam-card">
      <div className="ps-row" style={{ justifyContent: "space-between" }}>
        <strong>{subject.state === "passed" ? "已经考过了" : "这一科的正式考试"}</strong>
        <Chip tone={STATE_TONE[subject.state]}>{STATE_TEXT[subject.state]}</Chip>
      </div>
      {subject.state === "passed" ? (
        <p className="ds-exam-card__big">
          <Icon name="check" size={20} />
          {subject.legacy ? "旧版驾考已通过，不用再考。" : `${subject.passed_score ?? "—"} 分通过${subject.passed_at ? `（${formatClock(subject.passed_at)}）` : ""}，成绩一直保留，不用再考。`}
        </p>
      ) : subject.state === "cooldown" ? (
        <>
          <p className="ds-exam-card__big">{until ? `${until} 后可以再约` : "这一轮的两次机会用完了"}</p>
          <p className="ps-muted">
            {subject.cooldown_until ? `${formatWait(subject.cooldown_until, now)}。` : ""}这一轮两次都没通过；这段时间可以不限次数地练习，等到了再约新一轮的两次机会。
          </p>
        </>
      ) : subject.state === "locked" ? (
        <p className="ps-muted">{subject.unlock_hint ?? "还没解锁"}，才能约这一科的正式考试。现在就可以上课和练习。</p>
      ) : subject.state === "in_exam" ? (
        <>
          <p className="ps-muted">这一科有一场正式考试还没考完，回去从保存的位置接着考，不会重新抽题。</p>
          {subject.open_session_id ? (
            <Link className="ps-btn ps-btn--primary ps-btn--block" to={`/school/session/${subject.open_session_id}`}>
              回去接着考
            </Link>
          ) : null}
        </>
      ) : (
        <>
          <p className="ds-exam-card__big">
            这次是{attemptText(subject.next_attempt)} · 本轮还剩 {subject.attempts_left} 次机会
          </p>
          <p className="ps-muted">
            {subject.next_attempt === "retake"
              ? `这是本轮最后一次机会：没通过的话${cooldownHours ? `要等 ${Math.round(cooldownHours / 24)} 天` : "要等一段时间"}才能再约。`
              : `没通过还有一次补考；两次都没通过${cooldownHours ? `要等 ${Math.round(cooldownHours / 24)} 天` : "要等一段时间"}才能再约。`}
            {subject.round_no > 1 ? `（第 ${subject.round_no} 轮）` : ""}
          </p>
          <Button variant="primary" block onClick={onBook}>
            约{attemptText(subject.next_attempt)}
          </Button>
        </>
      )}
      {subject.last_result ? (
        <Link className="ds-link ds-exam-card__last" to={`/school/result/${subject.last_result.session_id}`}>
          上一次正式考试：{subject.last_result.score ?? "—"} 分，{subject.last_result.passed ? "通过" : "没通过"} · 看成绩单
        </Link>
      ) : null}
    </Card>
  );
}

function Exam({ subject, info, enrolled, cooldownHours, onBook }: { subject: SubjectStatus; info: SubjectCurriculum; enrolled: boolean; cooldownHours: number | null; onBook: () => void }) {
  return (
    <section aria-labelledby="ds-exam" className="ps-stack">
      <h2 id="ds-exam" className="ps-section-title ds-jump-target" tabIndex={-1}>
        正式考试
      </h2>
      {enrolled ? (
        <ExamCard subject={subject} cooldownHours={cooldownHours} onBook={onBook} />
      ) : (
        <Card flat>
          <p className="ps-muted" style={{ margin: 0 }}>
            报名以后，正式考试按科目一到科目四依次解锁。
          </p>
        </Card>
      )}
      <Rules info={info} />
    </section>
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
  const enrolled = Boolean(status.data && status.data.stage !== "none" && status.data.stage !== "wish");
  return (
    <Page>
      <TopBar title={info ? info.title.split("：")[0] : SUBJECT_SHORT[key]} subtitle={info?.theme} back="/school" />
      {!info || !subject ? (
        status.isError || curriculum.isError ? (
          <p className="ds-error" role="alert">
            {toApiError(status.error ?? curriculum.error).playerMessage}
          </p>
        ) : (
          <LoadingState />
        )
      ) : (
        <div className="ps-stack">
          <h1 className="ps-h1">{info.title.split("：")[1]}</h1>
          {!enrolled ? (
            <Card flat className="ps-stack">
              <p className="ps-muted" style={{ margin: 0 }}>
                先回驾校首页陪 TA 报名，报名后就能练习和约考试。
              </p>
              <Link className="ps-btn ps-btn--primary ps-btn--block" to="/school">
                去报名
              </Link>
            </Card>
          ) : null}
          <Entries info={info} subject={subject} enrolled={enrolled} />
          <Lessons info={info} coach={curriculum.data?.coach ?? null} />
          <Practice subject={key} info={info} enrolled={enrolled} />
          <Exam subject={subject} info={info} enrolled={enrolled} cooldownHours={curriculum.data?.cooldown_hours ?? null} onBook={() => setBooking(true)} />
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
