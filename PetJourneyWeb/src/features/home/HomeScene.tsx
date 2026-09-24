import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
  type RefObject,
} from "react";
import { Link, useLocation, useNavigate, useSearchParams, type Location } from "react-router";
import type { CharacterState, HomeSnapshot, PetPresence, PlotSummary } from "@/shared/contracts";
import { Button, Icon, Sheet, type IconName } from "@/shared/ui";
import room from "./assets/living/room-base.webp";
import cup from "./assets/living/ordinary-cup.webp";
import { GardenBed } from "@/features/farm/GardenScene";
// 菜园入口里的 GardenBed：几何在 garden-bed.css（GardenScene 自己引入），地块基础样式、摇摆 / 成熟动画与“减少动态效果”在 farm.css。
import "@/features/farm/farm.css";
import { mapFocusHref } from "@/features/world_map/mapFocus";
import { characterNote, PetFigure, sceneAsset } from "./PetFigure";

/**
 * 庭院底图：UI-ASSET-008 v1 长图（r7k，780×1690，交付单 docs/coordination/ui-assets/deliveries/UI-ASSET-008-v1.md）。
 * 上面 780×1320 与原图同位，下面多出的 370px 只是静景：热点、TA 的站位、以后的环境视频都仍按原 780×1320 的框算，
 * 场景盒子照旧 390:610（盒子里显示第 50–1270 行，和原图 cover 居中时一样），多出来的在盒子下面接着铺（.ps-living-ground）。
 * 屋内的长图接缝没过审，屋内仍用原图 + [过渡方案] 垫层。
 */
const COURTYARD_TALL = "/ui-assets/UI-ASSET-008/v1/courtyard-base-tall.webp";

/** Only the isolated internal test harness supplies a character. No default pet identity. */
export const LivingCharacterContext = createContext<{
  petId: string;
  rest: string;
  sit: string;
  bag: string;
} | null>(null);

/**
 * 院子里菜园入口露出的那一块地：和菜园页同一个 GardenBed——开垦土块，作物的入土点对准垄沟，前景土层挡住入土的那一截，
 * 成熟时的光由代码加（样式在 farm 的 garden-bed.css / farm.css）。外面这层仍是原来 92px 高的框，入口按钮的位置和大小不变。
 */
export function PlotArt({ plot }: { plot: PlotSummary }) {
  return (
    <span className="ps-living-plot-art" aria-hidden="true">
      <GardenBed cropKey={plot.crop_key} stage={plot.stage} />
    </span>
  );
}

/**
 * 这一页之前有没有站内的一页：与顶栏返回同一个判断（直接打开时，初始条目的 key 是 "default"）。
 * 浏览器里再核一次 React Router 记在 history.state 里的序号 idx：直接打开后换过房间（replace 会换 key）仍算没有来路，
 * 不然后退会退出站点。内存路由（测试）没有这个序号，只按 key 判断。
 */
function hasInAppPrevious(location: Location): boolean {
  if (location.key === "default") return false;
  const idx = (window.history.state as { idx?: unknown } | null)?.idx;
  return typeof idx === "number" ? idx > 0 : true;
}

/**
 * 小窝是地图下面的二级页：左上角始终能回到地图（方案第 5 节），并且不多压一条历史（手机返回键不会在地图和小窝之间来回跳）：
 * - 从地图进来（地址带 from=map，且站内有来路）：直接后退回到地图那一条，地图自己接上次选中的宠物和镜头；
 * - 直接打开、没有站内来路、或不是从地图来的：去 /map?focus=<当前宠物>（对准 TA），用 replace 换掉小窝这一条；
 *   还不知道是哪只时就是普通的地图首页。
 * 链接的地址始终是 /map?focus=…：新标签页打开、读屏都以它为准；带修饰键、中键的点按交给浏览器。
 * “我出门啦”便笺的意思是“去看 TA 走到哪了”，照旧跳 /map?focus=，不走这里。
 */
export function HomeBackLink({ inline = false, petId = null }: { inline?: boolean; petId?: string | null }) {
  const location = useLocation();
  const navigate = useNavigate();
  const backToMap = new URLSearchParams(location.search).get("from") === "map" && hasInAppPrevious(location);
  return (
    <Link
      to={mapFocusHref(petId)}
      replace
      className={`ps-home-back${inline ? " is-inline" : ""}`}
      aria-label="回到地图"
      onClick={(event) => {
        if (!backToMap || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        navigate(-1);
      }}
    >
      <Icon name="back" size={16} />
      地图
    </Link>
  );
}

/** 有事实表明 TA 在外面的几种状态；unknown / not_activated 不算，不替 TA 写“出门啦”。 */
const AWAY_PRESENCE: ReadonlySet<PetPresence> = new Set<PetPresence>(["in_transit", "at_destination", "visiting", "returning"]);

/* ---------- 第一次进来：可点的东西依次轻闪一次；按宠物记在本机，之后不再打扰 ---------- */
const HINT_START_MS = 400;
const HINT_STEP_MS = 480;
/** 与 home.css 里 `ps-home-hint` 的时长保持一致。 */
const HINT_GLOW_MS = 1100;
const introKey = (petId: string) => `petsoul:home-intro:${petId}`;

function introSeen(petId: string): boolean {
  try {
    return window.localStorage.getItem(introKey(petId)) === "1";
  } catch {
    return false; // 读不到就当第一次
  }
}

function rememberIntro(petId: string) {
  try {
    window.localStorage.setItem(introKey(petId), "1");
  } catch {
    // 记不住只会让下次进来再提示一次，不影响使用
  }
}

/** 暂停时（到家时刻还开着）先不提示、也不记；同一次停留里只试一次，换房间不会重播。 */
function useFirstVisitHint(petId: string, paused: boolean, count: number): boolean {
  const [hintFor, setHintFor] = useState<string | null>(null);
  const tried = useRef(new Set<string>());
  useEffect(() => {
    if (paused || count === 0 || tried.current.has(petId)) return;
    tried.current.add(petId);
    if (introSeen(petId)) return;
    rememberIntro(petId);
    setHintFor(petId);
  }, [petId, paused, count]);
  useEffect(() => {
    if (!hintFor) return;
    const timer = setTimeout(() => setHintFor(null), HINT_START_MS + Math.max(0, count - 1) * HINT_STEP_MS + HINT_GLOW_MS + 200);
    return () => clearTimeout(timer);
  }, [hintFor, count]);
  return hintFor === petId;
}

/* ---------- 点到才冒出来的小气泡：名字 + 能做的事 ---------- */
/** 气泡冒在物件的哪一侧（放不下时翻到另一侧）。 */
type BubbleSide = "top" | "bottom" | "left" | "right";
type ThingKey = "door" | "cabinet" | "pet" | "memento" | "mail" | "garden";
type RailKey = "rail-photo" | "rail-mail";
type OpenKey = ThingKey | RailKey;
const BUBBLE_GAP = 8;
const BUBBLE_EDGE = 8;

/**
 * 把气泡放在物件旁边，并收进场景里（场景会裁掉溢出的部分）；放不下就翻到另一侧。
 * 和左侧小图标同一高度时不压住它们（窄屏上收藏柜的气泡会往左伸到小图标上）。
 */
function placeBubble(scene: DOMRect, anchor: DOMRect, bubble: DOMRect, place: BubbleSide, avoid: DOMRect | null) {
  const { width: w, height: h } = bubble;
  let left: number;
  let top: number;
  if (place === "top" || place === "bottom") {
    left = anchor.left + anchor.width / 2 - w / 2;
    top = place === "top" ? anchor.top - BUBBLE_GAP - h : anchor.bottom + BUBBLE_GAP;
    if (place === "top" && top < scene.top + BUBBLE_EDGE) top = anchor.bottom + BUBBLE_GAP;
    if (place === "bottom" && top + h > scene.bottom - BUBBLE_EDGE) top = anchor.top - BUBBLE_GAP - h;
  } else {
    top = anchor.top + anchor.height / 2 - h / 2;
    left = place === "left" ? anchor.left - BUBBLE_GAP - w : anchor.right + BUBBLE_GAP;
    if (place === "left" && left < scene.left + BUBBLE_EDGE) left = anchor.right + BUBBLE_GAP;
    if (place === "right" && left + w > scene.right - BUBBLE_EDGE) left = anchor.left - BUBBLE_GAP - w;
  }
  top = Math.max(scene.top + BUBBLE_EDGE, Math.min(top, scene.bottom - BUBBLE_EDGE - h));
  const besideRail = avoid && top < avoid.bottom && top + h > avoid.top;
  const minLeft = besideRail ? avoid.right + BUBBLE_GAP : scene.left + BUBBLE_EDGE;
  left = Math.max(minLeft, Math.min(left, scene.right - BUBBLE_EDGE - w));
  return { left: Math.round(left - scene.left), top: Math.round(top - scene.top) };
}

function Bubble({
  id,
  name,
  detail,
  place,
  anchorKey,
  anchorOf,
  scene,
  rail,
  children,
}: {
  id: string;
  name: string;
  detail?: string | null;
  place: BubbleSide;
  anchorKey: string;
  anchorOf: (key: string) => HTMLElement | null;
  scene: RefObject<HTMLElement | null>;
  rail: RefObject<HTMLElement | null>;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [at, setAt] = useState<{ left: number; top: number } | null>(null);
  useLayoutEffect(() => {
    const measure = () => {
      const bubble = ref.current;
      const anchor = anchorOf(anchorKey);
      const area = scene.current;
      if (!bubble || !anchor || !area) return;
      const next = placeBubble(area.getBoundingClientRect(), anchor.getBoundingClientRect(), bubble.getBoundingClientRect(), place, rail.current?.getBoundingClientRect() ?? null);
      setAt((prev) => (prev && prev.left === next.left && prev.top === next.top ? prev : next));
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [anchorKey, anchorOf, scene, rail, place, name, detail]);
  return (
    <div ref={ref} id={id} role="group" aria-label={name} className="ps-home-bubble" style={at ? { left: at.left, top: at.top } : undefined}>
      <strong className="ps-home-bubble__name">{name}</strong>
      {detail ? <span className="ps-home-bubble__detail">{detail}</span> : null}
      <div className="ps-home-bubble__actions">{children}</div>
    </div>
  );
}

/**
 * 侧边小图标：本身就是入口（有地址、有无障碍名称）。鼠标悬停、键盘聚焦时冒出名字，点一下直接去；
 * 触屏没有悬停，第一下只冒出写着名字的小气泡，再点图标或气泡才去，点别处收起。
 */
function RailEntry({
  railKey,
  bubbleId,
  to,
  name,
  label,
  icon,
  dot = false,
  open,
  onReveal,
  register,
}: {
  railKey: RailKey;
  bubbleId: string;
  to: string;
  name: string;
  label: string;
  icon: IconName;
  dot?: boolean;
  open: boolean;
  onReveal: () => void;
  register: (key: OpenKey) => (el: HTMLElement | null) => void;
}) {
  const pointer = useRef<string | null>(null);
  return (
    <div className="ps-home-rail__item">
      <Link
        ref={register(railKey)}
        to={to}
        className="ps-home-rail__btn"
        aria-label={label}
        data-name={name}
        data-open={open ? "true" : undefined}
        onPointerDown={(event) => {
          pointer.current = event.pointerType;
        }}
        onClick={(event) => {
          const touch = pointer.current === "touch" || pointer.current === "pen";
          pointer.current = null;
          if (touch && !open) {
            event.preventDefault();
            onReveal();
          }
        }}
      >
        <Icon name={icon} size={20} />
        {/* 有新消息只挂一个小红点，不写数字；几条写在无障碍名称与信箱气泡里 */}
        {dot ? <span className="ps-home-rail__dot" aria-hidden="true" data-testid="home-rail-dot" /> : null}
      </Link>
      {open ? (
        <Link id={bubbleId} to={to} className="ps-home-rail__bubble">
          {name}
          <Icon name="chevron" size={14} />
        </Link>
      ) : null}
    </div>
  );
}

export function HomeScene({
  snapshot,
  worldCharacter = null,
  petActions = null,
  introPaused = false,
}: {
  snapshot: HomeSnapshot;
  worldCharacter?: CharacterState | null;
  petActions?: ReactNode;
  /** 到家时刻这类盖在上面的卡片还开着时为 true：第一次的轻闪提示等它关掉再放。 */
  introPaused?: boolean;
}) {
  const [params, setParams] = useSearchParams();
  const inside = params.get("room") === "inside";
  const home = snapshot.presence === "at_home";
  const away = AWAY_PRESENCE.has(snapshot.presence);
  const character = useContext(LivingCharacterContext);
  const sprite =
    snapshot.data_origin === "fixture" &&
    character?.petId === snapshot.pet.pet_id
      ? character
      : null;
  const [sitting, setSitting] = useState(false);
  const [petOpen, setPetOpen] = useState(false);
  // 正式宠物的场景形象只来自后端生效的角色版本；没有时退回原照肖像（临时），fixture 演示猫仍只在内部样例里出现。
  const figure = sprite ? null : worldCharacter;
  const note = characterNote(figure);
  const object = snapshot.welcome?.details.find(
    (detail) => detail.kind === "favorite_object",
  );
  const unread = snapshot.unread.messages;
  const name = snapshot.pet.name;
  // 菜园是二级页（/garden）：院子里只留一个入口，露出最值得看的那块地；状态点开才说。
  const ripe = snapshot.plots.filter((p) => p.stage === "ripe");
  const growing = snapshot.plots.filter((p) => p.stage === "growing");
  const open = snapshot.plots.filter((p) => p.stage === "empty" || p.stage === "harvested");
  const showcase = ripe[0] ?? growing[0] ?? snapshot.plots[0] ?? null;
  const gardenStatus = ripe.length ? `${ripe.length} 块熟了` : open.length ? "有空地可以种" : growing.length ? "都在长" : null;

  // 场景里此刻真有的、可以点的东西（按从上到下的顺序，也是第一次提示时依次轻闪的顺序）。
  const things: ThingKey[] = [
    inside ? "cabinet" : "door",
    ...(home ? (["pet"] as const) : []),
    ...(object ? (["memento"] as const) : []),
    ...(inside ? [] : (["mail", "garden"] as const)),
  ];
  const glowOrder: string[] = [...things];
  if (away) glowOrder.splice(1, 0, "note");
  const hinting = useFirstVisitHint(snapshot.pet.pet_id, introPaused, glowOrder.length);
  const glow = (key: string): { className: string; style?: CSSProperties } => {
    const order = glowOrder.indexOf(key);
    if (order < 0) return { className: "" };
    return {
      className: hinting ? " is-hinting" : "",
      style: { "--hint-delay": `${HINT_START_MS + order * HINT_STEP_MS}ms` } as CSSProperties,
    };
  };

  const sceneRef = useRef<HTMLElement>(null);
  const railRef = useRef<HTMLElement>(null);
  const triggers = useRef(new Map<string, HTMLElement>());
  // 每件东西一个固定的 ref 回调：气泡靠它找到自己挨着的那件东西，点别处收起时也靠它判断“是不是点在它身上”。
  const refCallbacks = useRef(new Map<string, (el: HTMLElement | null) => void>());
  const register = useCallback((key: OpenKey) => {
    let callback = refCallbacks.current.get(key);
    if (!callback) {
      callback = (el: HTMLElement | null) => {
        if (el) triggers.current.set(key, el);
        else triggers.current.delete(key);
      };
      refCallbacks.current.set(key, callback);
    }
    return callback;
  }, []);
  const anchorOf = useCallback((key: string) => triggers.current.get(key) ?? null, []);
  const bubblePrefix = useId();
  const bubbleId = (key: OpenKey) => `${bubblePrefix}${key}`;
  const [openKey, setOpenKey] = useState<OpenKey | null>(null);
  // 院子里场景自己有信箱（有未读时信封探出来），左侧的信箱小图标只在屋内出现。
  const railMail = inside;
  const present: OpenKey[] = [...things, "rail-photo", ...(railMail ? (["rail-mail"] as const) : [])];
  // 房间或 TA 的状态变了，原来那件东西不在了，气泡跟着消失。
  const openNow = openKey && present.includes(openKey) ? openKey : null;
  const toggle = (key: OpenKey) => setOpenKey((current) => (current === key ? null : key));

  useEffect(() => {
    if (!openNow) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      const trigger = triggers.current.get(openNow);
      const bubble = document.getElementById(`${bubblePrefix}${openNow}`);
      if (target && (trigger?.contains(target) || bubble?.contains(target))) return;
      setOpenKey(null);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpenKey(null);
      triggers.current.get(openNow)?.focus({ preventScroll: true });
    };
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [openNow, bubblePrefix]);

  const changeRoom = (value: boolean) => {
    setOpenKey(null);
    const next = new URLSearchParams(params);
    if (value) next.set("room", "inside");
    else next.delete("room");
    // 换房间不加浏览器历史：在地图上按返回不会回到小窝的某个房间（刷新仍停在当前房间）。
    setParams(next, { replace: true });
  };
  const hit = (key: ThingKey, label: string, shown: string) => ({
    ref: register(key),
    type: "button" as const,
    "aria-label": label,
    "aria-expanded": openNow === key,
    "aria-controls": openNow === key ? bubbleId(key) : undefined,
    "data-name": shown,
    onClick: () => toggle(key),
    style: glow(key).style,
  });
  const hitClass = (key: ThingKey, base: string) => `${base} ps-home-hit ps-home-glow${glow(key).className}`;
  const openPetSheet = () => {
    // 焦点先回到 TA 身上，面板收起时就会回到这里（气泡马上要消失）。
    triggers.current.get("pet")?.focus({ preventScroll: true });
    setOpenKey(null);
    setPetOpen(true);
  };

  const bubbleFor = (key: ThingKey) => {
    const common = { id: bubbleId(key), anchorKey: key, anchorOf, scene: sceneRef, rail: railRef };
    switch (key) {
      case "door":
        return (
          <Bubble {...common} name="屋门" place="right">
            <button type="button" className="ps-home-bubble__action" onClick={() => changeRoom(true)}>
              进屋看看 <Icon name="chevron" size={14} />
            </button>
          </Bubble>
        );
      case "cabinet":
        return (
          <Bubble {...common} name="收藏柜" place="left">
            <Link className="ps-home-bubble__action" to="/collection">
              看看收藏 <Icon name="chevron" size={14} />
            </Link>
          </Bubble>
        );
      case "pet":
        return (
          <Bubble {...common} name={name} detail={note ? `在家 · ${note}` : "在家"} place="bottom">
            <button type="button" className="ps-home-bubble__action" onClick={openPetSheet}>
              陪 TA 待一会儿 <Icon name="chevron" size={14} />
            </button>
          </Bubble>
        );
      case "memento":
        return object ? (
          <Bubble {...common} name={object.text} detail="你为 TA 留下的生活叮嘱" place="right">
            <Link className="ps-home-bubble__action" to="/onboarding/reception?mode=supplement">
              补充叮嘱 <Icon name="chevron" size={14} />
            </Link>
          </Bubble>
        ) : null;
      case "mail":
        return (
          <Bubble {...common} name="信箱" detail={unread > 0 ? `${unread} 条新消息` : "暂时没有新消息"} place="top">
            <Link className="ps-home-bubble__action" to="/communicator">
              打开信箱 <Icon name="chevron" size={14} />
            </Link>
          </Bubble>
        );
      case "garden":
        return (
          <Bubble {...common} name="菜园" detail={gardenStatus} place="top">
            <Link className="ps-home-bubble__action" to="/garden">
              去菜园 <Icon name="chevron" size={14} />
            </Link>
          </Bubble>
        );
    }
  };
  const openThing = openNow && openNow !== "rail-photo" && openNow !== "rail-mail" ? openNow : null;

  return (
    <>
    {/*
      * 场景往下的“地面”（场景是固定比例 390:610，高屏手机上场景下面会露出一截）。纯装饰、不接收点按；
      * 必须在 section 外面（section 自成层叠上下文，放里面会盖住下面的卡片）。
      * - 庭院：长图在场景盒子下面接着铺第 1270–1690 行，再往下补长图最底几行取的地面色（.ps-living-ground）。
      * - 屋内：[过渡方案] 屋内长图接缝没过审，仍是底图底部淡出 + 按底边取色垫一层（.ps-living-extend）；
      *   屋内真图到了，删掉这个元素和 home.css 里标了 [过渡方案] 的那一段。
      */}
    {inside ? (
      <div className="ps-living-extend is-inside" aria-hidden="true" data-testid="home-scene-extend" />
    ) : (
      <div className="ps-living-ground" aria-hidden="true" data-testid="home-scene-ground" style={{ "--ground-src": `url("${COURTYARD_TALL}")` } as CSSProperties} />
    )}
    <section
      ref={sceneRef}
      className={`ps-living-scene ${inside ? "is-inside" : "is-courtyard"}`}
      data-presence={snapshot.presence}
      data-hint={hinting ? "on" : undefined}
      aria-label={inside ? "共同的家·屋内" : "共同的家·庭院"}
    >
      <img
        className="ps-living-background"
        src={inside ? room : COURTYARD_TALL}
        alt=""
        fetchPriority="high"
      />
      <header className="ps-living-header">
        <HomeBackLink petId={snapshot.pet.pet_id} />
        <h1 className="ps-home-title">{name}的小窝</h1>
        <Link
          to="/market"
          className="ps-living-wallet"
          aria-label={`${snapshot.wallet.balance} 星币，查看仓库与集市`}
        >
          <Icon name="coin" size={17} />
          <strong data-testid="home-wallet">{snapshot.wallet.balance}</strong>
        </Link>
        <nav className="ps-living-switch" aria-label="家里的空间">
          <button
            type="button"
            aria-pressed={!inside}
            onClick={() => changeRoom(false)}
          >
            庭院
          </button>
          <button
            type="button"
            aria-pressed={inside}
            onClick={() => changeRoom(true)}
          >
            屋内
          </button>
        </nav>
      </header>
      <nav ref={railRef} className="ps-home-rail" aria-label="快捷入口">
        <RailEntry
          railKey="rail-photo"
          bubbleId={bubbleId("rail-photo")}
          to="/photos?scene=home"
          name="给 TA 拍一张"
          label="给 TA 拍一张"
          icon="camera"
          open={openNow === "rail-photo"}
          onReveal={() => setOpenKey("rail-photo")}
          register={register}
        />
        {railMail ? (
          <RailEntry
            railKey="rail-mail"
            bubbleId={bubbleId("rail-mail")}
            to="/communicator"
            name="信箱"
            label={unread > 0 ? `信箱，${unread} 条未读` : "信箱"}
            icon="mail"
            dot={unread > 0}
            open={openNow === "rail-mail"}
            onReveal={() => setOpenKey("rail-mail")}
            register={register}
          />
        ) : null}
      </nav>
      {inside ? (
        <button {...hit("cabinet", "收藏柜", "收藏柜")} className={hitClass("cabinet", "ps-home-spot ps-home-spot--cabinet")} />
      ) : (
        <button {...hit("door", "屋门", "屋门")} className={hitClass("door", "ps-home-spot ps-home-spot--door")} />
      )}
      {home ? (
        <>
          <button
            {...hit("pet", `看看 ${name}${note ? `，${note}` : ""}`, name)}
            className={hitClass("pet", `ps-living-pet ${sitting ? "is-sitting" : ""} ${sprite ? "is-photo" : sceneAsset(figure, inside ? "sleeping" : "neutral_full") ? "is-character" : "is-portrait"}`)}
            data-testid="home-pet"
          >
            {sprite ? (
              <>
                <span className="ps-living-pet__shadow" aria-hidden="true" />
                <img
                  src={sitting ? sprite.sit : sprite.rest}
                  alt={`${name}的内部测试形象`}
                />
              </>
            ) : (
              <PetFigure pet={snapshot.pet} state={figure} pose={inside ? "sleeping" : "neutral_full"} />
            )}
          </button>
          {sprite && !inside ? (
            <img
              className="ps-living-bag"
              src={sprite.bag}
              alt=""
              data-testid="home-bag"
            />
          ) : null}
        </>
      ) : null}
      {!inside ? (
        <img
          className="ps-living-cup"
          src={cup}
          alt=""
          data-testid="home-cup"
        />
      ) : null}
      {away ? (
        // TA 不在家：窝是空的，窝边留一张便笺；点它回到地图并对准 TA（?focus=）。
        <Link
          to={mapFocusHref(snapshot.pet.pet_id)}
          className={`ps-living-note ps-home-glow${glow("note").className}`}
          style={glow("note").style}
          aria-label={`我出门啦，回到地图看看 ${name} 在哪`}
          data-testid="home-away-note"
        >
          我出门啦<span>看看我走到哪啦</span>
        </Link>
      ) : null}
      {object ? (
        <button {...hit("memento", `你留下的叮嘱：${object.text}`, object.text)} className={hitClass("memento", "ps-home-memento")}>
          <Icon name="bookmark" size={16} />
        </button>
      ) : null}
      {!inside ? (
        <>
          <button {...hit("mail", unread > 0 ? `信箱，${unread} 条未读` : "信箱", "信箱")} className={hitClass("mail", `ps-home-spot ps-home-spot--mail${unread > 0 ? " has-mail" : ""}`)}>
            {unread > 0 ? (
              <span className="ps-home-envelope" aria-hidden="true">
                <Icon name="mail" size={20} />
              </span>
            ) : null}
          </button>
          <button
            {...hit("garden", `菜园${gardenStatus ? `，${gardenStatus}` : ""}`, "菜园")}
            className={hitClass("garden", `ps-living-garden-gate${ripe.length ? " is-ready" : ""}`)}
            data-testid="home-garden-gate"
          >
            {showcase ? <PlotArt plot={showcase} /> : null}
            {ripe.length ? (
              <span className="ps-living-garden-gate__ripe" aria-hidden="true">
                <Icon name="sparkle" size={13} />
              </span>
            ) : null}
          </button>
        </>
      ) : null}
      {openThing ? bubbleFor(openThing) : null}
      {petOpen && home ? (
        <Sheet
          title={`陪 ${name} 待一会儿`}
          subtitle={sprite ? "内部角色动作示例，不改变宠物真实状态" : note ? `TA 在家 · ${note}` : "TA 在家"}
          onClose={() => setPetOpen(false)}
        >
          <div className="ps-stack">
            {sprite ? (
              <Button
                variant="leaf"
                onClick={() => {
                  setSitting(!sitting);
                  setPetOpen(false);
                }}
              >
                {sitting ? "让 TA 趴着休息" : "陪 TA 坐一会儿"}
              </Button>
            ) : null}
            <Link className="ps-btn ps-btn--secondary" to="/communicator">
              给 TA 捎句话
            </Link>
            <Link className="ps-btn ps-btn--ghost" to="/journey">
              看看下一段旅途
            </Link>
            {sprite ? null : petActions}
          </div>
        </Sheet>
      ) : null}
    </section>
    </>
  );
}
