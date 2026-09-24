import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";
import type { CandidateKind, CareNoteDecision, IntakeCandidate, IntakeConfirmationResult, MemoryPurpose, SaveTarget, SessionState } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { toApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { onboardingRoute, useSessionState } from "@/shared/session/onboarding";
import { Button, Card, Chip, DataOriginBadge, ErrorState, Icon, LoadingState, Page, TopBar } from "@/shared/ui";
import { EntryHeading, entryStepKicker } from "@/features/identity/EntryHeading";
import { fixtureReceptionControls } from "./service";
import { leaveSupplement, notesTrail, SUPPLEMENT_PARENT, type NotesTrail } from "./trail";
import receptionWorld from "./assets/reception-world-v1.webp";
import "./reception.css";

/** 普通左键点击才由页面接管（修饰键 / 中键交给浏览器按链接地址打开），与 TopBar 的返回一致。 */
function plainClick(event: MouseEvent): boolean {
  return !event.defaultPrevented && event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
}

const KIND_TEXT: Record<CandidateKind, string> = {
  habit: "习惯",
  shared_story: "共同经历",
  wish: "愿望",
  letter: "想对 TA 说",
  owner_private: "你的心里话",
  inference: "推测（需要你确认）",
};

const TARGET_TEXT: Record<SaveTarget, string> = { give_to_pet: "交给 TA", keep_here: "只留在这里", do_not_save: "不保存" };

const PURPOSE_TEXT: Record<MemoryPurpose, string> = {
  private_chat: "私人通讯",
  home_interaction: "家里的互动",
  travel_preference: "旅行偏好",
  food_preference_pet: "TA 的口味",
  public_story: "公开故事（默认不选）",
  media_generation: "生成照片（默认不选）",
};

/** 私人倾诉与模型推测永远不能“交给 TA”。 */
function allowedTargets(kind: CandidateKind): SaveTarget[] {
  return kind === "owner_private" || kind === "inference" ? ["keep_here", "do_not_save"] : ["give_to_pet", "keep_here", "do_not_save"];
}

function defaultDecision(c: IntakeCandidate): Partial<CareNoteDecision> & { candidate_id: string; text: string } {
  const base = { candidate_id: c.candidate_id, text: c.text, slot: c.suggested_slot, slot_value: c.suggested_slot_value };
  if (c.kind === "owner_private") return { ...base, target: "keep_here", purposes: [] };
  if (c.kind === "inference") return { ...base, target: "do_not_save", purposes: [] };
  const purposes: MemoryPurpose[] = c.suggested_slot === "wish_place" || c.suggested_slot === "travel_mood" ? ["travel_preference"] : ["home_interaction", "private_chat"];
  return { ...base, purposes }; // target 留空：普通习惯也要主人逐项选择
}

type Draft = ReturnType<typeof defaultDecision>;

function NoteCard({ candidate, draft, onChange }: { candidate: IntakeCandidate; draft: Draft; onChange: (d: Draft) => void }) {
  const [showSource, setShowSource] = useState(false);
  return (
    <Card paper className="ps-note" data-testid={`note-${candidate.candidate_id}`}>
      <div className="ps-row" style={{ justifyContent: "space-between" }}>
        <Chip>{KIND_TEXT[candidate.kind]}</Chip>
        <button type="button" className="ps-btn ps-btn--ghost ps-btn--sm" onClick={() => setShowSource((v) => !v)} aria-expanded={showSource}>
          原话
        </button>
      </div>
      {showSource ? <blockquote className="ps-note__source">“{candidate.source_excerpt}”</blockquote> : null}
      <label className="visually-hidden" htmlFor={`note-text-${candidate.candidate_id}`}>
        便笺内容
      </label>
      <textarea id={`note-text-${candidate.candidate_id}`} className="ps-textarea ps-note__text" value={draft.text} maxLength={500} onChange={(e) => onChange({ ...draft, text: e.target.value })} />
      <div className="ps-note__targets" role="radiogroup" aria-label="这条怎么处理">
        {(["give_to_pet", "keep_here", "do_not_save"] as SaveTarget[]).map((t) => {
          const allowed = allowedTargets(candidate.kind).includes(t);
          return (
            <button key={t} type="button" role="radio" aria-checked={draft.target === t} disabled={!allowed} className="ps-chip" aria-pressed={draft.target === t} onClick={() => onChange({ ...draft, target: t })}>
              {TARGET_TEXT[t]}
            </button>
          );
        })}
      </div>
      {candidate.kind === "owner_private" ? (
        <p className="ps-note__hint">
          <Icon name="lock" size={12} /> 这是你的心里话，不会交给 TA、其他角色、寻味或任何公开内容。
        </p>
      ) : null}
      {candidate.kind === "inference" ? <p className="ps-note__hint">这是整理时的推测，不会当成事实；想保留请改写成你确认的话，作为新的一条交代。</p> : null}
      {draft.target === "give_to_pet" ? (
        <fieldset className="ps-note__purposes">
          <legend>TA 会在这些地方记着</legend>
          {(Object.keys(PURPOSE_TEXT) as MemoryPurpose[]).map((p) => (
            <label key={p} className="ps-note__purpose">
              <input
                type="checkbox"
                checked={draft.purposes?.includes(p) ?? false}
                onChange={(e) => onChange({ ...draft, purposes: e.target.checked ? [...(draft.purposes ?? []), p] : (draft.purposes ?? []).filter((x) => x !== p) })}
              />
              {PURPOSE_TEXT[p]}
            </label>
          ))}
        </fieldset>
      ) : null}
    </Card>
  );
}

/** 保存结果只讲去向；确认编号只留给排查（data 属性），不作为给主人看的文案。 */
function Saved({ result, trail }: { result: IntakeConfirmationResult; trail: NotesTrail | null }) {
  const navigate = useNavigate();
  const given = result.notes.filter((n) => n.target === "give_to_pet").length;
  const kept = result.notes.filter((n) => n.target === "keep_here").length;
  const persisted = result.persist_state === "persisted";
  const home = result.onboarding.step === "active";
  // 已入住后再来补充的叮嘱（live 才分得出来）存好后离开补充流程：站内有来路就回来路（从通讯器来回通讯器），
  // 直接打开时回上级页“我的”（链接地址也是它）；入住中照旧按入住阶段去入住；演示模式的保存结果总是“已入住”，按入住阶段回地图首页。
  const supplementDone = home && env.dataMode === "live";
  const next = supplementDone ? SUPPLEMENT_PARENT : onboardingRoute(result.onboarding);
  const backSteps = supplementDone ? trail?.leaveSteps ?? 0 : 0;
  const onDone = (event: MouseEvent) => {
    if (backSteps <= 0 || !plainClick(event)) return;
    event.preventDefault();
    leaveSupplement(navigate, backSteps);
  };
  return (
    <section className={`ps-notes-saved${persisted ? "" : " is-failed"}`} role="status" data-confirmation-id={result.confirmation_id}>
      <span className="ps-notes-saved__seal" aria-hidden="true"><Icon name={persisted ? "check" : "alert"} size={22} /></span>
      <h2>{persisted ? "记下了" : "这次没有保存成功"}</h2>
      {/* 失败说明与下面按钮同一套条件：入住中“先去入住”，补充叮嘱回“我的”，演示回地图。
          契约允许 persist_state = failed，但目前后端只回 persisted、演示的保存失败直接报错，这个分支暂时走不到。 */}
      <p>{persisted ? `交给 TA ${given} 条 · 只留在这里 ${kept} 条。以后还能在“我的”里补充。` : `便笺没有写进去。可以回到接待再试一次，或${!home ? "先去入住" : env.dataMode === "live" ? "先回“我的”" : "先回地图"}。`}</p>
      <DataOriginBadge origin={result.data_origin} label={result.data_origin === "fixture" ? "演示：只保存在本浏览器标签页，不是服务器保存" : undefined} />
      <Link className="ps-btn ps-btn--primary ps-btn--block" to={next} onClick={onDone}>
        {/* 文字跟着去向走：补充叮嘱存好就是“完成”（回来路或“我的”）；演示模式回地图首页；入住中照旧“带 TA 去新家”。 */}
        {home ? (env.dataMode === "live" ? "完成" : "回地图") : "带 TA 去新家"}
      </Link>
    </section>
  );
}

/** 一句都没交代时：不给一个永远点不了的确认按钮，而是给两条真实出路。 */
function NothingToConfirm({ sessionId, trail }: { sessionId: string; trail: NotesTrail | null }) {
  const { reception } = useServices();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const account = useSessionState();
  const active = account.data?.onboarding?.step === "active";
  const skip = useMutation({
    mutationFn: () => reception.skip(sessionId),
    onSuccess: async () => {
      // 已入住后来补充叮嘱：离开补充流程——站内有来路就回来路，直接打开时回“我的”；演示模式回地图首页；入住中照旧去入住。
      if (active) return leaveSupplement(navigate, trail?.leaveSteps ?? 0);
      if (env.dataMode !== "live") return navigate("/map");
      await queryClient.invalidateQueries({ queryKey: queryKeys.session });
      navigate("/onboarding/move-in");
    },
  });
  // 从接待页点“整理”来的：回接待就是退一步，不再压一页新的接待。
  const backToReception = (event: MouseEvent) => {
    if (!trail || !plainClick(event)) return;
    event.preventDefault();
    void navigate(-1);
  };
  return (
    <section className="ps-notes-empty">
      <span className="ps-notes-empty__icon" aria-hidden="true"><Icon name="bookmark" size={22} /></span>
      <h2>还没有要确认的叮嘱</h2>
      <p>在接待那里说一件关于 TA 的小事，这里就会出现一条待你确认的便笺。不说也完全可以。</p>
      <div className="ps-notes-empty__actions">
        <Link className="ps-btn ps-btn--secondary ps-btn--block" to={active ? "/onboarding/reception?mode=supplement" : "/onboarding/reception"} onClick={backToReception}>回到接待说一件小事</Link>
        <Button variant="primary" block icon={active ? "back" : env.dataMode === "live" ? "home" : "pin"} loading={skip.isPending} onClick={() => skip.mutate()}>{active ? "先回去" : env.dataMode === "live" ? "先去入住" : "先去地图看看"}</Button>
      </div>
      {skip.isError ? <p role="alert" className="ps-form-error"><strong>这一步没能完成，可以再点一次。</strong> {toApiError(skip.error).message}</p> : null}
    </section>
  );
}

export function CareNotesPage() {
  const { reception } = useServices();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const account = useSessionState();
  const trail = notesTrail(location);
  // 已入住后来补充（live 才分得出来）：不再写“入住准备 · 03 / 04”和四站步骤条。
  const supplement = env.dataMode === "live" && account.data?.onboarding?.step === "active";
  const sessionId = params.get("session") ?? "";
  const session = useQuery({ queryKey: queryKeys.reception(sessionId), queryFn: () => reception.get(sessionId), enabled: Boolean(sessionId) });
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [failNext, setFailNext] = useState(false);
  const keyRef = useRef(newIdempotencyKey("reception-confirm"));

  useEffect(() => {
    if (session.data) setDrafts((prev) => Object.fromEntries(session.data.candidates.map((c) => [c.candidate_id, prev[c.candidate_id] ?? defaultDecision(c)])));
  }, [session.data]);

  const decisions = useMemo(() => Object.values(drafts), [drafts]);
  const undecided = decisions.filter((d) => !d.target || !d.text.trim()).length;
  const missingPurpose = decisions.filter((d) => d.target === "give_to_pet" && (d.purposes?.length ?? 0) === 0).length;
  const ready = decisions.length > 0 && undecided === 0 && missingPurpose === 0;

  const confirm = useMutation({
    mutationFn: () => {
      fixtureReceptionControls.failNextSave = failNext;
      return reception.confirm(
        { session_id: sessionId, draft_revision: session.data!.draft_revision, decisions: decisions.map((d) => ({ candidate_id: d.candidate_id, text: d.text.trim(), target: d.target as SaveTarget, purposes: d.purposes ?? [], slot: d.slot ?? null, slot_value: d.slot_value ?? null })) },
        keyRef.current,
      );
    },
    onSuccess: (result) => {
      // 跨模块失效：确认后刷新家园快照（HomeWelcome 同一版本）与入住阶段。
      void queryClient.invalidateQueries({ queryKey: queryKeys.home });
      queryClient.setQueryData<SessionState | undefined>(queryKeys.session, (prev) => (prev ? { ...prev, onboarding: result.onboarding } : prev));
      setFailNext(false);
    },
    // 演示开关只作用于“下一次”保存；失败后重试沿用同一个幂等键。
    onError: () => setFailNext(false),
  });

  const empty = Boolean(session.data && session.data.candidates.length === 0);
  return (
    <Page bare className="ps-entry-page ps-notes-page">
      <TopBar title="生活叮嘱" subtitle="这样记对吗？每一条都由你决定" back={`/onboarding/reception${session.data?.branch === "adopted" ? "?branch=adopted" : ""}`} />
      <div className="ps-notes-band" aria-hidden="true"><img src={receptionWorld} alt="" /></div>
      <EntryHeading step={supplement ? undefined : 3} kicker={supplement ? "再记下几件小事" : entryStepKicker(3)} title="把重要的小事记下来" description="这页只写你确认过的话；每条便笺的去向与用途都可单独决定。" />
      {!sessionId ? (
        <ErrorState error={toApiError(new Error("缺少接待会话"))} />
      ) : session.isError ? (
        <ErrorState error={session.error} onRetry={() => void session.refetch()} />
      ) : !session.data ? (
        <LoadingState lines={3} />
      ) : confirm.data ? (
        <Saved result={confirm.data} trail={trail} />
      ) : empty ? (
        <NothingToConfirm sessionId={sessionId} trail={trail} />
      ) : (
        <>
          <div className="ps-stack">
            <p className="ps-notes-legend">
              <span><strong>交给 TA</strong> 只按你勾的用途使用，默认不公开</span>
              <span><strong>只留在这里</strong> 只有你和接待员看得到</span>
              <span><strong>不保存</strong> 会被移除，不会再被整理回来</span>
            </p>
            {session.data.candidates.map((c) =>
              drafts[c.candidate_id] ? <NoteCard key={c.candidate_id} candidate={c} draft={drafts[c.candidate_id]} onChange={(d) => setDrafts((prev) => ({ ...prev, [c.candidate_id]: d }))} /> : null,
            )}
            {confirm.isError ? (
              <Card className="ps-save-error" role="alert">
                <strong>{toApiError(confirm.error).code === "VERSION_CONFLICT" ? "便笺在别处更新过" : "保存没有成功"}</strong>
                <div className="ps-muted">{toApiError(confirm.error).message} 你的修改都还在，可以直接重试。</div>
              </Card>
            ) : null}
            {env.dataMode === "fixture" ? (
              <label className="ps-row ps-muted">
                <input type="checkbox" checked={failNext} onChange={(e) => setFailNext(e.target.checked)} /> 演示：下一次保存失败
              </label>
            ) : null}
          </div>
          <div className="ps-entry-dock" role="group" aria-label="确认叮嘱">
            {!ready ? (
              <p className="ps-entry-dock__hint" aria-live="polite">
                {undecided > 0 ? `还有 ${undecided} 条没选怎么处理。` : `“交给 TA”的 ${missingPurpose} 条至少勾一个用途。`}
              </p>
            ) : null}
            <Button variant="primary" block icon="check" disabled={!ready} loading={confirm.isPending} onClick={() => confirm.mutate()}>
              这样记就对了
            </Button>
            {/* 从接待页点“整理”来的：回接待是退一步，不再压一页新的接待（否则接待页的“先回去”会退回这里）。 */}
            <Button variant="ghost" block onClick={() => (env.dataMode !== "live" ? navigate("/map") : trail ? navigate(-1) : navigate("/onboarding/reception"))}>
              {env.dataMode === "live" ? "回到接待" : "先去地图看看"}
            </Button>
          </div>
        </>
      )}
    </Page>
  );
}
