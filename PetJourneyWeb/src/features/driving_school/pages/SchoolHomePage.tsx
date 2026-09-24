/**
 * /school：爪爪驾校总览。一眼看懂：
 * - 顶上一张“现在 / 下一步”卡：走到哪一步、下一步做什么，只有一个主要动作（报名、接着考、去某一科、去领证）；
 * - 紧接着四科：每科的状态、还剩几次机会、冷却到本地几月几日几点、成绩；
 * - 再往下是驾照、教练、补考规则、最近记录、体验版。
 * 还没报名时顶上是报名卡（TA 想学开车的原话在这张纸卡上），教练卡跟在后面。
 * 最上面一张横幅（UI-ASSET-009）只作装饰，标题是页面文字；横幅和各处素材加载失败都退回原来的画法。
 */
import { useState, type ReactNode } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router";
import type { DrivingSchoolStatus, SchoolCurriculum, SessionBrief, SubjectStatus } from "@/shared/contracts";
import { toApiError } from "@/shared/api/errors";
import { useNow } from "@/shared/time/clock";
import { useServices } from "@/shared/services/registry";
import { Button, Card, Chip, DataOriginBadge, Icon, Page, PetAvatar, QueryView, TopBar } from "@/shared/ui";
import { env } from "@/shared/config/env";
import { SCHOOL_ART } from "../assets";
import { useCurriculum, useInvalidateSchool, usePet, useSchoolHistory, useSchoolPetId, useSchoolStatus } from "../hooks";
import { attemptText, formatClock, formatWait, schoolNow, STATE_TEXT, STATE_TONE, SUBJECT_SHORT } from "../text";

/** 素材图：只作装饰（alt=""，旁边的文字已经说了是谁）；加载失败就换回原来的画法（fallback，没有就什么都不画）。 */
function Art({ src, size, className, fallback = null }: { src: string; size: number; className?: string; fallback?: ReactNode }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <>{fallback}</>;
  return <img className={className} src={src} alt="" width={size} height={size} decoding="async" onError={() => setFailed(true)} />;
}

/**
 * 首页横幅：780×320；标题是页面文字，叠在左边安静的天空和草地上（衬一层渐变）；图片加载失败只剩柔和的底色。
 * 只放 780 宽的 webp（宽度描述符 + sizes）：横幅最宽显示 528px，390 宽 2 倍屏按实际显示宽度要的像素不超过 780；
 * 1560 的大图目前只有 1.98MB 的 PNG，先不用，等补来 1560 的 webp 再加回“1560w”。
 */
function Hero() {
  const [failed, setFailed] = useState(false);
  const { hero } = SCHOOL_ART;
  return (
    <div className={`ds-hero${failed ? " ds-hero--plain" : ""}`} data-testid="ds-hero">
      {failed ? null : (
        <img
          className="ds-hero__img"
          src={hero.src}
          srcSet={`${hero.src} ${hero.width}w`}
          sizes="(min-width: 560px) 528px, calc(100vw - 32px)"
          width={hero.width}
          height={hero.height}
          alt=""
          decoding="async"
          onError={() => setFailed(true)}
        />
      )}
      <div className="ds-hero__text">
        <h1 className="ds-hero__title">爪爪驾校</h1>
        <p className="ds-hero__tag">陪 TA 学会开车</p>
      </div>
    </div>
  );
}

/** 原来的龟教练画法（素材加载失败时用）。 */
function TurtleDrawing() {
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true">
      <ellipse cx="22" cy="30" rx="17" ry="12" className="ds-turtle-shell" />
      <circle cx="40" cy="24" r="6" className="ds-turtle-head" />
      <circle cx="42" cy="22" r="1.2" className="ds-turtle-eye" />
    </svg>
  );
}

/**
 * “最近的练习与考试”右边那一句。练习没达标（包括碰了红线：服务端给 passed=false、分数却可能是 100）不写分数，
 * 和成绩单“这次不计分”一个说法；正式考试照常写分数和过没过（红线没过的正式考试这里分不出来，简表里没有原因字段）。
 */
function historyNote(h: SessionBrief): string {
  if (h.state === "running") return "进行中";
  if (h.state === "preparing") return "还没开始";
  if (h.state === "void") return "已作废，不算次数";
  const score = `${h.score ?? "—"} 分`;
  if (h.mode === "practice") return h.passed === false ? "练习没达标，不计分" : h.passed ? `${score} · 练习达标` : score;
  return h.passed === null ? score : `${score} · ${h.passed ? "通过" : "未通过"}`;
}

/** 一科一行：还没报名时只说这一科学什么（报名前不能练习、不能约考）；报名后说状态、机会、冷却到几点、成绩。 */
function subjectDetail(subject: SubjectStatus, enrolled: boolean, now: number): string {
  if (!enrolled) return `${subject.theme} · 报名后开放练习和考试`;
  switch (subject.state) {
    case "passed":
      return subject.legacy ? "旧版驾考已通过" : `${subject.passed_score ?? "—"} 分通过${subject.passed_at ? ` · ${formatClock(subject.passed_at)}` : ""}`;
    case "cooldown": {
      const until = formatClock(subject.cooldown_until);
      return until ? `${until} 后可以再约 · ${formatWait(subject.cooldown_until!, now)}` : "这一轮的两次机会用完了，练习随时可以";
    }
    case "locked":
      return `${subject.unlock_hint ?? "还没解锁"}才能约考 · 上课、练习随时可以`;
    case "in_exam":
      return "有一场正式考试还没考完";
    default:
      return `还剩 ${subject.attempts_left} 次机会 · 下一次是${attemptText(subject.next_attempt)}`;
  }
}

function SubjectLine({ subject, enrolled, now }: { subject: SubjectStatus; enrolled: boolean; now: number }) {
  return (
    <Link to={`/school/subject/${subject.subject}`} className="ds-subject-row">
      <span className="ds-subject-row__no" aria-hidden="true">
        {subject.state === "passed" && enrolled ? <Icon name="check" size={18} /> : SUBJECT_SHORT[subject.subject].slice(2)}
      </span>
      <span className="ds-subject-row__body">
        <strong>
          <span className="visually-hidden">{SUBJECT_SHORT[subject.subject]}：</span>
          {subject.title.split("：")[1] ?? subject.title}
        </strong>
        <span className="ps-muted">{subjectDetail(subject, enrolled, now)}</span>
      </span>
      {enrolled ? <Chip tone={STATE_TONE[subject.state]}>{STATE_TEXT[subject.state]}</Chip> : null}
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
    <Card paper className="ps-stack ds-enroll">
      {/* 纸卡上的小字交给 ui.css 的 .ps-card--paper .ps-muted（纸墨色），不在这里另写颜色 */}
      <p className="ds-now__step ps-muted">第 1 步 · 报名</p>
      <strong className="ps-h2">{status.wish_text ? `${name}想学开车` : `陪${name}学开车`}</strong>
      {status.wish_text ? <p className="ds-quote">“{status.wish_text}”</p> : <p className="ps-muted">以前是你开车带 TA 出门；这一次，你陪 TA 学会开车。</p>}
      <p className="ps-muted">报名后可以上课、不限次数练习；正式考试按科目一到科目四依次解锁。</p>
      <Button variant="primary" block loading={enroll.isPending} onClick={() => enroll.mutate()}>
        陪 {name} 报名爪爪驾校
      </Button>
      {enroll.error ? <p className="ds-error" role="alert">{toApiError(enroll.error).playerMessage}</p> : null}
    </Card>
  );
}

/** 报名以后的“现在 / 下一步”：只有一个主要动作。 */
function NowCard({ status, curriculum, now }: { status: DrivingSchoolStatus; curriculum: SchoolCurriculum | undefined; now: number }) {
  const { name } = usePet();
  const info = schoolNow(status, name, now, curriculum?.cooldown_hours ?? null);
  const action = info.action;
  return (
    <section aria-labelledby="ds-now-title" className={`ps-card ds-now ds-now--${info.tone}`} data-testid="ds-now">
      <p className="ds-now__step">{info.step}</p>
      <h2 id="ds-now-title" className="ds-now__title">
        {info.title}
      </h2>
      {info.detail ? <p className="ds-now__detail">{info.detail}</p> : null}
      {action && action.kind === "link" ? (
        <Link className="ps-btn ps-btn--primary ps-btn--block" to={action.to}>
          {action.label}
        </Link>
      ) : null}
    </section>
  );
}

function LicenseCard({ status }: { status: DrivingSchoolStatus }) {
  const license = status.license!;
  return (
    <Card paper className="ds-license-mini">
      {/* 驾照正面底图（素材只是底，名字、号码都是代码叠上去的）；加载失败就是原来的纸色卡 */}
      <Art src={SCHOOL_ART.license.front} size={SCHOOL_ART.license.width} className="ds-license-mini__art" />
      <div className="ps-row" style={{ justifyContent: "space-between" }}>
        <strong>PetSoul · 爪爪驾驶证</strong>
        <Chip tone="leaf" icon="check">
          已签发
        </Chip>
      </div>
      <div className="ds-license-mini__meta">
        编号 {license.number} · {formatClock(license.issued_at)}
      </div>
      {status.voucher_available ? <div className="ds-license-mini__meta">还有一张驾校借车券：第一次自驾不用租车费。</div> : null}
      {/* 领证仪式还没做时，主要入口在顶上的“现在”卡里，这里不再放第二个主按钮 */}
      {status.ceremony_done ? (
        <Link className="ps-btn ps-btn--secondary ps-btn--block" to="/school/ceremony">
          回看领证仪式
        </Link>
      ) : null}
    </Card>
  );
}

function CoachCard({ status }: { status: DrivingSchoolStatus }) {
  return (
    <Card className="ds-coach">
      <div className="ds-coach__face" aria-hidden="true">
        <Art src={SCHOOL_ART.coach.portrait} size={56} fallback={<TurtleDrawing />} />
      </div>
      <div>
        <strong>{status.coach.name}</strong>
        <p className="ds-quote">“{status.coach.line}”</p>
        <p className="ps-muted">{status.coach.intro}</p>
      </div>
    </Card>
  );
}

function Subjects({ status, enrolled, now }: { status: DrivingSchoolStatus; enrolled: boolean; now: number }) {
  const { pet, name } = usePet();
  const passed = status.subjects.filter((s) => s.state === "passed").length;
  return (
    <section aria-labelledby="ds-subjects">
      <div className="ps-row" style={{ justifyContent: "space-between" }}>
        <h2 id="ds-subjects" className="ps-section-title">
          四个科目 · 已通过 {passed}/4
        </h2>
        {pet ? <PetAvatar petId={pet.pet_id} name={name} species={pet.species} photoUrl={pet.photo_url} size={28} /> : null}
      </div>
      <Card className="ds-subjects">
        {status.subjects.map((s) => (
          <SubjectLine key={s.subject} subject={s} enrolled={enrolled} now={now} />
        ))}
      </Card>
    </section>
  );
}

function Overview({ status, curriculum }: { status: DrivingSchoolStatus; curriculum: SchoolCurriculum | undefined }) {
  const now = useNow(30_000);
  const history = useSchoolHistory();
  const enrolled = status.stage !== "none" && status.stage !== "wish";
  return (
    <div className="ps-stack">
      <Hero />
      {enrolled ? (
        <>
          <NowCard status={status} curriculum={curriculum} now={now} />
          <Subjects status={status} enrolled={enrolled} now={now} />
          {status.license ? <LicenseCard status={status} /> : null}
          <CoachCard status={status} />
        </>
      ) : (
        <>
          {/* 报名卡在教练卡前面：加了横幅以后，320×568 首屏也要看得到“陪 TA 报名”这个主要动作 */}
          <Enroll status={status} />
          <CoachCard status={status} />
          <Subjects status={status} enrolled={enrolled} now={now} />
        </>
      )}

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
                <span className="ps-muted">{historyNote(h)}</span>
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
