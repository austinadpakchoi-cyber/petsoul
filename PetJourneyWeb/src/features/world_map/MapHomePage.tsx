/**
 * 地图首页原型（/map，批次 1“看见 TA 在生活”）。
 * - live：只读 W1 统一世界状态（`GET /world/state`，./worldState 只做形状转换），家里的每只宠物都上地图；守卫与主布局一致：未登录去欢迎页，入住未完成回入住步骤。
 *   请求带上当前宠物的 id（跨多个家时由它指明是哪个家）；还在读、读不出来时底部三栏和“我的”照样在（./MapStatusShell）。
 * - fixture：演示剧本（./demoScript 按需加载），页面顶部始终挂“演示剧本”，可调速度、跳到下一段。
 * 首屏只有一张主状态面板；小窝、菜园从左上进入；“我的”在右上头像；底部是新版三栏（地图 · 通讯器 · 回忆）的预览。
 * 同一个家只画一个小窝标记，在家的几只围着它错开（./homeCluster）。
 * 提醒合进面板（先后与收起见 ./panelNotes、./StatusPanel）：信箱（live，面板上这只自己的未读，见 ./homeNotes）> 驾校（TA 想学开车 / 学车进度 / 领证仪式，见 ./schoolNote，
 *   live 与演示都走驾校服务）> 旅行心愿（想去哪里 / 还差什么，见 journey/travelPlan/wishNote）> 系统提示（世界正在更新，live，也按面板上那只：后端按宠物算）。
 * 地图上点哪只只是本页看哪只，不改当前宠物；从面板进按宠物区分的页面（信箱提醒、捎句话、进小窝看看、家的标记、左上“进小窝”）时，
 *   先把当前宠物换成面板上这只再走（C84A-MAP-MAIL-SCOPE-01、第 0b 步）。
 * 进小窝再回来接着看：选中的宠物、是否跟着 TA、镜头、演示时钟存在 sessionStorage（./mapSession）；
 *   从面板进页面时换了当前宠物的，记录先改记到新的当前宠物名下，回来照样接着看（见 enterPet）；
 *   从小窝的“‹ 地图”“我出门啦”回来带 ?focus=<宠物 id>，改为选中并对准那只（./mapFocus）。
 * 真实地图取不到配置或加载失败时退回示意底图，状态照常显示——不拿假位置顶替。
 */
import { startTransition, useEffect, useRef, useState, type RefObject } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useCurrentHousehold, useOptionalCurrentHousehold } from "@/shared/session/householdContext";
import { useNow } from "@/shared/time/clock";
import { Icon, LoadingState, Page } from "@/shared/ui";
import { PetMoodAvatar } from "@/features/pets/PetMoodAvatar";
import { useWishNote } from "@/features/journey/travelPlan/wishNote";
import { AmapView, type MapStatus } from "./AmapView";
import { focusPetId, sceneFromWorldState } from "./worldState";
import { fetchMapConfig } from "./mapConfig";
import { acceptedFocus, FOCUS_PARAM } from "./mapFocus";
import { mapSessionScope, readMapSession, restoredView, resumeDemoClock, writeMapSession } from "./mapSession";
import { HomeMarkerView, PetMarkerView, PlaceMarkerView } from "./markers";
import { panelCopy } from "./copy";
import type { WorldPet, WorldScene } from "./model";
import { useHomeNotes } from "./homeNotes";
import { MapLoadError, MapStatusShell } from "./MapStatusShell";
import { arrangeNotes } from "./panelNotes";
import { useSchoolNote } from "./schoolNote";
import { StatusPanel } from "./StatusPanel";
import { PreviewTabBar } from "./PreviewTabBar";
import { WorldGate } from "./WorldGate";
import "./world-map.css";

type DemoModule = typeof import("./demoScript");

export function MapHomePage() {
  return <WorldGate>{env.dataMode === "live" ? <LiveMapHome /> : <DemoMapHome />}</WorldGate>;
}

function LiveMapHome() {
  const { world } = useServices();
  const { userId, pet, pets } = useCurrentHousehold();
  const state = useQuery({
    // 查询键只按用户：换当前宠物时 selectPet 会清掉这类缓存，随后按新的那只重读。
    queryKey: queryKeys.worldStateFor(userId ?? "-"),
    // 知道当前宠物就带上它的 id（跨多个家时由它指明是哪个家）；W1 照旧给这个家的全部宠物。
    queryFn: ({ signal }) => world.state(pet?.pet_id, signal),
    enabled: Boolean(userId),
    // 按后端给的缓存时长刷新（纯读，不推进世界）。
    refetchInterval: (query) => Math.max(10, query.state.data?.cache_seconds ?? 15) * 1000,
  });
  const nowMs = useNow(500);
  if (state.isPending) {
    return (
      <MapStatusShell>
        <LoadingState lines={2} label="正在找 TA 在哪…" />
      </MapStatusShell>
    );
  }
  if (state.isError) {
    return (
      <MapStatusShell>
        <MapLoadError error={state.error} onRetry={() => void state.refetch()} />
      </MapStatusShell>
    );
  }
  // W1 没给证件照小头像时，头像退回家庭资料里的照片（见 worldPetFromState）。位置与状态全部来自 W1。
  const scene = sceneFromWorldState(state.data, new Map(pets.map(({ pet: p }) => [p.pet_id, p.photo_url ?? null])));
  return <MapHomeView scene={scene} nowMs={nowMs} demo={null} focusId={focusPetId(scene, pet?.pet_id)} />;
}

/* ---------------- 演示剧本（fixture） ---------------- */

interface DemoClock {
  now: number;
  speed: number;
  paused: boolean;
  dayStart: number;
  setSpeed(speed: number): void;
  togglePause(): void;
  next(): void;
}

const DEMO_SPEEDS = [1, 60, 240] as const;

function useFrameTick(fps: number) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const frame = 1000 / fps;
    if (typeof requestAnimationFrame !== "function") {
      const id = window.setInterval(() => setTick((t) => t + 1), frame);
      return () => window.clearInterval(id);
    }
    let raf = 0;
    let last = 0;
    const loop = (t: number) => {
      if (t - last >= frame) {
        last = t;
        setTick((x) => x + 1);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [fps]);
}

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function useDemoClock(demo: DemoModule | null, scope: string): DemoClock {
  // 进小窝再回来：接着上次的演示时钟走（离开的这段按倍速补上），倍速与暂停也照旧；第一次打开或读不到时从默认开始。
  const [initial] = useState(() => {
    const saved = readMapSession(scope).demo;
    if (saved && (DEMO_SPEEDS as readonly number[]).includes(saved.speed)) {
      return { speed: saved.speed, paused: saved.paused, dayStart: saved.dayStart, demoNow: resumeDemoClock(saved, Date.now()) };
    }
    const wall = Date.now();
    // 一天从“现在的 17 分钟前”开始：打开几秒就能看到 TA 出门。
    return { speed: 60, paused: false, dayStart: wall - 17 * 60_000, demoNow: wall };
  });
  const [speed, setSpeedState] = useState<number>(initial.speed);
  const [paused, setPaused] = useState(initial.paused);
  const { dayStart } = initial;
  const anchor = useRef({ wall: performance.now(), demo: initial.demoNow });
  useFrameTick(prefersReducedMotion() ? 4 : 20);
  const now = paused ? anchor.current.demo : anchor.current.demo + (performance.now() - anchor.current.wall) * speed;
  // 记下锚点（换算成真实时刻）与走法：之后任何时候都能按它算出演示时钟读数。
  const persist = (nextSpeed: number, nextPaused: boolean) => {
    const { wall, demo: demoAt } = anchor.current;
    writeMapSession(scope, { demo: { dayStart, demoAt, wallAt: Date.now() - (performance.now() - wall), speed: nextSpeed, paused: nextPaused } });
  };
  const rebase = (demoMs: number, nextSpeed: number, nextPaused: boolean) => {
    anchor.current = { wall: performance.now(), demo: demoMs };
    persist(nextSpeed, nextPaused);
  };
  useEffect(() => {
    persist(initial.speed, initial.paused);
    // 只在挂载时记一次起点；之后每次换速、暂停、跳段都会重记。
  }, []);
  return {
    now,
    speed,
    paused,
    dayStart,
    setSpeed(next) {
      rebase(now, next, paused);
      setSpeedState(next);
    },
    togglePause() {
      rebase(now, speed, !paused);
      setPaused(!paused);
    },
    next() {
      if (!demo) return;
      const { end } = demo.segmentAt(now - dayStart);
      // 跳到下一次变化前 2 秒（按当前倍速），能看到变化本身。
      rebase(Math.max(now, dayStart + end - 2000 * speed), speed, paused);
    },
  };
}

function DemoMapHome() {
  const scope = mapSessionScope(useOptionalCurrentHousehold()?.userId ?? null);
  const [demo, setDemo] = useState<DemoModule | null>(null);
  useEffect(() => {
    let alive = true;
    void import("./demoScript").then((mod) => {
      if (alive) setDemo(mod);
    });
    return () => {
      alive = false;
    };
  }, []);
  const clock = useDemoClock(demo, scope);
  if (!demo) {
    return (
      <Page>
        <LoadingState lines={2} label="正在准备演示剧本…" />
      </Page>
    );
  }
  const scene = demo.demoScene(clock.now, clock.dayStart);
  return <MapHomeView scene={scene} nowMs={clock.now} demo={clock} />;
}

function DemoBar({ clock }: { clock: DemoClock }) {
  return (
    <div className="ps-wmap-demo" role="group" aria-label="演示剧本控制">
      <span className="ps-wmap-demo__tag">演示剧本 · 不是真实数据</span>
      <div className="ps-wmap-demo__controls">
        <button type="button" onClick={clock.togglePause} aria-label={clock.paused ? "继续" : "暂停"}>
          <Icon name={clock.paused ? "play" : "pause"} size={14} />
        </button>
        {DEMO_SPEEDS.map((s) => (
          <button key={s} type="button" aria-pressed={clock.speed === s} onClick={() => clock.setSpeed(s)}>
            {s}×
          </button>
        ))}
        <button type="button" onClick={clock.next}>
          下一段 <Icon name="chevron" size={12} />
        </button>
      </div>
    </div>
  );
}

/* ---------------- 共用的地图首页布局 ---------------- */

type Scope = "nearby" | "global" | "friends" | "mine";
const SCOPES: Array<{ id: Scope; label: string; open: boolean }> = [
  { id: "nearby", label: "附近", open: false },
  { id: "global", label: "全球", open: false },
  { id: "friends", label: "朋友", open: false },
  { id: "mine", label: "只看自己", open: true },
];

function ScopeControl() {
  const [open, setOpen] = useState(false);
  return (
    <div className="ps-wmap-scope">
      <button type="button" className="ps-wmap-fab" aria-expanded={open} aria-label="显示范围：只看自己" onClick={() => setOpen((o) => !o)}>
        <Icon name="planet" size={20} />
      </button>
      {open ? (
        <div className="ps-wmap-scope__menu" role="menu" aria-label="显示范围">
          {SCOPES.filter((s) => s.open).map((s) => (
            <button key={s.id} type="button" role="menuitemradio" aria-checked={s.id === "mine"} onClick={() => setOpen(false)}>
              <span>{s.label}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** 底部面板 + 标签栏的实际高度写到 --wmap-bottom：高德 Logo 与版权要一直露在面板上方（使用条款要求可见）。 */
function useBottomInset(rootRef: RefObject<HTMLDivElement | null>, bottomRef: RefObject<HTMLDivElement | null>): number {
  const [inset, setInset] = useState(0);
  useEffect(() => {
    const root = rootRef.current;
    const bottom = bottomRef.current;
    if (!root || !bottom) return;
    const apply = () => {
      const height = Math.round(bottom.getBoundingClientRect().height);
      root.style.setProperty("--wmap-bottom", `${height}px`);
      setInset(height);
    };
    apply();
    if (typeof ResizeObserver !== "function") return;
    const observer = new ResizeObserver(apply);
    observer.observe(bottom);
    return () => observer.disconnect();
  }, [rootRef, bottomRef]);
  return inset;
}

function MapFallback({ pet, status }: { pet: WorldPet | null; status: MapStatus }) {
  const reason = status === "loading" ? "正在打开地图…" : "地图暂时没连上，TA 的状态照常更新。";
  return (
    <div className="ps-wmap-canvas ps-wmap-fallback" data-basemap="schematic">
      {pet ? (
        <div className="ps-wmap-fallback__pet">
          <PetMoodAvatar name={pet.name} photoUrl={pet.photoUrl} mood={pet.activity.pose} size={64} />
        </div>
      ) : null}
      <p className="ps-wmap-fallback__note" role="status">
        {reason}
      </p>
    </div>
  );
}

function MapHomeView({ scene, nowMs, demo, focusId = null }: { scene: WorldScene; nowMs: number; demo: DemoClock | null; focusId?: string | null }) {
  const navigate = useNavigate();
  const configQuery = useQuery({ queryKey: ["world-map", "config"], queryFn: ({ signal }) => fetchMapConfig(signal), staleTime: Infinity, retry: false });
  const config = configQuery.data ?? null;
  const household = useOptionalCurrentHousehold();
  const scope = mapSessionScope(household?.userId ?? null);
  // 从小窝回来带 ?focus=<宠物 id>：只认当前家庭里的宠物（live 看当前家庭的名单，演示看演示场景里自己家的）。
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedFocus = searchParams.get(FOCUS_PARAM);
  const familyIds = env.dataMode === "live" ? new Set((household?.household?.pets ?? []).map((p) => p.pet_id)) : null;
  const focusRequest = acceptedFocus(requestedFocus, scene, familyIds);
  // 进小窝再回来：同一只当前宠物下，接着上次的选中、跟随与镜头；换了当前宠物就从头对准新的那只。
  // 带着认得的 ?focus= 回来：选中并跟随那只，不接上次存下的镜头（方案第 5 节“回到地图并对准 TA”）。
  const [restored] = useState(() => (focusRequest ? { selectedId: focusRequest, following: true, camera: null } : restoredView(readMapSession(scope), focusId)));
  const [status, setStatus] = useState<MapStatus>("loading");
  const [following, setFollowing] = useState(restored.following);
  const [recenterToken, setRecenterToken] = useState(0);
  const [openPlace, setOpenPlace] = useState<string | null>(null);
  // 默认看当前选中的那只（家里多只宠物都在地图上）；点别的头像就切到那只。
  const me = scene.pets.find((p) => p.petId === focusId) ?? scene.pets[0] ?? null;
  const [selectedId, setSelectedId] = useState<string | null>(restored.selectedId);
  const selected = scene.pets.find((p) => p.petId === selectedId) ?? me;
  // “回来接着看”的记录记在哪只当前宠物名下：平时就是 focusId；从面板进页面换了当前宠物时，由 enterPet 先改成新的那只。
  const sessionFocusRef = useRef(focusId);
  useEffect(() => {
    sessionFocusRef.current = focusId;
  }, [focusId]);
  useEffect(() => {
    writeMapSession(scope, { view: { focusId, selectedId, following } });
  }, [scope, focusId, selectedId, following]);
  useEffect(() => {
    if (requestedFocus === null) return;
    // 已经在地图上又收到 ?focus=：同样选中、跟随，并把镜头推到那只身上。
    if (focusRequest) {
      setSelectedId(focusRequest);
      setFollowing(true);
      setRecenterToken((t) => t + 1);
    }
    // 处理完就从地址里去掉（replace，不留历史）：刷新、前进后退都不会再触发；认不出的值也一样去掉、不理会。
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete(FOCUS_PARAM);
        return next;
      },
      { replace: true },
    );
  }, [requestedFocus]);
  // 提醒按来源先后排（信箱 > 驾校 > 旅行心愿 > 系统提示）；只关于某只宠物的（信箱、驾校、心愿、世界正在更新）在面板显示别的宠物时不出现。
  // 信箱和“世界正在更新”读面板上这只自己的家园快照（./homeNotes）：换看另一只就读那只的，读到之前不出这两行，不拿当前宠物的顶替。
  const homeNotes = useHomeNotes(selected?.petId ?? null);
  const wish = useWishNote();
  const school = useSchoolNote();
  const panelNotes = arrangeNotes([...homeNotes, wish, school], selected?.petId ?? null);
  // 点标记只换本页看哪只，不调 selectPet（它会清掉世界状态缓存，地图要闪一下重读）。
  // 从面板进按宠物区分的页面时，才把当前宠物换成面板上这只：目标页可能是另一个家庭上下文实例，靠 sessionStorage 接上，所以在跳转之前换；已经是当前宠物就不换。
  // selectPet 当场写 sessionStorage、清缓存；它的界面更新标成过渡，和随后的跳转（路由也按过渡提交）一起落地——
  // 否则地图会先按清空的缓存再画一次（闪出“正在找 TA 在哪…”、多读一遍世界状态和家园快照）才离开。
  // 回来时这只就是当前宠物了：先把“回来接着看”的记录改记在它名下（选中、跟随、以及卸载时报上来的镜头），
  // 回来接着这一眼，不当成“换了宠物”从头对准（./mapSession.restoredView 只认同一只当前宠物下存的）。
  const enterPet = (petId: string) => {
    // 与 selectPet 自己的判断一致（没有账号 / 已经是当前宠物 / 不是自己家的就不换）：不换的时候也不能改记“回来接着看”。
    if (!household?.userId || household.pet?.pet_id === petId || !household.pets.some(({ pet }) => pet.pet_id === petId)) return;
    sessionFocusRef.current = petId;
    writeMapSession(scope, { view: { focusId: petId, selectedId: selected?.petId ?? petId, following } });
    startTransition(() => household.selectPet(petId));
  };

  const locate = () => {
    setFollowing(true);
    setRecenterToken((t) => t + 1);
  };
  const petLabel = (pet: WorldPet) => panelCopy(pet, nowMs, null).headline;
  const showMap = config?.available && status !== "failed";
  const rootRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const bottomInset = useBottomInset(rootRef, bottomRef);

  return (
    <div className={`ps-wmap${demo ? " is-demo" : ""}`} ref={rootRef}>
      {config && showMap ? (
        <AmapView
          config={config}
          pets={scene.pets}
          nowMs={nowMs}
          followPetId={following ? selected?.petId ?? null : null}
          recenterToken={recenterToken}
          bottomInset={bottomInset}
          initialCamera={restored.camera}
          onUserMove={() => setFollowing(false)}
          onStatus={(s) => setStatus(s)}
          onCameraChange={(camera) => writeMapSession(scope, { camera: { focusId: sessionFocusRef.current, ...camera } })}
          renderPet={(pet) => (
            <PetMarkerView
              key={`${pet.activity.phase}-${pet.activity.since ?? 0}`}
              pet={pet}
              selected={pet.petId === selected?.petId}
              label={petLabel(pet)}
              onSelect={() => {
                setSelectedId(pet.petId);
                locate();
              }}
            />
          )}
          renderHome={(owner, residents) => {
            // 同一个家只画一个小窝标记（./homeCluster）：名字和进哪只的视角都跟着面板上那只（和面板的“进小窝看看”一致）；
            // 面板上那只不住这里时，才用这个家的第一只。
            const who = selected && residents.some((p) => p.petId === selected.petId) ? selected : owner;
            return (
              <HomeMarkerView
                petName={who.name}
                occupied={who.activity.phase === "home"}
                onOpen={() => {
                  enterPet(who.petId);
                  navigate("/home?from=map");
                }}
              />
            );
          }}
          renderPlace={(pet) =>
            pet.activity.place ? (
              <PlaceMarkerView name={pet.activity.place.name} open={openPlace === pet.petId} onToggle={() => setOpenPlace((o) => (o === pet.petId ? null : pet.petId))} />
            ) : null
          }
        />
      ) : (
        <MapFallback pet={me} status={config ? (config.available ? status : "failed") : "loading"} />
      )}

      <header className="ps-wmap-top">
        <div className="ps-wmap-top__left">
          {/* 和面板上的“进小窝看看”一样跟着面板上那只：先把当前宠物换成它再跳（第 0b 步）。 */}
          <Link
            className="ps-wmap-fab"
            to="/home?from=map"
            aria-label="进小窝"
            onClick={() => {
              if (selected) enterPet(selected.petId);
            }}
          >
            <Icon name="home" size={20} />
          </Link>
          <Link className="ps-wmap-fab" to="/garden" aria-label="去菜园">
            <Icon name="sprout" size={20} />
          </Link>
        </div>
        {demo ? <DemoBar clock={demo} /> : null}
        <Link className="ps-wmap-me" to="/me" aria-label="我的">
          <Icon name="user" size={20} />
        </Link>
      </header>

      <div className="ps-wmap-side">
        <button type="button" className={`ps-wmap-fab${following ? " is-on" : ""}`} aria-label="定位 TA" aria-pressed={following} onClick={locate}>
          <Icon name="locate" size={20} />
        </button>
        {/* 只有一种范围真能用时不出现开关（不放“即将开放”这类没有后端支撑的占位）；W2 开放附近 / 全球 / 朋友后自动出现。 */}
        {SCOPES.filter((s) => s.open).length > 1 ? <ScopeControl /> : null}
      </div>

      <div className="ps-wmap-bottom" ref={bottomRef}>
        {selected ? <StatusPanel pet={selected} nowMs={nowMs} notes={panelNotes} onLocate={locate} onEnter={enterPet} /> : null}
        <PreviewTabBar />
      </div>
    </div>
  );
}
