/**
 * /school/session/:sessionId（全屏，收起主导航）：考局外壳。
 * - preparing：说明与“开始”按钮——资源加载完成、点开始才计一次考试；
 * - running：科一科四用答题界面，科二科三用驾驶界面；回来时按服务端保存的作答或操作接着来；
 * - 离开：练习直接结束；正式考试可以先离开（考局保留）或放弃（二次确认，计为不通过）。
 */
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import type { InputChunk, SchoolCurriculum, SchoolSession } from "@/shared/contracts";
import { toApiError } from "@/shared/api/errors";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { Button, Chip, ErrorState, LoadingState, Page } from "@/shared/ui";
import { type DriveBackend, DriveRunner } from "../drive/DriveRunner";
import { practiceHints, useCurriculum, useInvalidateSchool, useSchoolStatus } from "../hooks";
import { QuizRunner } from "../quiz/QuizRunner";
import { attemptText, SUBJECT_SHORT } from "../text";

const VOID_TEXT: Record<string, string> = {
  not_started: "建立后一小时内没有开始，这场考局已经作废，不计次。",
  platform_fault: "考场出了故障，这场考局已经作废，不计次。",
  abandoned: "这次练习已经结束。",
  replaced: "这次练习已经被新的练习替换。",
};

function Prepare({ session, curriculum, onBegin, onLeave, busy }: { session: SchoolSession; curriculum: SchoolCurriculum; onBegin: () => void; onLeave: () => void; busy: boolean }) {
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
        <p className="ps-muted">
          {info.format}。{info.pass_rule}。
        </p>
        {info.red_lines.length ? (
          <div className="ds-redlines">
            <strong>红线（自动制动，本次不通过）</strong>
            <ul className="ds-list">
              {info.red_lines.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </div>
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
        <Button variant="ghost" block onClick={onLeave}>
          {formal ? "先不考了（不计次）" : "不练了"}
        </Button>
      </div>
    </Page>
  );
}

function ExitDialog({ session, onStay, onLeave, onAbandon, busy, error }: { session: SchoolSession; onStay: () => void; onLeave: () => void; onAbandon: () => void; busy: boolean; error: string | null }) {
  const [confirm, setConfirm] = useState(false);
  const practice = session.mode === "practice";
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
            <p className="ps-muted">先离开：考局保留，已经保存的作答、操作和扣分都在，回来接着考。</p>
            <Button variant="primary" block onClick={onLeave}>
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
        <Button variant="ghost" block onClick={onStay}>
          {practice ? "接着练" : "回去接着考"}
        </Button>
      </div>
    </div>
  );
}

export function SessionPage() {
  const { sessionId = "" } = useParams();
  const { driving } = useServices();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const invalidate = useInvalidateSchool();
  const curriculum = useCurriculum();
  const status = useSchoolStatus();
  const [exiting, setExiting] = useState(false);
  const [voidMessage, setVoidMessage] = useState<string | null>(null);
  const query = useQuery({ queryKey: queryKeys.drivingSession(sessionId), queryFn: () => driving.session(sessionId), refetchOnWindowFocus: false, staleTime: Infinity });
  const put = (session: SchoolSession) => queryClient.setQueryData(queryKeys.drivingSession(sessionId), session);
  // 结算后先取回已结算的考局再进成绩页，成绩页直接显示服务端结果。
  const toResult = async () => {
    try {
      put(await driving.session(sessionId));
    } catch {
      /* 取不到也照常跳转，成绩页会自己重试 */
    }
    invalidate();
    navigate(`/school/result/${sessionId}`, { replace: true });
  };
  const begin = useMutation({
    mutationFn: () => driving.begin(sessionId),
    onSuccess: (s) => {
      put(s);
      invalidate();
    },
  });
  const abandon = useMutation({
    mutationFn: () => driving.abandon(sessionId, true),
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
      upload: (chunk: InputChunk) => driving.inputs(sessionId, chunk),
      pause: () => driving.pause(sessionId),
      reload: async () => {
        const fresh = await driving.session(sessionId);
        queryClient.setQueryData(queryKeys.drivingSession(sessionId), fresh);
        return fresh;
      },
    }),
    [driving, queryClient, sessionId],
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
      error={abandon.error ? toApiError(abandon.error).message : null}
      onStay={() => setExiting(false)}
      onLeave={() => {
        invalidate();
        navigate(`/school/subject/${session.subject}`);
      }}
      onAbandon={() => abandon.mutate()}
    />
  ) : null;

  if (session.state === "preparing") {
    return (
      <>
        <Prepare session={session} curriculum={curriculum.data} busy={begin.isPending || abandon.isPending} onBegin={() => begin.mutate()} onLeave={() => abandon.mutate()} />
        {begin.error ? (
          <p className="ds-error" role="alert">
            {toApiError(begin.error).message}
          </p>
        ) : null}
      </>
    );
  }

  const labels = curriculum.data.reasons;
  return (
    <div className="ds-session">
      {session.quiz ? (
        <QuizRunner
          session={session}
          practice={practice}
          exitLabel={practice ? "结束" : "离开"}
          onExit={() => setExiting(true)}
          onAnswer={(body) => driving.answer(sessionId, body)}
          onSubmit={async () => {
            put(await driving.submit(sessionId));
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
      {exitDialog}
    </div>
  );
}
