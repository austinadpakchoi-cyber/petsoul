import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, useLocation, useNavigate, useSearchParams } from "react-router";
import type { ReceptionBranch, ReceptionSession } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { toApiError } from "@/shared/api/errors";
import { queryKeys } from "@/shared/query/queryClient";
import { env } from "@/shared/config/env";
import { useServices } from "@/shared/services/registry";
import { useSessionState } from "@/shared/session/onboarding";
import { HouseholdProvider, useOptionalCurrentHousehold } from "@/shared/session/householdContext";
import { Button, DataOriginBadge, ErrorState, Icon, LoadingState, Page, TopBar } from "@/shared/ui";
import { EntrySteps, entryStepKicker } from "@/features/identity/EntryHeading";
import receptionWorld from "./assets/reception-world-v1.webp";
import { PawMark, petPortraitUrl } from "@/features/pets/PetPortrait";
import { hasInAppHistory, leaveSupplement, SUPPLEMENT_PARENT, trailFromReception } from "./trail";
import "./reception.css";

/** 接待页头像：不用名字首字——有照片用照片，演示模式用授权小灰猫，live 没有照片用爪印占位。 */
function ReceptionPortrait({ name, photoUrl: rawPhotoUrl }: { name: string; photoUrl: string | null }) {
  const photoUrl = petPortraitUrl(rawPhotoUrl);
  const [photoFailed, setPhotoFailed] = useState(false);
  useEffect(() => setPhotoFailed(false), [photoUrl]);
  const hasPhoto = Boolean(photoUrl && !photoFailed);
  return (
    <div className={`ps-reception-portrait${hasPhoto ? " has-photo" : ""}`} aria-label={hasPhoto ? `${name}的当前头像` : `${name}暂时没有照片`}>
      {hasPhoto ? <img src={photoUrl!} alt={name} onError={() => setPhotoFailed(true)} /> : <span className="ps-reception-portrait__empty"><PawMark size={34} /></span>}
      <span className="ps-reception-portrait__caption">{hasPhoto ? name : "暂无照片"}</span>
    </div>
  );
}

function ReceptionHero({ name, photoUrl, supplement }: { name: string; photoUrl: string | null; supplement: boolean }) {
  return (
    <section className="ps-reception-hero" aria-label="入住接待场景">
      <img className="ps-reception-hero__scene" src={receptionWorld} alt="" />
      <div className="ps-reception-hero__label"><span aria-hidden="true">✦</span> PetSoul · {supplement ? "生活叮嘱" : "入住接待"}</div>
      <ReceptionPortrait name={name} photoUrl={photoUrl} />
      <div className="ps-reception-hero__caption">
        <div>
          <span className="ps-reception-hero__eyebrow">{supplement ? "再记下一件小事" : entryStepKicker(3)}</span>
          <h1>{supplement ? `再聊聊 ${name}` : `先认识 ${name}`}</h1>
          <p>把你知道的，慢慢说给这个世界听。</p>
          {supplement ? null : <EntrySteps step={3} className="ps-reception-hero__steps" />}
        </div>
      </div>
    </section>
  );
}

/** 接待员身份（AI 角色）始终可见；记录方式的说明收进“怎么记”，不在首屏堆满说明文字。 */
function HostIntro({ session }: { session: ReceptionSession }) {
  return (
    <aside className="ps-host">
      <div className="ps-host__avatar" aria-hidden="true"><Icon name="sparkle" size={19} /></div>
      <div className="ps-host__body">
        <div className="ps-host__title"><strong>{session.host.display_name}</strong><span>{session.host.role_label}</span></div>
        <details className="ps-host__about">
          <summary>接待员会怎么记你说的话</summary>
          <p className="ps-host__disclosure">{session.host.disclosure}</p>
          {session.mode === "guided_notes" && !session.host.disclosure.includes("引导便笺模式") ? <p className="ps-host__mode">你的话会原样进入待确认页，不会被当作 TA 已经说过的话。</p> : null}
        </details>
      </div>
    </aside>
  );
}

function Conversation({ session }: { session: ReceptionSession }) {
  return (
    <div className="ps-reception-chat">
      <div className="ps-reception-section-title"><span>你和接待员</span><small>想到什么说什么 · 可以跳过</small></div>
      <ol className="ps-turns" aria-label="接待对话">
        {session.turns.map((turn) => (
          <li key={turn.turn_id} className={`ps-turn ps-turn--${turn.speaker}`}>
            {turn.text}
          </li>
        ))}
      </ol>
      <p id="reception-input-hint" className="ps-reception-hint">说一件，就整理成一条待你确认的叮嘱；不说也可以，以后还能补充</p>
    </div>
  );
}

/** 输入框最多长到这么高（约 5 行），再多就在框里滚动：贴底区不能吃掉整屏。 */
const COMPOSER_MAX_HEIGHT = 132;

/**
 * 输入框和“交代这一句”放在贴底区里（2026-09-24 巡检 P1：原来它们在正文末尾，首屏正好落在贴底按钮下面，
 * 320×568 上更是整个在首屏之外）。贴底区始终在屏幕底部，发送键任何时候都看得见、点得到。
 */
function Composer({ session }: { session: ReceptionSession }) {
  const { reception } = useServices();
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const keyRef = useRef(newIdempotencyKey("reception-turn"));
  const send = useMutation({
    mutationFn: () => reception.addTurn(session.session_id, { text, expected_revision: session.draft_revision }, keyRef.current),
    onSuccess: (next) => {
      keyRef.current = newIdempotencyKey("reception-turn");
      setText("");
      queryClient.setQueryData(queryKeys.reception(session.session_id), next);
    },
    // 别处（另一个标签页）改过便笺：重新读取当前版本，输入框里的话保留，由主人再发一次。
    onError: (error) => {
      if (toApiError(error).code === "VERSION_CONFLICT") void queryClient.invalidateQueries({ queryKey: queryKeys.reception(session.session_id) });
    },
  });
  // 一行起步，随内容长高到上限：平时贴底区只占一行输入的高度。
  useLayoutEffect(() => {
    const input = inputRef.current;
    if (!input) return;
    input.style.height = "";
    if (input.scrollHeight > 0) input.style.height = `${Math.min(input.scrollHeight, COMPOSER_MAX_HEIGHT)}px`;
  }, [text]);
  return (
    <form
      className="ps-composer"
      onSubmit={(event) => {
        event.preventDefault();
        if (text.trim() && !send.isPending) send.mutate();
      }}
    >
      <label className="visually-hidden" htmlFor="reception-input">
        再交代一件小事
      </label>
      <div className="ps-composer__row">
        <textarea
          ref={inputRef}
          id="reception-input"
          className="ps-composer__input"
          rows={1}
          placeholder="说一件关于 TA 的小事……"
          aria-describedby="reception-input-hint"
          value={text}
          maxLength={2000}
          onChange={(e) => setText(e.target.value)}
        />
        <Button type="submit" variant="leaf" size="sm" loading={send.isPending} disabled={!text.trim()}>
          交代这一句
        </Button>
      </div>
      {send.isError ? (
        <span role="alert" className="ps-composer__note is-error">没发出去，内容还在输入框里</span>
      ) : null}
    </form>
  );
}

/**
 * 接待页有两种用法，靠 `supplement` 分开：
 * - 入住中（新伙伴正在入住，入住阶段不是 active，也没带 ?mode=supplement）：叮嘱记给入住阶段里那只（session.onboarding.pet_id）；
 * - 入住以后来补充（?mode=supplement，或入住阶段已经是 active）：叮嘱记给“当前宠物”——通讯器、我的、小窝用的同一个家庭上下文，
 *   也就是切换栏选中的那只（2026-09-24 巡检 P0：切到豆包再补充，原来记到了入住阶段里记着的年糕身上）。
 *   接待页是不挂主布局的全屏页，没有家庭上下文，所以补充时在这里包一层 HouseholdProvider（两只以上时顶上也有切换栏）。
 */
export function ReceptionPage() {
  const [params] = useSearchParams();
  const account = useSessionState();
  const onboarding = account.data?.onboarding ?? null;
  const live = env.dataMode === "live";
  const supplement = params.get("mode") === "supplement" || onboarding?.step === "active";
  const userId = account.data?.user?.user_id ?? null;
  if (live && account.data && !account.data.authenticated) return <Navigate to="/welcome" replace />;
  if (live && onboarding?.step === "needs_companion") return <Navigate to="/onboarding" replace />;
  if (live && supplement && userId) {
    return (
      <HouseholdProvider userId={userId}>
        <ReceptionView supplement />
      </HouseholdProvider>
    );
  }
  return <ReceptionView supplement={supplement} />;
}

function ReceptionView({ supplement }: { supplement: boolean }) {
  const { reception, world, pets } = useServices();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const account = useSessionState();
  const current = useOptionalCurrentHousehold()?.pet ?? null;
  const onboarding = account.data?.onboarding ?? null;
  const live = env.dataMode === "live";
  // live：入住中用入住阶段里的那只（伙伴刚建立、尚未入住，不能读家园快照）；补充时用当前宠物。分支由那只宠物的来源决定。
  const livePetId = supplement ? current?.pet_id ?? onboarding?.pet_id : onboarding?.pet_id;
  const liveOrigin = supplement && current ? current.origin : onboarding?.pet_origin;
  const adoptedPet = liveOrigin ? liveOrigin !== "own_pet" : params.get("branch") === "adopted";
  const branch: ReceptionBranch = (live ? adoptedPet : params.get("branch") === "adopted") ? "adopted" : "own_pet";
  // 每只宠物各用一把开场幂等键：补充时在顶上切到另一只，是另一次接待，不沿用上一只的键。
  const startKeys = useRef(new Map<string, string>());
  const startKey = (id: string) => {
    let key = startKeys.current.get(id);
    if (!key) {
      key = newIdempotencyKey("reception-start");
      startKeys.current.set(id, key);
    }
    return key;
  };
  // 演示模式读演示家园快照；显式传当前宠物（演示下没有家庭上下文，就是 null，结果不变）。
  const home = useQuery({ queryKey: queryKeys.home, queryFn: () => world.home(current?.pet_id ?? null), enabled: !live && branch === "own_pet" });
  const petId = live ? livePetId ?? undefined : branch === "adopted" ? "fx-adopt-pet" : home.data?.pet.pet_id;
  const petProfile = useQuery({ queryKey: queryKeys.petProfile(petId ?? "-"), queryFn: () => pets.publicProfile(petId!), enabled: Boolean(petId), retry: false });
  const start = useQuery({
    queryKey: ["reception", "start", branch, petId],
    queryFn: () => reception.start({ pet_id: petId!, branch }, startKey(petId!)),
    enabled: Boolean(petId),
    staleTime: Infinity,
  });
  const sessionId = start.data?.session_id;
  const session = useQuery({ queryKey: queryKeys.reception(sessionId ?? "-"), queryFn: () => reception.get(sessionId!), enabled: Boolean(sessionId), initialData: start.data });
  const skip = useMutation({
    mutationFn: () => reception.skip(sessionId!),
    onSuccess: async () => {
      // 补充叮嘱：和左上角返回同一条规矩——站内有来路就回来路，直接打开时回“我的”；演示模式的入住接待回地图首页；入住中照旧去入住。
      if (supplement) return leaveSupplement(navigate, hasInAppHistory(location) ? 1 : 0);
      if (!live) return navigate("/map");
      await queryClient.invalidateQueries({ queryKey: queryKeys.session });
      navigate("/onboarding/move-in");
    },
  });

  const error = account.error ?? home.error ?? start.error ?? session.error;
  const name = petProfile.data?.display_name ?? home.data?.pet.name ?? "TA";
  const count = session.data?.candidates.length ?? 0;
  return (
    <Page bare className="ps-entry-page ps-reception-page">
      <TopBar title={supplement ? "补充叮嘱" : "入住接待"} subtitle={branch === "adopted" ? "迎接新伙伴" : "交代一些只有你知道的小事"} back={supplement ? SUPPLEMENT_PARENT : live ? undefined : "/onboarding"} />
      <ReceptionHero name={name} photoUrl={petProfile.data?.avatar_url ?? home.data?.pet.photo_url ?? null} supplement={supplement} />
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
        <>
          <div className="ps-stack ps-reception-body">
            <HostIntro session={session.data} />
            <Conversation session={session.data} />
            <DataOriginBadge origin={session.data.data_origin} label={session.data.data_origin === "fixture" ? "演示接待：对话为预置脚本，不是模型理解" : "引导便笺：原话原样记录，规则只给建议"} />
          </div>
          {/* 贴底区：输入框在上（发送键始终露在外面），主行动在下。主行动随状态变化：有待确认的叮嘱才去整理；一句没说时不把人引到空的确认页。 */}
          <div className="ps-entry-dock ps-reception-dock">
            <Composer key={session.data.session_id} session={session.data} />
            <div className="ps-reception-dock__actions" role="group" aria-label={supplement ? "补充叮嘱的下一步" : "接待的下一步"}>
              {count > 0 ? (
                <>
                  <Button variant="primary" block icon="bookmark" onClick={() => navigate(`/onboarding/notes?session=${encodeURIComponent(session.data!.session_id)}`, { state: trailFromReception(location) })}>
                    整理这 {count} 条叮嘱
                  </Button>
                  <Button variant="ghost" block loading={skip.isPending} onClick={() => skip.mutate()}>
                    {supplement ? "先回去（以后还能补充）" : live ? "跳过，直接去入住（以后还能补充）" : "先去地图看看（以后还能补充）"}
                  </Button>
                </>
              ) : (
                <Button variant="primary" block icon={supplement ? "back" : live ? "home" : "pin"} loading={skip.isPending} onClick={() => skip.mutate()}>
                  {supplement ? "先回去" : live ? `先带 ${name} 去入住` : "先去地图看看"}
                </Button>
              )}
              {skip.isError ? <p role="alert" className="ps-form-error ps-entry-dock__error"><strong>这一步没能完成，可以再点一次。</strong><span>{toApiError(skip.error).message}</span></p> : null}
            </div>
          </div>
        </>
      )}
    </Page>
  );
}
