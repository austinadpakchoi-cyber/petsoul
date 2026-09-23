import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, useNavigate, useSearchParams } from "react-router";
import type { ReceptionBranch, ReceptionSession } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { queryKeys } from "@/shared/query/queryClient";
import { env } from "@/shared/config/env";
import { useServices } from "@/shared/services/registry";
import { useSessionState } from "@/shared/session/onboarding";
import { Button, Chip, DataOriginBadge, ErrorState, Icon, LoadingState, Page, TopBar } from "@/shared/ui";
import receptionWorld from "./assets/reception-world-v1.webp";
import "./reception.css";

function PetPortrait({ name, photoUrl }: { name: string; photoUrl: string | null }) {
  const [photoFailed, setPhotoFailed] = useState(false);
  useEffect(() => setPhotoFailed(false), [photoUrl]);
  const hasPhoto = Boolean(photoUrl && !photoFailed);
  return (
    <div className={`ps-reception-portrait${hasPhoto ? " has-photo" : ""}`} aria-label={hasPhoto ? `${name}的当前头像` : `${name}暂时没有照片`}>
      {hasPhoto ? <img src={photoUrl!} alt={name} onError={() => setPhotoFailed(true)} /> : <span className="ps-reception-portrait__empty">{name.slice(0, 1)}</span>}
      <span className="ps-reception-portrait__caption">{hasPhoto ? name : "暂无照片"}</span>
    </div>
  );
}

function ReceptionHero({ name, photoUrl, supplement }: { name: string; photoUrl: string | null; supplement: boolean }) {
  return (
    <section className="ps-reception-hero" aria-label="入住接待场景">
      <img className="ps-reception-hero__scene" src={receptionWorld} alt="" />
      <div className="ps-reception-hero__label"><span aria-hidden="true">✦</span> PetSoul · {supplement ? "生活手册" : "入住接待"}</div>
      <PetPortrait name={name} photoUrl={photoUrl} />
      <div className="ps-reception-hero__caption">
        <div>
          <span className="ps-reception-hero__eyebrow">{supplement ? "再记下一件小事" : "在生活开始之前"}</span>
          <h1>{supplement ? `再聊聊 ${name}` : `先认识 ${name}`}</h1>
          <p>把你知道的，慢慢说给这个世界听。</p>
        </div>
      </div>
    </section>
  );
}

function HostIntro({ session }: { session: ReceptionSession }) {
  return (
    <aside className="ps-host">
      <div className="ps-host__avatar" aria-hidden="true"><Icon name="sparkle" size={21} /></div>
      <div className="ps-host__body">
        <div className="ps-host__title"><strong>{session.host.display_name}</strong><span>{session.host.role_label}</span></div>
        <p className="ps-host__disclosure">{session.host.disclosure}</p>
        {session.mode === "guided_notes" && !session.host.disclosure.includes("引导便笺模式") ? <p className="ps-host__mode">当前为引导便笺：你的话原样进入待确认页，不会被当作 TA 已经说过的话。</p> : null}
      </div>
    </aside>
  );
}

function Conversation({ session }: { session: ReceptionSession }) {
  const { reception } = useServices();
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const keyRef = useRef(newIdempotencyKey("reception-turn"));
  const send = useMutation({
    mutationFn: () => reception.addTurn(session.session_id, { text, expected_revision: session.draft_revision }, keyRef.current),
    onSuccess: (next) => {
      keyRef.current = newIdempotencyKey("reception-turn");
      setText("");
      queryClient.setQueryData(queryKeys.reception(session.session_id), next);
    },
  });
  return (
    <div className="ps-stack">
      <div className="ps-reception-section-title"><span>你和接待员</span><small>轻声聊聊 · 可以跳过</small></div>
      <ol className="ps-turns" aria-label="接待对话">
        {session.turns.map((turn) => (
          <li key={turn.turn_id} className={`ps-turn ps-turn--${turn.speaker}`}>
            {turn.text}
          </li>
        ))}
      </ol>
      <form
        className="ps-stack"
        onSubmit={(event) => {
          event.preventDefault();
          if (text.trim()) send.mutate();
        }}
      >
        <label className="visually-hidden" htmlFor="reception-input">
          再交代一件小事
        </label>
        <textarea id="reception-input" className="ps-textarea" placeholder="再交代一件小事，比如它怎么撒娇……（不想说可以跳过）" value={text} maxLength={2000} onChange={(e) => setText(e.target.value)} />
        <div className="ps-row">
          <Button type="submit" variant="secondary" loading={send.isPending} disabled={!text.trim()}>
            交代这一句
          </Button>
          {send.isError ? <Chip tone="danger">没发出去，内容还在输入框里</Chip> : null}
        </div>
      </form>
    </div>
  );
}

export function ReceptionPage() {
  const { reception, world, pets } = useServices();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const account = useSessionState();
  const onboarding = account.data?.onboarding ?? null;
  const live = env.dataMode === "live";
  // live：宠物来自当前账号的入住阶段（伙伴刚建立、尚未入住，不能读家园快照）；分支由伙伴来源决定。
  const adoptedPet = onboarding?.pet_origin ? onboarding.pet_origin !== "own_pet" : params.get("branch") === "adopted";
  const branch: ReceptionBranch = (live ? adoptedPet : params.get("branch") === "adopted") ? "adopted" : "own_pet";
  const supplement = params.get("mode") === "supplement" || onboarding?.step === "active";
  const keyRef = useRef(newIdempotencyKey("reception-start"));
  const home = useQuery({ queryKey: queryKeys.home, queryFn: () => world.home(), enabled: !live && branch === "own_pet" });
  const petId = live ? onboarding?.pet_id ?? undefined : branch === "adopted" ? "fx-adopt-pet" : home.data?.pet.pet_id;
  const petProfile = useQuery({ queryKey: queryKeys.petProfile(petId ?? "-"), queryFn: () => pets.publicProfile(petId!), enabled: Boolean(petId), retry: false });
  const start = useQuery({
    queryKey: ["reception", "start", branch, petId],
    queryFn: () => reception.start({ pet_id: petId!, branch }, keyRef.current),
    enabled: Boolean(petId),
    staleTime: Infinity,
  });
  const sessionId = start.data?.session_id;
  const session = useQuery({ queryKey: queryKeys.reception(sessionId ?? "-"), queryFn: () => reception.get(sessionId!), enabled: Boolean(sessionId), initialData: start.data });
  const skip = useMutation({
    mutationFn: () => reception.skip(sessionId!),
    onSuccess: async () => {
      if (!live || supplement) return navigate("/home");
      await queryClient.invalidateQueries({ queryKey: queryKeys.session });
      navigate("/onboarding/move-in");
    },
  });

  if (live && account.data && !account.data.authenticated) return <Navigate to="/welcome" replace />;
  if (live && onboarding?.step === "needs_companion") return <Navigate to="/onboarding" replace />;
  const error = account.error ?? home.error ?? start.error ?? session.error;
  return (
    <Page bare className="ps-entry-page ps-reception-page">
      <TopBar title={supplement ? "补充叮嘱" : "入住接待"} subtitle={branch === "adopted" ? "迎接新伙伴" : "交代一些只有你知道的小事"} back={supplement ? "/home" : live ? undefined : "/onboarding"} />
      <ReceptionHero name={petProfile.data?.display_name ?? home.data?.pet.name ?? "TA"} photoUrl={petProfile.data?.avatar_url ?? home.data?.pet.photo_url ?? null} supplement={supplement} />
      {error ? (
        <ErrorState error={error} onRetry={() => {
          if (account.isError) void account.refetch();
          if (home.isError) void home.refetch();
          if (start.isError) void start.refetch();
          if (session.isError && sessionId) void session.refetch();
        }} />
      ) : !session.data ? (
        <LoadingState lines={2} label="接待员正在准备…" />
      ) : (
        <div className="ps-stack">
          <HostIntro session={session.data} />
          <Conversation session={session.data} />
          <p className="ps-reception-privacy">你说的话会先整理成便笺。是否交给 TA、只留在这里或不保存，下一步由你逐条确认。</p>
          <DataOriginBadge origin={session.data.data_origin} label={session.data.data_origin === "fixture" ? "演示接待：对话为预置脚本，不是模型理解" : "引导便笺：原话原样记录，规则只给建议"} />
          <div className="ps-reception-actions">
            <Button variant="primary" block icon="bookmark" onClick={() => navigate(`/onboarding/notes?session=${encodeURIComponent(session.data!.session_id)}`)}>
              整理成入住叮嘱（{session.data.candidates.length} 条待确认）
            </Button>
            <Button variant="ghost" block loading={skip.isPending} onClick={() => skip.mutate()}>
              {supplement ? "先回家（以后还能补充）" : "跳过，直接去入住（以后还能补充）"}
            </Button>
          </div>
        </div>
      )}
    </Page>
  );
}
