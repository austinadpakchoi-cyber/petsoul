import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router";
import type { CandidateKind, CareNoteDecision, IntakeCandidate, IntakeConfirmationResult, MemoryPurpose, SaveTarget, SessionState } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { toApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { onboardingRoute } from "@/shared/session/onboarding";
import { Button, Card, Chip, DataOriginBadge, ErrorState, Icon, LoadingState, Page, TopBar } from "@/shared/ui";
import { EntryHeading } from "@/features/identity/EntryHeading";
import { fixtureReceptionControls } from "./service";
import "./reception.css";

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
        <div className="ps-note__purposes" aria-label="用在哪里">
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
        </div>
      ) : null}
    </Card>
  );
}

function Saved({ result }: { result: IntakeConfirmationResult }) {
  const given = result.notes.filter((n) => n.target === "give_to_pet").length;
  const kept = result.notes.filter((n) => n.target === "keep_here").length;
  return (
    <Card className="ps-stack" role="status">
      <div className="ps-row">
        <Icon name="check" />
        <strong>{result.persist_state === "persisted" ? "已保存" : "没有保存成功"}</strong>
      </div>
      <p style={{ margin: 0 }}>
        交给 TA {given} 条 · 只留在这里 {kept} 条。确认编号 {result.confirmation_id}。
      </p>
      <DataOriginBadge origin={result.data_origin} label={result.data_origin === "fixture" ? "演示：只保存在本浏览器标签页，不是服务器保存" : undefined} />
      <Link className="ps-btn ps-btn--primary" to={onboardingRoute(result.onboarding)}>
        {result.onboarding.step === "active" ? "回到家" : "去入住"}
      </Link>
    </Card>
  );
}

export function CareNotesPage() {
  const { reception } = useServices();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const sessionId = params.get("session") ?? "";
  const session = useQuery({ queryKey: queryKeys.reception(sessionId), queryFn: () => reception.get(sessionId), enabled: Boolean(sessionId) });
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [failNext, setFailNext] = useState(false);
  const keyRef = useRef(newIdempotencyKey("reception-confirm"));

  useEffect(() => {
    if (session.data) setDrafts((prev) => Object.fromEntries(session.data.candidates.map((c) => [c.candidate_id, prev[c.candidate_id] ?? defaultDecision(c)])));
  }, [session.data]);

  const decisions = useMemo(() => Object.values(drafts), [drafts]);
  const ready = decisions.length > 0 && decisions.every((d) => d.target && d.text.trim() && (d.target !== "give_to_pet" || (d.purposes?.length ?? 0) > 0));

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

  return (
    <Page bare className="ps-entry-page">
      <TopBar title="入住叮嘱" subtitle="这样记对吗？每一条都由你决定" back={`/onboarding/reception${session.data?.branch === "adopted" ? "?branch=adopted" : ""}`} />
      <EntryHeading step={3} kicker="入住准备 · 03 / 04" title="把重要的小事记下来" description="这页只写你确认过的话；每条便笺的去向与用途都可单独决定。" />
      {!sessionId ? (
        <ErrorState error={toApiError(new Error("缺少接待会话"))} />
      ) : session.isError ? (
        <ErrorState error={session.error} onRetry={() => void session.refetch()} />
      ) : !session.data ? (
        <LoadingState lines={3} />
      ) : confirm.data ? (
        <Saved result={confirm.data} />
      ) : (
        <div className="ps-stack">
          <p className="ps-muted" style={{ margin: 0 }}>
            “交给 TA”的内容只按你勾选的用途使用，默认不公开；“只留在这里”只有你和接待员看得到；“不保存”会被移除，不会再被整理回来。
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
          <div className="ps-reception-actions">
            <Button variant="primary" block icon="check" disabled={!ready} loading={confirm.isPending} onClick={() => confirm.mutate()}>
              这样记就对了
            </Button>
            {!ready ? <span className="ps-muted">每一条都选一下怎么处理；“交给 TA”至少勾一个用途。</span> : null}
            <Button variant="ghost" block onClick={() => navigate(env.dataMode === "live" ? "/onboarding/reception" : "/home")}>
              {env.dataMode === "live" ? "回到接待" : "先去看家"}
            </Button>
          </div>
        </div>
      )}
    </Page>
  );
}
