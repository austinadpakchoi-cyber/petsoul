/**
 * /school/session/:sessionId（全屏，收起主导航）：考局外壳。
 * - preparing：说明与“开始”按钮——资源加载完成、点开始才计一次考试；
 * - running：科一科四用答题界面，科二科三用驾驶界面；回来时按服务端保存的作答或操作接着来；
 * - 离开：练习直接结束；正式考试可以先离开（考局保留）或放弃（二次确认，计为不通过）。
 */
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import type { InputChunk, SchoolCurriculum, SchoolSession } from "@/shared/contracts";
import { toApiError } from "@/shared/api/errors";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { WorldGate } from "@/features/world_map/WorldGate";
import { Button, Chip, ErrorState, LoadingState, Page } from "@/shared/ui";
import type { DriveBackend } from "../drive/DriveRunner";
import { practiceHints, useCurriculum, useInvalidateSchool, useSchoolPetId, useSchoolStatus } from "../hooks";
import { attemptText, SUBJECT_SHORT } from "../text";

// 驾驶和答题按考局类型分开按需加载（巡检第 5 批：进驾驶考局也会下载答题组件）；加载中留在考局底色上显示过渡，不闪白。
const DriveRunner = lazy(() => import("../drive/DriveRunner").then((m) => ({ default: m.DriveRunner })));
const QuizRunner = lazy(() => import("../quiz/QuizRunner").then((m) => ({ default: m.QuizRunner })));

function RunnerLoading() {
  return (
    <div className="ds-exam ds-exam--loading">
      <LoadingState label="正在进入考场…" />
    </div>
  );
}

const VOID_TEXT: Record<string, string> = {
  not_started: "建立后一小时内没有开始，这场考局已经作废，不计次。",
  platform_fault: "考场出了故障，这场考局已经作废，不计次。",
  abandoned: "这次练习已经结束。",
  replaced: "这次练习已经被新的练习替换。",
};

/**
 * 练习按这一局实际的内容说明（题数、通过线、练哪几项），不照搬正式考试的“10 道题 / 三项连考”。
 * 算法与服务端判分一致（grading.py）：答题每题 10 分，达标线＝科目通过线 × 实际满分 ÷ 100（向下取整）；驾驶满分 100。
 */
export function practiceSummary(session: SchoolSession): string {
  if (session.quiz) {
    const count = session.quiz.questions.length;
    const max = count * 10;
    const pass = Math.floor((session.pass_score * max) / 100);
    return `这一局练习 ${count} 道题，每题 10 分，达到 ${pass} 分（满分 ${max}）算练习达标；每答一题马上讲解，不计成绩。`;
  }
  const items = session.drive?.items ?? [];
  if (items.length === 1) return `这一局只练「${items[0].title}」：完成这一项、达到 ${session.pass_score} 分算练习达标，不计成绩。`;
  return `这一局连着练 ${items.map((it) => `「${it.title}」`).join("")}：${items.length} 项都完成、综合达到 ${session.pass_score} 分算练习达标，不计成绩。`;
}

/** 出错的那一行：写在按钮下面、读屏会念（role=alert）；矮屏上按钮常在首屏最下面，出错后把这一行滚进视野 */
function PrepareError({ text }: { text: string | null }) {
  const ref = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (text) ref.current?.scrollIntoView?.({ block: "nearest" });
  }, [text]);
  return text ? (
    <p className="ds-error" role="alert" ref={ref}>
      {text}
    </p>
  ) : null;
}

function Prepare({
  session,
  curriculum,
  onBegin,
  onLeave,
  busy,
  beginError,
  leaveError,
}: {
  session: SchoolSession;
  curriculum: SchoolCurriculum;
  onBegin: () => void;
  onLeave: () => void;
  busy: boolean;
  /** “开始”没成功：给玩家看的一句（写在“开始”按钮下面） */
  beginError: string | null;
  /** “不练了 / 先不考了”没成功：写在那颗按钮下面 */
  leaveError: string | null;
}) {
  const [ready, setReady] = useState(false);
  const info = curriculum.subjects.find((s) => s.subject === session.subject)!;
  useEffect(() => {
    let alive = true;
    // 考场资源：题目或场地配置已经随考局下发；等字体就绪再允许开始（避免开考后画面跳动）。
    const fonts = (document as Document & { fonts?: { ready: Promise<unknown> } }).fonts;
    const ok = session.quiz ? session.quiz.questions.length > 0 : !!session.drive?.items.length;
    void Promise.race([fonts?.ready ?? Promise.resolve(), new Promise((r) => setTimeout(r, 1500))]).then(() => alive && setReady(ok));
    return () => {
      alive = false;
    };
  }, [session]);
  const formal = session.mode === "formal";
  return (
    <Page bare className="ds-prepare">
      <div className="ps-stack">
        <Chip tone={formal ? "sun" : "leaf"}>{formal ? `正式考试 · 本轮${attemptText(session.attempt_kind)}` : "练习 · 不计成绩"}</Chip>
        <h1 className="ps-h1">{session.title}</h1>
        <p className="ps-muted">{formal ? `${info.format}。${info.pass_rule}。` : practiceSummary(session)}</p>
        {info.red_lines.length ? (
          <div className="ds-redlines">
            <strong>{formal ? "红线（自动制动，本次不通过）" : "红线（自动制动，这一局练习到此结束）"}</strong>
            <ul className="ds-list">
              {info.red_lines.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {/* 规格 §4.3：扣分项和红线都要在开考前列出来（数据用课程里现成的 deductions，不另写） */}
        {info.deductions.length ? (
          <section className="ds-prepare__deductions" aria-labelledby="ds-prepare-deductions">
            <strong id="ds-prepare-deductions">扣分项</strong>
            <ul className="ds-list ds-deduction-list">
              {info.deductions.map((d) => (
                <li key={d.label}>
                  <span>{d.label}</span>
                  <span className="ds-prepare__points">−{d.points}</span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        {info.kind === "drive" ? (
          <ul className="ds-list ps-muted">
            {curriculum.controls.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        ) : null}
        <p className="ps-muted" role="status">
          {ready ? "考场已经准备好。" : "正在准备考场…"}
          {formal ? "点“开始考试”后才算一次考试；中途断线可以回来接着考。" : ""}
        </p>
        <Button variant="primary" block disabled={!ready} loading={busy} onClick={onBegin}>
          {formal ? "开始考试" : "开始练习"}
        </Button>
        <PrepareError text={beginError} />
        <Button variant="ghost" block onClick={onLeave}>
          {formal ? "先不考了（不计次）" : "不练了"}
        </Button>
        <PrepareError text={leaveError} />
      </div>
    </Page>
  );
}

function ExitDialog({ session, onStay, onLeave, onAbandon, busy, error }: { session: SchoolSession; onStay: () => void; onLeave: () => void; onAbandon: () => void; busy: boolean; error: string | null }) {
  const [confirm, setConfirm] = useState(false);
  const practice = session.mode === "practice";
  // 键盘：Esc 等于“回去接着考 / 接着练”；会结束或放弃的那一步，焦点落在“回去 / 接着练”上（误按回车也不会放弃），
  // 只有“先离开，回来接着考”（考局保留）这一步焦点落在主按钮上
  useEffect(() => {
    if (practice || confirm) document.querySelector<HTMLButtonElement>(".ds-overlay--page [data-stay]")?.focus();
  }, [practice, confirm]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onStay();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onStay]);
  return (
    <div className="ds-overlay ds-overlay--page">
      <div className="ds-overlay__card" role="alertdialog" aria-label={practice ? "结束练习" : "离开考场"}>
        {practice ? (
          <>
            <strong className="ps-h2">结束这次练习？</strong>
            <p className="ps-muted">练习不计成绩，想练随时再来。</p>
            <Button variant="primary" block loading={busy} onClick={onAbandon}>
              结束练习
            </Button>
          </>
        ) : !confirm ? (
          <>
            <strong className="ps-h2">要离开考场吗？</strong>
            <p className="ps-muted">先离开：这场考试会保留，已经保存的作答、操作和扣分都在，回来接着考。</p>
            <Button variant="primary" block autoFocus onClick={onLeave}>
              先离开，回来接着考
            </Button>
            <Button variant="danger" block onClick={() => setConfirm(true)}>
              放弃这场考试
            </Button>
          </>
        ) : (
          <>
            <strong className="ps-h2">确定放弃吗？</strong>
            <p className="ps-muted">
              放弃会计为本轮{attemptText(session.attempt_kind)}没通过
              {session.attempt_kind === "retake" ? "；这是本轮最后一次机会，放弃后这一科要等 7 天才能再约考试" : "，还剩一次补考机会"}。
            </p>
            <Button variant="danger" block loading={busy} onClick={onAbandon}>
              确定放弃
            </Button>
          </>
        )}
        {error ? (
          <p className="ds-error" role="alert">
            {error}
          </p>
        ) : null}
        <Button variant="ghost" block data-stay="" onClick={onStay}>
          {practice ? "接着练" : "回去接着考"}
        </Button>
      </div>
    </div>
  );
}

/**
 * 全屏页（bareRoutes）不在主布局里，没有家庭上下文：用 WorldGate 套一层（与“我的”等全屏页同一个守卫），
 * 才知道当前是哪只宠物——一家有两只时，考局与领证的每条请求都要带上它（否则 409 pet_required）。
 */
export function SessionPage() {
  return (
    <WorldGate>
      <SessionBody />
    </WorldGate>
  );
}

function SessionBody() {
  const { sessionId = "" } = useParams();
  const { driving } = useServices();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const invalidate = useInvalidateSchool();
  const curriculum = useCurriculum();
  const status = useSchoolStatus();
  // 考局按宠物分：一家有两只时每条都要带上是哪一只（否则 409 pet_required）。
  const petId = useSchoolPetId();
  const [exiting, setExiting] = useState(false);
  const [voidMessage, setVoidMessage] = useState<string | null>(null);
  const query = useQuery({ queryKey: queryKeys.drivingSession(sessionId), queryFn: () => driving.session(sessionId, petId), refetchOnWindowFocus: false, staleTime: Infinity });
  const put = (session: SchoolSession) => queryClient.setQueryData(queryKeys.drivingSession(sessionId), session);
  // 结算后先取回已结算的考局再进成绩页，成绩页直接显示服务端结果。
  const toResult = async () => {
    try {
      put(await driving.session(sessionId, petId));
    } catch {
      /* 取不到也照常跳转，成绩页会自己重试 */
    }
    invalidate();
    navigate(`/school/result/${sessionId}`, { replace: true });
  };
  const begin = useMutation({
    mutationFn: () => driving.begin(sessionId, petId),
    onSuccess: (s) => {
      put(s);
      invalidate();
    },
  });
  const abandon = useMutation({
    mutationFn: () => driving.abandon(sessionId, true, petId),
    onSuccess: (s) => {
      put(s);
      invalidate();
      setExiting(false);
      if (s.state === "settled") navigate(`/school/result/${sessionId}`, { replace: true });
      else navigate(`/school/subject/${s.subject}`, { replace: true });
    },
  });
  const backend = useMemo<DriveBackend>(
    () => ({
      upload: (chunk: InputChunk) => driving.inputs(sessionId, chunk, petId),
      pause: () => driving.pause(sessionId, petId),
      reload: async () => {
        const fresh = await driving.session(sessionId, petId);
        queryClient.setQueryData(queryKeys.drivingSession(sessionId), fresh);
        return fresh;
      },
    }),
    [driving, queryClient, sessionId, petId],
  );
  const hints = useMemo(() => practiceHints(curriculum.data), [curriculum.data]);
  // TA 的台词按 DNA 行为画像的性格选（服务端给出 temperament），只影响话语，不影响成绩。
  const temperament = status.data?.temperament ?? "steady";
  const petLines = useMemo(() => curriculum.data?.pet_lines[temperament] ?? {}, [curriculum.data, temperament]);

  if (query.isPending || curriculum.isPending) {
    return (
      <Page bare>
        <LoadingState label="正在进入考场…" />
      </Page>
    );
  }
  if (query.isError || curriculum.isError) {
    return (
      <Page bare>
        <ErrorState error={query.error ?? curriculum.error} onRetry={() => void query.refetch()} />
        <Link className="ps-btn ps-btn--ghost ps-btn--block" to="/school">
          回驾校
        </Link>
      </Page>
    );
  }
  const session = query.data;
  if (session.state === "settled") return <Navigate to={`/school/result/${sessionId}`} replace />;
  if (voidMessage || session.state === "void") {
    return (
      <Page bare className="ds-prepare">
        <div className="ps-stack">
          <h1 className="ps-h1">{session.title}</h1>
          <p>{voidMessage ?? VOID_TEXT[session.void_reason ?? ""] ?? "这场考局已经结束，不计次。"}</p>
          <Link className="ps-btn ps-btn--primary ps-btn--block" to={`/school/subject/${session.subject}`}>
            回到{SUBJECT_SHORT[session.subject]}
          </Link>
        </div>
      </Page>
    );
  }
  const practice = session.mode === "practice";
  const exitDialog = exiting ? (
    <ExitDialog
      session={session}
      busy={abandon.isPending}
      error={abandon.error ? toApiError(abandon.error).playerMessage : null}
      onStay={() => setExiting(false)}
      onLeave={() => {
        invalidate();
        navigate(`/school/subject/${session.subject}`);
      }}
      onAbandon={() => abandon.mutate()}
    />
  ) : null;

  if (session.state === "preparing") {
    // 出错的那一行放进准备页、写在对应按钮下面（原来画在准备页外面，贴着屏幕左下角；“不练了”失败时哪里都不显示）
    return (
      <Prepare
        session={session}
        curriculum={curriculum.data}
        busy={begin.isPending || abandon.isPending}
        onBegin={() => begin.mutate()}
        onLeave={() => abandon.mutate()}
        beginError={begin.error ? toApiError(begin.error).playerMessage : null}
        leaveError={abandon.error ? toApiError(abandon.error).playerMessage : null}
      />
    );
  }

  const labels = curriculum.data.reasons;
  return (
    <div className="ds-session">
      <Suspense fallback={<RunnerLoading />}>
      {session.quiz ? (
        <QuizRunner
          session={session}
          practice={practice}
          exitLabel={practice ? "结束" : "离开"}
          onExit={() => setExiting(true)}
          onAnswer={(body) => driving.answer(sessionId, body, petId)}
          onSubmit={async () => {
            put(await driving.submit(sessionId, petId));
            invalidate();
            navigate(`/school/result/${sessionId}`, { replace: true });
          }}
        />
      ) : (
        <DriveRunner
          title={`${SUBJECT_SHORT[session.subject]} · ${practice ? "练习" : attemptText(session.attempt_kind)}`}
          items={session.drive!.items}
          startIndex={session.drive!.current_item}
          practice={practice}
          reasons={labels}
          petLines={petLines}
          hints={hints}
          backend={backend}
          exitLabel={practice ? "结束练习" : "离开考场"}
          onExit={() => setExiting(true)}
          onFinished={() => void toResult()}
          onVoid={(message) => {
            invalidate();
            setVoidMessage(message);
          }}
        />
      )}
      </Suspense>
      {exitDialog}
    </div>
  );
}
