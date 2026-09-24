import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";
import type { EntryIntentRequest, HabitatKind, HabitatOption, SessionState, SettingsUpdateInput, SettingsView } from "@/shared/contracts";
import { toApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { onboardingRoute, routeAfterSession, useSessionState } from "@/shared/session/onboarding";
import { useCurrentHousehold } from "@/shared/session/householdContext";
import { Button, Card, Chip, DisabledState, ErrorState, Icon, LoadingState, Page, ToggleChip, TopBar } from "@/shared/ui";
import { EntryHeading, EntrySteps, entryStepKicker } from "./EntryHeading";
import { BrandLogo } from "@/shared/ui/BrandLogo";
import "./identity.css";
import entryFilm from "./assets/entry-film-mobile.mp4";
import entryPoster from "./assets/entry-film-poster.jpg";
import invitationLetter from "@/features/pets/assets/entry-invitation-letter-v1.webp";
import courtyard from "@/features/home/assets/living/courtyard-base.webp";
import { PawMark, petPortraitUrl } from "@/features/pets/PetPortrait";
import { petToReturnTo } from "@/features/world_map/WorldGate";

export function WelcomePage() {
  const session = useSessionState();
  const film = useRef<HTMLVideoElement>(null);
  const [paused, setPaused] = useState(false);
  const [reduceMotion, setReduceMotion] = useState(() => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => {
      setReduceMotion(preference.matches);
      if (preference.matches) film.current?.pause();
    };
    preference.addEventListener("change", update);
    return () => preference.removeEventListener("change", update);
  }, []);
  if (env.dataMode === "live" && session.data?.authenticated) return <Navigate to={routeAfterSession(session.data)} replace />;
  return (
    <Page bare className="ps-welcome-page">
      <div className="ps-welcome-film" aria-hidden="true">
        <img src={entryPoster} alt="" />
        <video ref={film} src={entryFilm} poster={entryPoster} autoPlay={!reduceMotion} muted playsInline loop preload="metadata" />
      </div>
      <div className="ps-welcome-top">
        <BrandLogo size="welcome" />
        {!reduceMotion ? <button
          type="button"
          className="ps-welcome-pause"
          aria-label={paused ? "播放开场影片" : "暂停开场影片"}
          onClick={() => {
            const video = film.current;
            if (!video) return;
            if (video.paused) {
              void video.play().then(() => setPaused(false)).catch(() => setPaused(true));
            } else {
              video.pause();
              setPaused(true);
            }
          }}
        >
          {paused ? "▶" : "Ⅱ"}
        </button> : null}
      </div>
      <div className="ps-welcome-bottom">
        <span className="ps-welcome-eyebrow">欢迎来到 PetSoul 星球</span>
        <h1>和 TA 一起，<br />走进另一个世界。</h1>
        <p>每只宠物，都有一段属于自己的故事。</p>
        <div className="ps-welcome-actions">
          <Link to="/register" className="ps-welcome-action ps-welcome-action--primary">寻找我的 TA <span aria-hidden="true">↗</span></Link>
          <Link to="/world#residents" className="ps-welcome-action ps-welcome-action--secondary">先去星球上逛逛 <span aria-hidden="true">→</span></Link>
        </div>
        <Link to="/login" className="ps-welcome-login">已经找到 TA 了？登录</Link>
        <span className="ps-welcome-disclosure">开场影片为概念影像，不代表你或居民的真实宠物。</span>
      </div>
    </Page>
  );
}

function entryFromParams(params: URLSearchParams): EntryIntentRequest | null {
  const kind = params.get("entry");
  if (kind === "adopt") {
    const petId = params.get("pet_id");
    return petId ? { kind, pet_id: petId, invite_token: null } : null;
  }
  if (kind === "invite") {
    const token = params.get("invite");
    return token ? { kind, pet_id: null, invite_token: token } : null;
  }
  if (kind === "browse" || kind === "own_pet") return { kind, pet_id: null, invite_token: null };
  return null;
}

function SelectedResidentBanner({ petId }: { petId: string }) {
  const { pets } = useServices();
  const selected = useQuery({ queryKey: queryKeys.publicPet(petId), queryFn: () => pets.publicPet(petId), retry: false, staleTime: 30_000 });
  if (selected.isPending) return <p className="ps-selected-resident ps-selected-resident--loading">正在找回刚才认识的居民…</p>;
  if (selected.isError || !selected.data) return <p className="ps-selected-resident">这位居民暂时无法打开，<Link to="/world">返回星球看看</Link>。</p>;
  return (
    <div className="ps-selected-resident">
      {/* 头像不用名字首字：没有公开照片时演示模式用授权小灰猫，live 用爪印占位。 */}
      <span className="ps-selected-resident__portrait">{petPortraitUrl(selected.data.profile.avatar_url) ? <img src={petPortraitUrl(selected.data.profile.avatar_url)!} alt="" /> : <PawMark size={18} />}</span>
      <span><small>刚才认识的居民</small><strong>{selected.data.profile.display_name}</strong></span>
      <Link to={`/world/residents/${encodeURIComponent(petId)}`}>再看一眼</Link>
    </div>
  );
}

function SelectedInviteBanner({ token }: { token: string }) {
  const { households } = useServices();
  const invite = useQuery({ queryKey: queryKeys.invitePreview(token), queryFn: () => households.previewInvite(token), retry: false, staleTime: 0 });
  if (invite.isPending) return <p className="ps-selected-resident ps-selected-resident--loading">正在核对家人邀请…</p>;
  if (invite.isError || !invite.data) return <p className="ps-selected-resident">这封邀请暂时无法打开。请检查链接或稍后重试。</p>;
  return <div className="ps-selected-resident">
    <span className="ps-selected-resident__portrait"><img src={invitationLetter} alt="" /></span>
    <span><small>刚才打开的家人邀请</small><strong>{invite.data.household_name || "一个正在生活的家"}</strong></span>
    <Link to={`/join?invite=${encodeURIComponent(token)}`}>再看一眼</Link>
  </div>;
}

function AuthForm({ kind }: { kind: "register" | "login" }) {
  const { session } = useServices();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const entry = entryFromParams(params);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const submit = useMutation({
    mutationFn: () => (kind === "register" ? session.register(username.trim(), password, undefined, entry) : session.login(username.trim(), password)),
    onSuccess: (state: SessionState) => {
      // 新会话：丢弃上一个账号的全部缓存，再按入住阶段跳转。
      queryClient.clear();
      queryClient.setQueryData(queryKeys.session, state);
      // Existing accounts have no register(entry) call: carry the selected public resident through login URL.
      const chosenPet = kind === "login" && entry?.kind === "adopt" ? entry.pet_id : null;
      const inviteToken = entry?.kind === "invite" ? entry.invite_token : null;
      navigate(inviteToken ? `/join?invite=${encodeURIComponent(inviteToken)}` : chosenPet && state.onboarding?.step === "needs_companion" ? `/onboarding/choice?pet_id=${encodeURIComponent(chosenPet)}` : routeAfterSession(state), { replace: true });
    },
  });
  const error = submit.error ? toApiError(submit.error) : null;
  return (
    <form
      className="ps-stack ps-auth-form"
      onSubmit={(e) => {
        e.preventDefault();
        submit.mutate();
      }}
    >
      <div className="ps-field">
        <label htmlFor="username">你的账号名</label>
        <input
          id="username"
          className="ps-input"
          autoComplete="username"
          autoCapitalize="none"
          placeholder="用来找到属于你的家"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          minLength={3}
          maxLength={32}
          pattern="[A-Za-z0-9_.\-]{3,32}"
          title="3–32 位字母、数字、下划线、点或短横线"
          required
        />
        <span className="ps-auth-field-note">3–32 位，可用英文字母、数字、点、下划线或短横线。</span>
      </div>
      <div className="ps-field">
        <label htmlFor="password">{kind === "register" ? "设置密码" : "密码"}</label>
        <div className="ps-auth-password">
          <input
            id="password"
            className="ps-input"
            type={showPassword ? "text" : "password"}
            autoComplete={kind === "register" ? "new-password" : "current-password"}
            placeholder={kind === "register" ? "至少 8 位" : "输入密码"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={kind === "register" ? 8 : 1}
            maxLength={128}
            required
          />
          <button type="button" className="ps-auth-password__toggle" aria-label={showPassword ? "隐藏密码" : "显示密码"} aria-pressed={showPassword} onClick={() => setShowPassword((old) => !old)}>
            {showPassword ? "隐藏" : "显示"}
          </button>
        </div>
        {kind === "register" ? <span className="ps-auth-field-note">现在还没有密码找回功能，请记住这把钥匙。</span> : null}
      </div>
      <Button type="submit" variant="primary" block loading={submit.isPending}>
        {kind === "register" ? "创建账号，继续" : "登录，继续"}
      </Button>
      {error ? (
        error.isCapabilityUnavailable ? (
          <DisabledState title="账号注册/登录不可用">{error.message}</DisabledState>
        ) : error.code === "USERNAME_TAKEN" || error.code === "INVALID_CREDENTIALS" || error.code === "RATE_LIMITED" || error.code === "VALIDATION_FAILED" ? (
          <p role="alert" className="ps-form-error">
            {error.code === "VALIDATION_FAILED" ? "用户名或密码格式不对。" : error.message}
          </p>
        ) : (
          <ErrorState error={error} />
        )
      ) : null}
    </form>
  );
}

export function RegisterPage() {
  const [params] = useSearchParams();
  const entry = entryFromParams(params);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const back = entry?.kind === "invite" && entry.invite_token ? `/join?invite=${encodeURIComponent(entry.invite_token)}` : entry?.kind === "adopt" && entry.pet_id ? `/world/residents/${encodeURIComponent(entry.pet_id)}` : "/welcome";
  return (
    <Page bare className={`ps-entry-page ps-auth-page${entry?.kind === "adopt" ? " ps-auth-page--adopt" : ""}`}>
      <div className="ps-auth-hero">
        <TopBar title="注册" back={back} />
        <div className="ps-auth-hero__caption">
          <BrandLogo />
          <strong>和 TA 一起，走进另一个世界。</strong>
        </div>
      </div>
      <div className="ps-auth-sheet">
        <EntryHeading step={1} kicker="第一站 · 建立账号" title={entry?.kind === "invite" ? "先收好这封邀请" : entry?.kind === "adopt" ? "把刚才的相遇留住" : "给自己留一把钥匙"} description={entry?.kind === "invite" ? "建立账号后，你可以决定是否加入这个家。" : entry?.kind === "adopt" ? "建立账号后，回到刚才认识的居民身边。" : "先认识你，再带 TA 来到这个世界。"} />
        {entry?.kind === "adopt" && entry.pet_id ? <SelectedResidentBanner petId={entry.pet_id} /> : null}
        {entry?.kind === "invite" && entry.invite_token ? <SelectedInviteBanner token={entry.invite_token} /> : null}
        <AuthForm kind="register" />
        <p className="ps-entry-support">创建账号不会自动领养居民或加入家庭，之后仍由你确认。</p>
        <p className="ps-entry-support ps-auth-switch">已有账号？<Link to={`/login${suffix}`}>登录，继续</Link></p>
      </div>
    </Page>
  );
}

export function LoginPage() {
  const [params] = useSearchParams();
  const entry = entryFromParams(params);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const back = entry?.kind === "invite" && entry.invite_token ? `/join?invite=${encodeURIComponent(entry.invite_token)}` : entry?.kind === "adopt" && entry.pet_id ? `/world/residents/${encodeURIComponent(entry.pet_id)}` : "/welcome";
  return (
    <Page bare className={`ps-entry-page ps-auth-page${entry?.kind === "adopt" ? " ps-auth-page--adopt" : ""}`}>
      <div className="ps-auth-hero">
        <TopBar title="登录" back={back} />
        <div className="ps-auth-hero__caption">
          <BrandLogo />
          <strong>另一个世界，等你回来。</strong>
        </div>
      </div>
      <div className="ps-auth-sheet">
        <EntryHeading kicker="欢迎回来" title="继续你们的故事" description="从上次停下的地方继续。" />
        {entry?.kind === "adopt" && entry.pet_id ? <SelectedResidentBanner petId={entry.pet_id} /> : null}
        {entry?.kind === "invite" && entry.invite_token ? <SelectedInviteBanner token={entry.invite_token} /> : null}
        <AuthForm kind="login" />
        <p className="ps-entry-support ps-auth-switch">第一次来？<Link to={`/register${suffix}`}>创建账号</Link></p>
      </div>
    </Page>
  );
}

/**
 * UI-ASSET-001 v1（r7k 交付，c84a 素材检查通过）：海边 SHA-256 3709438F…/blob 1fa57117，城市 3487B7C8…/blob 23b3f6a2。
 * 只登记已交付的住处；其余住处开放前另出版本，未登记时显示中性色块，不用示意画冒充。
 */
const HABITAT_ART: Partial<Record<HabitatKind, string>> = {
  seaside: "/ui-assets/UI-ASSET-001/v1/habitat-seaside.webp",
  city: "/ui-assets/UI-ASSET-001/v1/habitat-city.webp",
};
const HABITAT_MARK: Partial<Record<HabitatKind, "wave" | "home" | "sprout" | "compass">> = { seaside: "wave", lakeside: "wave", city: "home", countryside: "sprout", grassland: "sprout", forest: "sprout" };

/**
 * 选这一类会安家在哪：照接口给的城市写（examples 是这一类里新家现在能分到的城市，2026-09-24 巡检 P2：原来写“可能落在 香港”）。
 * 卡上的图只是这一类地方的样子，这句只说城市，不说“图里就是那儿”；接口没给城市时由星球安排。
 */
export function habitatWhere(option: HabitatOption): string {
  const cities = option.examples.map((city) => city.trim()).filter(Boolean);
  if (!cities.length) return "由星球安排片区";
  return cities.length === 1 ? `安家在${cities[0]}` : `安家在${cities.slice(0, -1).join("、")}或${cities[cities.length - 1]}`;
}

function HabitatPostcard({ option, selected, onSelect }: { option: HabitatOption; selected: boolean; onSelect: () => void }) {
  const art = HABITAT_ART[option.habitat];
  const [artFailed, setArtFailed] = useState(false);
  const showArt = Boolean(art && !artFailed);
  return (
    <button type="button" className={`ps-habitat-card is-${option.habitat}${selected ? " is-selected" : ""}${showArt ? " has-art" : ""}`} aria-pressed={selected} onClick={onSelect}>
      <span className="ps-habitat-card__art" aria-hidden="true">
        {showArt ? <img src={art} alt="" onError={() => setArtFailed(true)} /> : <Icon name={HABITAT_MARK[option.habitat] ?? "compass"} size={26} strokeWidth={1.5} />}
        <span className="ps-habitat-card__check"><Icon name="check" size={15} strokeWidth={2.6} /></span>
      </span>
      <strong>{option.label}</strong>
      <small>{habitatWhere(option)}</small>
    </button>
  );
}

/** 入住失败的每种原因都有自己的出路；pet_away 是等待，不是错误。 */
function moveInProblem(error: unknown): { reason: string | null; message: string } | null {
  if (!error) return null;
  const err = toApiError(error);
  const reason = typeof err.details?.reason === "string" ? err.details.reason : null;
  if (reason === "pet_away") return { reason, message: "" };
  if (reason === "habitat_not_supported") return { reason, message: "刚才选的地方暂时不能入住了。请重新选一处，或者不选直接入住。" };
  if (reason === "manage_required") return { reason, message: "家的位置由家庭管理员决定。可以不选，直接入住。" };
  if (err.kind === "network" || err.kind === "timeout" || (err.status ?? 0) >= 500) return { reason: "unconfirmed", message: "入住结果还没确认。已经重新核对；如果还停在这里，可以再点一次，不会重复入住。" };
  return { reason, message: err.message };
}

/** 入住激活：与接待分开。主人明确选择是否让 TA 的旅行到访生成公开动态（默认不公开）。 */
export function MoveInPage() {
  const { session, pets } = useServices();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const state = useSessionState();
  const [publicPosts, setPublicPosts] = useState(false);
  const [habitat, setHabitat] = useState<HabitatKind | null>(null);
  // 入住成功后本页不再按会话步骤自行跳转：否则守卫的 <Navigate replace> 会盖掉带“到家时刻”状态的那次跳转。
  const movedIn = useRef(false);
  const petId = state.data?.onboarding?.pet_id ?? null;
  const profile = useQuery({ queryKey: queryKeys.petProfile(petId ?? "-"), queryFn: () => pets.publicProfile(petId!), enabled: Boolean(petId) });
  const place = useQuery({ queryKey: queryKeys.homePlace(petId ?? "-"), queryFn: () => session.homePlace(petId), enabled: Boolean(petId), retry: false });
  const moveIn = useMutation({
    mutationFn: () => session.moveIn(publicPosts, habitat, petId),
    onSuccess: (onboarding) => {
      movedIn.current = true;
      queryClient.setQueryData<SessionState | undefined>(queryKeys.session, (prev) => (prev ? { ...prev, onboarding } : prev));
      void queryClient.invalidateQueries({ queryKey: queryKeys.home });
      void queryClient.invalidateQueries({ queryKey: ["households"] });
      // The choice is user-scoped and revalidated against /households before display.
      const userId = state.data?.user?.user_id;
      if (userId && petId) {
        try { sessionStorage.setItem(`petsoul:current-pet:${userId}`, petId); } catch { /* still usable without storage */ }
      }
      // 到家时刻只跟着这一次跳转（路由状态）出现：刷新、返回都不会重播。
      // 这里有意去小窝 /home、不去地图首页 /map：第一次入住的“到家时刻”在小窝里播（小窝左上角再回地图）；
      // 其余完成、返回都已改去 /map 或“我的”（2026-09-24 新导航）。
      navigate("/home", { replace: true, state: petId ? { arrival: petId } : null });
    },
    onError: (error) => {
      const problem = moveInProblem(error);
      if (problem?.reason === "habitat_not_supported") {
        setHabitat(null);
        void place.refetch();
      }
      if (problem?.reason === "manage_required") setHabitat(null);
      // 入住接口幂等：回执不确定时先重读会话；若其实已经入住，下方守卫会按入住阶段直接带去地图首页。
      if (problem?.reason === "unconfirmed") void state.refetch();
    },
  });

  if (env.dataMode === "fixture") return <Navigate to="/map" replace />;
  if (state.isPending) return <LoadingState lines={2} />;
  if (state.isError) return <ErrorState error={state.error} onRetry={() => void state.refetch()} />;
  if (!state.data.authenticated) return <Navigate to="/welcome" replace />;
  if (movedIn.current) return <Page bare className="ps-entry-page ps-movein-page"><LoadingState lines={1} label="正在回家…" /></Page>;
  const step = state.data.onboarding?.step;
  if (step !== "ready_to_move_in" && step !== "reception_optional") return <Navigate to={onboardingRoute(state.data.onboarding)} replace />;

  const name = profile.data?.display_name ?? "TA";
  const photo = profile.data?.avatar_url ?? null;
  const portrait = petPortraitUrl(photo);
  const problem = moveIn.isError && !moveIn.isPending ? moveInProblem(moveIn.error) : null;
  const away = problem?.reason === "pet_away";
  const view = place.data;
  const openOptions = view?.options.filter((option) => option.open) ?? [];
  // 还没开放的类型不一一列出（2026-09-24 巡检 P2：原来一口气列出六个“还没开放”），只在有的时候说一句“更多地方以后开放”。
  const moreLater = view?.options.some((option) => option.open === false) ?? false;
  const canChoose = Boolean(view && !view.place.chosen && view.can_change && openOptions.length);
  // 账号里已经有住进来的宠物、这一只是后加的：给一个“先不加了”的出口回地图，当前宠物还是原来那只（第一次入住没有这个出口）。
  const returnTo = petToReturnTo(state.data.onboarding, state.data.user?.user_id);
  return (
    <Page bare className="ps-entry-page ps-movein-page">
      <TopBar title="入住" subtitle="最后一步，带 TA 回家" />
      <section className="ps-movein-hero" aria-label={`${name} 的新家`}>
        <img className="ps-movein-hero__scene" src={courtyard} alt="" />
        <span className={`ps-movein-hero__pet${portrait ? " has-photo" : ""}`} aria-label={portrait ? `${name}的当前头像` : `${name}暂时没有照片`}>
          {portrait ? <img src={portrait} alt="" /> : <PawMark size={28} />}
          <small>{portrait ? name : "暂无照片"}</small>
        </span>
        <div className="ps-movein-hero__caption">
          <span className="ps-movein-hero__kicker">{entryStepKicker(4)}</span>
          <h1>带 {name} 回家</h1>
          <p>入住之后，家园、信箱和 TA 的旅途会按真实时间慢慢展开。</p>
          <EntrySteps step={4} />
        </div>
      </section>

      <section className="ps-movein-section" aria-labelledby="movein-place-title">
        <h2 id="movein-place-title">家的样子</h2>
        {place.isPending ? <LoadingState lines={1} label="正在确认可以安家的地方…" /> : place.isError ? <ErrorState error={place.error} onRetry={() => void place.refetch()} /> : view ? (
          view.place.chosen ? (
            <p className="ps-movein-note">这个家在 {view.place.display}，{name} 会住进同一处。</p>
          ) : (
            <>
              <p className="ps-movein-note">
                {canChoose ? `希望 ${name} 住在什么样的地方？星球会在那一类片区里安排一处，不给具体地址。不选也可以，先住在 ${view.place.display}。` : `${name} 会先住在 ${view.place.display}。`}
              </p>
              {canChoose ? (
                <div className="ps-habitat-grid" role="group" aria-label="选择家的环境">
                  {openOptions.map((option) => <HabitatPostcard key={option.habitat} option={option} selected={habitat === option.habitat} onSelect={() => setHabitat((old) => (old === option.habitat ? null : option.habitat))} />)}
                </div>
              ) : null}
              {!view.can_change ? <p className="ps-movein-note">TA 在外面的时候不能定家的位置，回来后再选。</p> : null}
              {moreLater ? <p className="ps-movein-closed">更多地方以后开放。</p> : null}
            </>
          )
        ) : null}
      </section>

      <section className="ps-movein-section">
        <label className="ps-switch-row">
          <span>
            <strong>让 TA 的旅途见闻出现在朋友圈</strong>
            <small>默认关闭。只在 TA 真实到访之后才会发；你们的私密通讯和生活叮嘱永远不会公开。之后可以在设置里改。</small>
          </span>
          <input type="checkbox" role="switch" className="ps-switch" checked={publicPosts} onChange={(e) => setPublicPosts(e.target.checked)} />
        </label>
      </section>

      <div className="ps-entry-dock" role="group" aria-label="入住">
        {away ? (
          <div className="ps-movein-away" role="status">
            <strong>{name} 还在外面</strong>
            <span>TA 不会瞬移回家。等 TA 回到驿站，再来接 TA 回家。</span>
          </div>
        ) : problem ? (
          <p role="alert" className="ps-form-error ps-entry-dock__error">{problem.message}</p>
        ) : null}
        <Button variant="primary" block icon="home" loading={moveIn.isPending} disabled={place.isPending || place.isError} onClick={() => moveIn.mutate()}>
          {away ? "再看看 TA 回来没有" : "入住，一起开始生活"}
        </Button>
        {returnTo ? (
          <Button variant="ghost" block icon="back" onClick={() => navigate("/map")}>
            先不加了，回到 {returnTo.name}
          </Button>
        ) : null}
      </div>
    </Page>
  );
}

const VISIBILITY: Array<{ id: string; label: string }> = [
  { id: "public", label: "所有人" },
  { id: "followers", label: "关注 TA 的宠物" },
  { id: "private", label: "只有我" },
];

/**
 * 聊天时的“理解帮手”（后端的意图判断层）：服务端统一开关，玩家这里只看。按模式说人话，不露原始代码。
 * off 没开；shadow 只在后台试着理解、不改变 TA 的回复；assist 开着。
 */
const INTENT_MODE: Record<string, { chip: string; tone: "neutral" | "sky"; note?: string }> = {
  off: { chip: "未开启", tone: "neutral" },
  shadow: { chip: "试运行中", tone: "neutral", note: "现在只在后台试着理解，不会改变 TA 的回复。" },
  assist: { chip: "已开启", tone: "sky" },
};

function SettingsForm({ view, petId, settingsKey }: { view: SettingsView; petId: string | null; settingsKey: readonly unknown[] }) {
  const { session } = useServices();
  const queryClient = useQueryClient();
  const [bio, setBio] = useState(view.bio ?? "");
  const intent = Object.prototype.hasOwnProperty.call(INTENT_MODE, view.intent_layer_mode) ? INTENT_MODE[view.intent_layer_mode] : INTENT_MODE.off;
  const save = useMutation({
    // 简介、公开范围、公开动态都是这只宠物的：带上当前宠物（一家有两只时不带就 409 pet_required）。
    mutationFn: (patch: SettingsUpdateInput) => session.updateSettings(patch, petId),
    onSuccess: (next) => {
      queryClient.setQueryData(settingsKey, next);
      void queryClient.invalidateQueries({ queryKey: ["social"] });
    },
  });
  return (
    <>
      <Card>
        <div className="ps-section-title" style={{ marginTop: 0 }}>
          朋友圈
        </div>
        <label className="ps-check">
          <input type="checkbox" checked={view.public_posts} disabled={save.isPending} onChange={(e) => save.mutate({ public_posts: e.target.checked })} />
          <span>
            TA 旅行到访后发公开动态
            <span className="ps-muted" style={{ display: "block" }}>
              关闭后新的到访不再公开；已发的动态可以在朋友圈里撤下。
            </span>
          </span>
        </label>
        <div className="ps-field">
          <span className="ps-muted">谁能看到 TA 的主页与照片</span>
          <div className="ps-segmented" role="group" aria-label="主页公开范围">
            {VISIBILITY.map((v) => (
              <ToggleChip key={v.id} pressed={view.profile_visibility === v.id} onToggle={() => save.mutate({ profile_visibility: v.id })}>
                {v.label}
              </ToggleChip>
            ))}
          </div>
        </div>
        <form
          className="ps-field"
          style={{ marginTop: 12 }}
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate({ bio: bio.trim() });
          }}
        >
          <label htmlFor="bio">TA 的简介</label>
          <input id="bio" className="ps-input" maxLength={120} value={bio} onChange={(e) => setBio(e.target.value)} placeholder="一句话介绍 TA" />
          <Button type="submit" size="sm" variant="secondary" loading={save.isPending} disabled={bio.trim() === (view.bio ?? "")}>
            保存简介
          </Button>
        </form>
        {save.isError ? <ErrorState error={save.error} /> : null}
      </Card>
      <Card>
        <div className="ps-section-title" style={{ marginTop: 0 }}>
          聊天时更懂你
        </div>
        <div className="ps-row" style={{ alignItems: "flex-start" }}>
          <Chip tone={intent.tone}>{intent.chip}</Chip>
          <span className="ps-muted">
            开启后，TA 回你消息时会更贴着你的意思，有时还会附上一个由你决定点不点的小选项；不开启时 TA 照常回复。开不开都不会替你改行程、删回忆，也不会把内容公开。
            {intent.note ? <span style={{ display: "block", marginTop: 4 }}>{intent.note}</span> : null}
          </span>
        </div>
      </Card>
    </>
  );
}

export function SettingsPage() {
  const { session } = useServices();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const current = useSessionState();
  // 设置里有这只宠物的简介与公开范围：按当前宠物读。live 的键带账号与宠物（切宠物时“identity”前缀的缓存不会被清，
  // 不分键就会看到上一只的简介）；演示只有一份。
  const { userId, pet } = useCurrentHousehold();
  const petId = pet?.pet_id ?? null;
  const fixture = env.dataMode === "fixture";
  const settingsKey = fixture ? queryKeys.settings : [...queryKeys.settings, userId ?? "-", petId ?? "-"];
  const settings = useQuery({ queryKey: settingsKey, queryFn: () => session.settings(petId), enabled: fixture || Boolean(userId && petId) });
  const logout = useMutation({
    mutationFn: () => session.logout(),
    onSettled: () => {
      queryClient.clear();
      navigate("/welcome", { replace: true });
    },
  });
  return (
    <Page>
      <TopBar title="账号与设置" back="/me" />
      <div className="ps-stack">
        <Card>
          <div className="ps-section-title" style={{ marginTop: 0 }}>
            当前账号
          </div>
          {current.isError ? (
            <ErrorState error={current.error} onRetry={() => void current.refetch()} />
          ) : current.data ? (
            current.data.authenticated ? (
              <div className="ps-stack">
                <div className="ps-row">
                  <Icon name="user" />
                  <strong>{current.data.user?.username ?? current.data.user?.display_name ?? "已登录"}</strong>
                  <Chip>{current.data.user?.auth_method === "apple_bearer" ? "Apple 登录" : "网页账号"}</Chip>
                </div>
                <Button variant="danger" loading={logout.isPending} onClick={() => logout.mutate()}>
                  退出登录
                </Button>
              </div>
            ) : (
              <div className="ps-stack">
                <span className="ps-muted">{env.dataMode === "fixture" ? "演示模式没有账号。" : "未登录。"}</span>
                <Link className="ps-btn ps-btn--secondary" to="/welcome">
                  去注册/登录
                </Link>
              </div>
            )
          ) : (
            <LoadingState lines={1} />
          )}
        </Card>
        {settings.isError ? <ErrorState error={settings.error} onRetry={() => void settings.refetch()} /> : settings.data ? <SettingsForm key={petId ?? "demo"} view={settings.data} petId={petId} settingsKey={settingsKey} /> : <LoadingState lines={2} />}
      </div>
    </Page>
  );
}
