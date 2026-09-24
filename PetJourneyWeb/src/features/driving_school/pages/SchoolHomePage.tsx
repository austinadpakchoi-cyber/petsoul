/** /school：爪爪驾校总览——认识教练、陪 TA 报名、四科状态（机会、冷却、成绩）、未结束的考试、驾照与领证、补考规则、最近记录。 */
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router";
import type { DrivingSchoolStatus, SchoolCurriculum, SubjectStatus } from "@/shared/contracts";
import { toApiError } from "@/shared/api/errors";
import { useNow } from "@/shared/time/clock";
import { useServices } from "@/shared/services/registry";
import { Button, Card, Chip, DataOriginBadge, Icon, Page, PetAvatar, QueryView, TopBar } from "@/shared/ui";
import { env } from "@/shared/config/env";
import { useCurriculum, useInvalidateSchool, usePet, useSchoolHistory, useSchoolPetId, useSchoolStatus } from "../hooks";
import { attemptText, formatDateTime, formatWait, STATE_TEXT, STATE_TONE, SUBJECT_SHORT } from "../text";

function SubjectLine({ subject, now }: { subject: SubjectStatus; now: number }) {
  let detail: string;
  if (subject.state === "passed") detail = subject.legacy ? "旧版驾考已通过" : `${subject.passed_score ?? "—"} 分通过 · ${formatDateTime(subject.passed_at)}`;
  else if (subject.state === "cooldown") detail = `两次都没通过，${formatWait(subject.cooldown_until!, now)}；练习随时可以`;
  else if (subject.state === "locked") detail = `${subject.unlock_hint}，才能约正式考试；上课和练习随时可以`;
  else if (subject.state === "in_exam") detail = "有一场正式考试还没结束，回去接着考";
  else detail = `本轮还有 ${subject.attempts_left} 次机会，下一次是${attemptText(subject.next_attempt)}`;
  return (
    <Link to={`/school/subject/${subject.subject}`} className="ds-subject-row">
      <span className="ds-subject-row__no">{SUBJECT_SHORT[subject.subject].slice(2)}</span>
      <span className="ds-subject-row__body">
        <strong>{subject.title.split("：")[1] ?? subject.title}</strong>
        <span className="ps-muted">{detail}</span>
      </span>
      <Chip tone={STATE_TONE[subject.state]}>{STATE_TEXT[subject.state]}</Chip>
    </Link>
  );
}

function Enroll({ status }: { status: DrivingSchoolStatus }) {
  const { driving } = useServices();
  const invalidate = useInvalidateSchool();
  const { name } = usePet();
  const petId = useSchoolPetId();
  const enroll = useMutation({ mutationFn: () => driving.enroll(petId), onSuccess: invalidate });
  return (
    <Card paper className="ps-stack">
      <strong className="ps-h2">{status.wish_text ? `${name}想学开车` : `陪${name}学开车`}</strong>
      {status.wish_text ? <p className="ds-quote">“{status.wish_text}”</p> : <p className="ps-muted">以前是你开车带 TA 出门；这一次，你陪 TA 学会开车。</p>}
      <p className="ps-muted">报名后可以上课、不限次数练习；正式考试按科目一到科目四依次解锁。</p>
      <Button variant="primary" block loading={enroll.isPending} onClick={() => enroll.mutate()}>
        陪 {name} 报名爪爪驾校
      </Button>
      {enroll.error ? <p className="ds-error" role="alert">{toApiError(enroll.error).message}</p> : null}
    </Card>
  );
}

function LicenseCard({ status }: { status: DrivingSchoolStatus }) {
  const license = status.license!;
  return (
    <Card paper className="ds-license-mini">
      <div className="ps-row" style={{ justifyContent: "space-between" }}>
        <strong>PetSoul · 爪爪驾驶证</strong>
        <Chip tone="leaf" icon="check">
          已签发
        </Chip>
      </div>
      <div className="ps-muted">
        编号 {license.number} · {formatDateTime(license.issued_at)}
      </div>
      {status.voucher_available ? <div className="ps-muted">还有一张驾校借车券：第一次自驾不用租车费。</div> : null}
      <Link className={`ps-btn ${status.ceremony_done ? "ps-btn--secondary" : "ps-btn--primary"} ps-btn--block`} to="/school/ceremony">
        {status.ceremony_done ? "回看领证仪式" : "去领证：盖章、合影"}
      </Link>
    </Card>
  );
}

function Overview({ status, curriculum }: { status: DrivingSchoolStatus; curriculum: SchoolCurriculum | undefined }) {
  const now = useNow(30_000);
  const { pet, name } = usePet();
  const history = useSchoolHistory();
  const passed = status.subjects.filter((s) => s.state === "passed").length;
  const enrolled = status.stage !== "none" && status.stage !== "wish";
  return (
    <div className="ps-stack">
      <Card className="ds-coach">
        <div className="ds-coach__face" aria-hidden="true">
          <svg viewBox="0 0 48 48">
            <ellipse cx="22" cy="30" rx="17" ry="12" className="ds-turtle-shell" />
            <circle cx="40" cy="24" r="6" className="ds-turtle-head" />
            <circle cx="42" cy="22" r="1.2" className="ds-turtle-eye" />
          </svg>
        </div>
        <div>
          <strong>{status.coach.name}</strong>
          <p className="ds-quote">“{status.coach.line}”</p>
          <p className="ps-muted">{status.coach.intro}</p>
        </div>
      </Card>

      {!enrolled ? <Enroll status={status} /> : null}

      {status.open_session ? (
        <Card className="ds-alert-card">
          <Icon name="alert" />
          <div>
            <strong>{SUBJECT_SHORT[status.open_session.subject]}有一场正式考试还没结束</strong>
            <p className="ps-muted">回去会从服务器保存的位置接着考，不会重新抽题。</p>
          </div>
          <Link className="ps-btn ps-btn--primary ps-btn--sm" to={`/school/session/${status.open_session.session_id}`}>
            接着考
          </Link>
        </Card>
      ) : null}

      {status.license ? <LicenseCard status={status} /> : null}

      <section aria-labelledby="ds-subjects">
        <div className="ps-row" style={{ justifyContent: "space-between" }}>
          <h2 id="ds-subjects" className="ps-section-title">
            四个科目 · 已通过 {passed}/4
          </h2>
          {pet ? <PetAvatar petId={pet.pet_id} name={name} species={pet.species} photoUrl={pet.photo_url} size={28} /> : null}
        </div>
        <Card className="ds-subjects">
          {status.subjects.map((s) => (
            <SubjectLine key={s.subject} subject={s} now={now} />
          ))}
        </Card>
      </section>

      {curriculum ? (
        <section aria-labelledby="ds-rules">
          <h2 id="ds-rules" className="ps-section-title">
            补考与等待
          </h2>
          <Card flat>
            <ul className="ds-list">
              {curriculum.retake_rule.map((line) => (
                <li key={line}>{line}</li>
              ))}
              <li>不卖补考次数，也不能花钱缩短等待；没考过不会影响你们的亲密度。</li>
            </ul>
          </Card>
        </section>
      ) : null}

      {history.data && history.data.length ? (
        <section aria-labelledby="ds-history">
          <h2 id="ds-history" className="ps-section-title">
            最近的练习与考试（只有你能看到）
          </h2>
          <Card flat className="ds-history">
            {history.data.slice(0, 8).map((h) => (
              <Link key={h.session_id} to={h.state === "running" ? `/school/session/${h.session_id}` : `/school/result/${h.session_id}`} className="ds-history__row">
                <span>
                  {SUBJECT_SHORT[h.subject]} · {h.mode === "practice" ? "练习" : attemptText(h.attempt_kind)}
                </span>
                <span className="ps-muted">{h.state === "running" ? "进行中" : `${h.score ?? "—"} 分 ${h.passed ? "通过" : h.mode === "practice" ? "" : "未通过"}`}</span>
              </Link>
            ))}
          </Card>
        </section>
      ) : null}

      <Link to="/school/try" className="ds-try-link">
        <Icon name="car" />
        <span>
          <strong>倒车入库体验版</strong>
          <span className="ps-muted">比赛现场随手试试：不计成绩，不发证。</span>
        </span>
        <Icon name="chevron" size={16} />
      </Link>
      <p className="ps-muted ds-footnote">爪爪驾校是 PetSoul 星球上的虚构机构；这里的扣分数值是游戏规则，不代表现实驾考标准，驾照也不代表现实驾驶资格。</p>
    </div>
  );
}

export function SchoolHomePage() {
  const status = useSchoolStatus();
  const curriculum = useCurriculum();
  return (
    <Page>
      <TopBar title="爪爪驾校" subtitle="主人陪考，宠物拿证" back="/map" right={env.dataMode === "fixture" ? <DataOriginBadge origin="fixture" /> : undefined} />
      <QueryView query={status}>{(data) => <Overview status={data} curriculum={curriculum.data} />}</QueryView>
    </Page>
  );
}
