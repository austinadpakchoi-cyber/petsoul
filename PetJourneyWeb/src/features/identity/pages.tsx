import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";
import type { EntryIntentRequest, HabitatKind, SessionState, SettingsUpdateInput, SettingsView } from "@/shared/contracts";
import { toApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { onboardingRoute, routeAfterSession, useSessionState } from "@/shared/session/onboarding";
import { Button, Card, Chip, DisabledState, ErrorState, Icon, LoadingState, Page, ToggleChip, TopBar } from "@/shared/ui";
import { EntryHeading } from "./EntryHeading";
import "./identity.css";
import entryFilm from "./assets/entry-film-mobile.mp4";
import entryPoster from "./assets/entry-film-poster.jpg";
import invitationLetter from "@/features/pets/assets/entry-invitation-letter-v1.webp";

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
        <span className="ps-welcome-wordmark">PetSoul<span className="ps-welcome-wordmark__star">✳</span></span>
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
        <span className="ps-welcome-eyebrow">WELCOME TO THE LIVING WORLD</span>
        <h1>这一次，<br />和 TA 一起生活。</h1>
        <p>家会一直在，旅途也正在发生。先从你喜欢的方式，走进这个世界。</p>
        <div className="ps-welcome-actions">
          <Link to="/register?entry=own_pet" className="ps-welcome-action ps-welcome-action--primary">带我的宠物来 <span aria-hidden="true">↗</span></Link>
          <Link to="/world#residents" className="ps-welcome-action ps-welcome-action--secondary">先认识星球居民 <span aria-hidden="true">→</span></Link>
        </div>
        <Link to="/login" className="ps-welcome-login">已经有家了？登录</Link>
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
      <span className="ps-selected-resident__portrait">{selected.data.profile.avatar_url ? <img src={selected.data.profile.avatar_url} alt="" /> : selected.data.profile.display_name.slice(0, 1)}</span>
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
      className="ps-stack"
      onSubmit={(e) => {
        e.preventDefault();
        submit.mutate();
      }}
    >
      <div className="ps-field">
        <label htmlFor="username">用户名</label>
        <input
          id="username"
          className="ps-input"
          autoComplete="username"
          autoCapitalize="none"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          minLength={3}
          maxLength={32}
          pattern="[A-Za-z0-9_.\-]{3,32}"
          title="3–32 位字母、数字、下划线、点或短横线"
          required
        />
      </div>
      <div className="ps-field">
        <label htmlFor="password">密码</label>
        <input
          id="password"
          className="ps-input"
          type="password"
          autoComplete={kind === "register" ? "new-password" : "current-password"}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          minLength={kind === "register" ? 8 : 1}
          maxLength={128}
          required
        />
        {kind === "register" ? <span className="ps-muted">至少 8 位。目前没有邮箱找回，请记好密码。</span> : null}
      </div>
      <Button type="submit" variant="primary" block loading={submit.isPending}>
        {kind === "register" ? "注册" : "登录"}
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
    <Page bare className="ps-entry-page">
      <TopBar title="注册" back={back} />
      <EntryHeading step={1} kicker="入住准备 · 01 / 04" title={entry?.kind === "invite" ? "把这封邀请，留在这里" : entry?.kind === "adopt" ? "把刚才的相遇，留在这里" : "从这里，走进 TA 的生活"} description={entry?.kind === "invite" ? "先建立账号。邀请会留作待确认事项，是否加入这个家仍由你决定。" : entry?.kind === "adopt" ? "先建立账号。刚才选中的居民会被记住，领养仍要由你登录后亲自确认。" : "先为自己建立一个账号。你可以带自己的宠物入住，也可以在星球上认识新伙伴。"} />
      {entry?.kind === "adopt" && entry.pet_id ? <SelectedResidentBanner petId={entry.pet_id} /> : null}
      {entry?.kind === "invite" && entry.invite_token ? <SelectedInviteBanner token={entry.invite_token} /> : null}
      <Card className="ps-entry-card">
        <AuthForm kind="register" />
      </Card>
      <p className="ps-entry-support">注册只建立账号，不会自动领养居民或加入家庭；之后都由你确认。</p>
      <p className="ps-entry-support">
        已有账号？<Link to={`/login${suffix}`}>去登录</Link>
      </p>
    </Page>
  );
}

export function LoginPage() {
  const [params] = useSearchParams();
  const entry = entryFromParams(params);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const back = entry?.kind === "invite" && entry.invite_token ? `/join?invite=${encodeURIComponent(entry.invite_token)}` : entry?.kind === "adopt" && entry.pet_id ? `/world/residents/${encodeURIComponent(entry.pet_id)}` : "/welcome";
  return (
    <Page bare className="ps-entry-page">
      <TopBar title="登录" back={back} />
      <EntryHeading kicker="欢迎回来" title="家还在这里等你" description="登录后继续照顾 TA。领养和加入家庭都需要你自己确认，不会因为登录自动发生。" />
      {entry?.kind === "adopt" && entry.pet_id ? <SelectedResidentBanner petId={entry.pet_id} /> : null}
      {entry?.kind === "invite" && entry.invite_token ? <SelectedInviteBanner token={entry.invite_token} /> : null}
      <Card className="ps-entry-card">
        <AuthForm kind="login" />
      </Card>
      <p className="ps-entry-support">
        还没有账号？<Link to={`/register${suffix}`}>去注册</Link>
      </p>
    </Page>
  );
}

/** 入住激活：与接待分开。主人明确选择是否让 TA 的旅行到访生成公开动态（默认不公开）。 */
export function MoveInPage() {
  const { session, pets, reception } = useServices();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const state = useSessionState();
  const [publicPosts, setPublicPosts] = useState(false);
  const [habitat, setHabitat] = useState<HabitatKind | null>(null);
  const petId = state.data?.onboarding?.pet_id ?? null;
  const profile = useQuery({ queryKey: queryKeys.petProfile(petId ?? "-"), queryFn: () => pets.publicProfile(petId!), enabled: Boolean(petId) });
  const welcome = useQuery({ queryKey: queryKeys.homeWelcome(petId ?? "-"), queryFn: () => reception.homeWelcome(petId!), enabled: Boolean(petId && !state.data?.onboarding?.reception_skipped), retry: false });
  const place = useQuery({ queryKey: queryKeys.homePlace(petId ?? "-"), queryFn: () => session.homePlace(petId), enabled: Boolean(petId), retry: false });
  const moveIn = useMutation({
    mutationFn: () => session.moveIn(publicPosts, habitat, petId),
    onSuccess: (onboarding) => {
      queryClient.setQueryData<SessionState | undefined>(queryKeys.session, (prev) => (prev ? { ...prev, onboarding } : prev));
      void queryClient.invalidateQueries({ queryKey: queryKeys.home });
      void queryClient.invalidateQueries({ queryKey: ["households"] });
      // The choice is user-scoped and revalidated against /households before display.
      const userId = state.data?.user?.user_id;
      if (userId && petId) {
        try { sessionStorage.setItem(`petsoul:current-pet:${userId}`, petId); } catch { /* still usable without storage */ }
      }
      navigate("/home", { replace: true });
    },
  });

  if (env.dataMode === "fixture") return <Navigate to="/home" replace />;
  if (state.isPending) return <LoadingState lines={2} />;
  if (state.isError) return <ErrorState error={state.error} onRetry={() => void state.refetch()} />;
  if (!state.data.authenticated) return <Navigate to="/welcome" replace />;
  const step = state.data.onboarding?.step;
  if (step !== "ready_to_move_in" && step !== "reception_optional") return <Navigate to={onboardingRoute(state.data.onboarding)} replace />;

  return (
    <Page bare className="ps-entry-page">
      <TopBar title="入住" subtitle="布置好了，就一起开始生活" />
      <EntryHeading step={4} kicker="入住准备 · 04 / 04" title="欢迎来到你们的家" description="从这一刻起，家园、信箱和 TA 的旅途会按真实状态慢慢展开。" />
      <div className="ps-stack">
        <Card className="ps-row ps-entry-card">
          {profile.data ? (
            <span className="ps-movein-portrait" aria-label={profile.data.avatar_url ? `${profile.data.display_name}的当前头像` : `${profile.data.display_name}暂时没有照片`}>
              {profile.data.avatar_url ? <img src={profile.data.avatar_url} alt="" /> : profile.data.display_name.slice(0, 1)}
            </span>
          ) : null}
          <div style={{ flex: 1 }}>
            <h2 className="ps-h2">{profile.data?.display_name ?? "TA"} 准备好搬进来了</h2>
            <div className="ps-muted">{welcome.data ? welcome.data.greeting : "入住后 TA 会先在家里熟悉环境、守着菜园；你可以在旅途里提出建议，TA 也有自己的节奏。"}</div>
          </div>
        </Card>
        <Card className="ps-entry-card">
          <div className="ps-section-title" style={{ marginTop: 0 }}>家的位置</div>
          {place.isPending ? <LoadingState lines={1} label="正在确认可以安家的地方…" /> : place.isError ? <ErrorState error={place.error} onRetry={() => void place.refetch()} /> : place.data ? <>
            <p className="ps-entry-support ps-place-note">{place.data.place.chosen ? `这个家已在 ${place.data.place.display}，新伙伴会住在同一处。` : `暂不选择会使用当前默认住处：${place.data.place.display}。`}</p>
            {!place.data.place.chosen && place.data.can_change ? <div className="ps-place-options" role="group" aria-label="选择家的环境">
              {place.data.options.filter((option) => option.open).map((option) => <button key={option.habitat} type="button" className={`ps-place-option${habitat === option.habitat ? " is-selected" : ""}`} aria-pressed={habitat === option.habitat} onClick={() => setHabitat((old) => old === option.habitat ? null : option.habitat)}>
                <strong>{option.label}</strong><small>{option.examples.length ? `可能落在 ${option.examples.join("、")}` : "由星球安排片区"}</small>
              </button>)}
            </div> : null}
            {!place.data.place.chosen && place.data.options.some((option) => option.open === false) ? <span className="ps-muted ps-place-unavailable">其余环境尚未开放，不会提前展示为可入住。</span> : null}
          </> : null}
        </Card>
        <Card className="ps-entry-card">
          <div className="ps-section-title" style={{ marginTop: 0 }}>
            星球圈公开范围
          </div>
          <label className="ps-check">
            <input type="checkbox" checked={publicPosts} onChange={(e) => setPublicPosts(e.target.checked)} />
            <span>
              允许 TA 旅行到访时在星球圈发公开动态
              <span className="ps-muted" style={{ display: "block" }}>
                只发生在真实到访之后；你和 TA 的私密通讯、入住叮嘱永远不会被公开。之后可以在设置里随时改。
              </span>
            </span>
          </label>
        </Card>
        <Button variant="primary" block icon="home" loading={moveIn.isPending} disabled={place.isPending || place.isError} onClick={() => moveIn.mutate()}>
          入住，一起开始生活
        </Button>
        {moveIn.isError ? <ErrorState error={moveIn.error} /> : null}
        <p className="ps-entry-support">入住后的菜地、旅费与来信，以家园实时状态为准。</p>
      </div>
    </Page>
  );
}

const VISIBILITY: Array<{ id: string; label: string }> = [
  { id: "public", label: "所有人" },
  { id: "followers", label: "关注 TA 的宠物" },
  { id: "private", label: "只有我" },
];

function SettingsForm({ view }: { view: SettingsView }) {
  const { session } = useServices();
  const queryClient = useQueryClient();
  const [bio, setBio] = useState(view.bio ?? "");
  const save = useMutation({
    mutationFn: (patch: SettingsUpdateInput) => session.updateSettings(patch),
    onSuccess: (next) => {
      queryClient.setQueryData(queryKeys.settings, next);
      void queryClient.invalidateQueries({ queryKey: ["social"] });
    },
  });
  return (
    <>
      <Card>
        <div className="ps-section-title" style={{ marginTop: 0 }}>
          星球圈
        </div>
        <label className="ps-check">
          <input type="checkbox" checked={view.public_posts} disabled={save.isPending} onChange={(e) => save.mutate({ public_posts: e.target.checked })} />
          <span>
            TA 旅行到访后发公开动态
            <span className="ps-muted" style={{ display: "block" }}>
              关闭后新的到访不再公开；已发的动态可以在星球圈里撤下。
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
          意图判断层
        </div>
        <div className="ps-row">
          <Chip tone={view.intent_layer_mode === "off" ? "neutral" : "sky"}>{view.intent_layer_mode === "off" ? "关闭（默认）" : view.intent_layer_mode}</Chip>
          <span className="ps-muted">只调整回应措辞或给出可选控件，不会替你改行程、删记忆或公开内容。</span>
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
  const settings = useQuery({ queryKey: queryKeys.settings, queryFn: () => session.settings() });
  const logout = useMutation({
    mutationFn: () => session.logout(),
    onSettled: () => {
      queryClient.clear();
      navigate("/welcome", { replace: true });
    },
  });
  return (
    <Page>
      <TopBar title="账号与设置" back="/home" />
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
        {settings.isError ? <ErrorState error={settings.error} onRetry={() => void settings.refetch()} /> : settings.data ? <SettingsForm view={settings.data} /> : <LoadingState lines={2} />}
      </div>
    </Page>
  );
}
