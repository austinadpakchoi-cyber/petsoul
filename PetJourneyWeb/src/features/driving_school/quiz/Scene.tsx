/**
 * 题目场景插画：全部用代码画（SVG，不用图片文件），按题目的 scene 键组合几种元素（道路、标志、信号灯、居民、车辆、车内、手机、天气）。
 * - 只做示意，不包含任何答案信息：画面只看 scene 键，同一个键在练习、正式考试、讲解前后画出来完全一样；
 * - 每道题要看懂的东西（标志、信号灯颜色、斑马线、停止线、救援车、雨雾夜、学校……）位置和含义保持原样，
 *   路面质感、草地、树、房子只是背景，画在它们下面；
 * - 过街的居民画成简单可爱的小动物（企鹅、兔子、小狗、小鹿），不画玩家的宠物；车里的 TA 只是一个圆点；
 * - 颜色全部取主题变量（深浅色自动跟随）；唯一的动画是“黄灯在闪”，另有静止的闪光线，减少动态效果时动画停住、意思不丢。
 * 关键元素带 data-part，供测试逐题核对。未知的键退回一段普通道路。
 */
import { useId, type ReactNode } from "react";

type Road = "straight" | "junction" | "zebra" | "curve" | "parking" | "narrow" | "cabin" | "board" | "yard" | "lanes";
type Sign = "stop" | "arrow_right" | "deer" | "curve" | "children" | "no_parking" | "parking" | "accessible" | "speed" | "crossing";

interface Spec {
  road: Road;
  sign?: Sign;
  light?: "red" | "green" | "flash";
  resident?: "penguin" | "rabbit" | "puppy" | "deer";
  vehicle?: "ambulance" | "firetruck";
  car?: boolean;
  phone?: "invite" | "video";
  drop?: "snack" | "frame";
  night?: boolean;
  rain?: boolean;
  fog?: boolean;
  school?: boolean;
  yawn?: boolean;
  /** 路边的黄色网格（禁止停车区） */
  grid?: boolean;
}

const SCENES: Record<string, Spec> = {
  stop_junction: { road: "junction", sign: "stop", car: true },
  stop_junction_night: { road: "junction", sign: "stop", car: true, night: true },
  // 2026-09-24 第四批按题干改画面（答案照题干出）：
  // s1.dir.1“蓝色圆牌上画着向右的白色箭头”——原来画的是向上箭头；
  // s1.dir.2“地上画着直行箭头的车道”——原来是一块向左的圆牌（意思是“只准左转”，和题目矛盾），改成路面上的车道箭头：
  //   小车在画直行箭头的车道，旁边车道画右转箭头（两条车道同样的白漆，不突出哪一条）；
  // s1.park.1“路边画着黄色网格”——原来没画网格。
  blue_arrow: { road: "straight", sign: "arrow_right", car: true },
  lane_arrows: { road: "lanes", car: true },
  deer_sign: { road: "curve", sign: "deer", resident: "deer" },
  curve_sign: { road: "curve", sign: "curve", car: true },
  children_sign: { road: "straight", sign: "children", school: true },
  zebra_penguin: { road: "zebra", resident: "penguin", car: true },
  zebra_waiting: { road: "zebra", resident: "rabbit", car: true },
  zebra_steps: { road: "zebra", resident: "penguin", sign: "crossing" },
  signal_flash: { road: "junction", light: "flash", car: true },
  signal_green_walker: { road: "zebra", light: "green", resident: "rabbit", car: true },
  signal_board: { road: "junction", light: "red" },
  ambulance_behind: { road: "straight", vehicle: "ambulance", car: true },
  firetruck_junction: { road: "junction", vehicle: "firetruck", light: "green" },
  ambulance_steps: { road: "straight", vehicle: "ambulance" },
  car_check: { road: "yard", car: true },
  seatbelt: { road: "cabin" },
  mirror_check: { road: "cabin" },
  no_parking: { road: "straight", sign: "no_parking", car: true, grid: true },
  parking_board: { road: "parking", sign: "parking" },
  accessible_bay: { road: "parking", sign: "accessible" },
  school_gate: { road: "straight", sign: "children", school: true, resident: "rabbit" },
  speed_sign: { road: "straight", sign: "speed", car: true },
  narrow_street: { road: "narrow", car: true, resident: "puppy" },
  reverse_check: { road: "parking", car: true },
  reverse_puppy: { road: "parking", car: true, resident: "puppy" },
  reverse_park: { road: "parking", car: true },
  sign_board: { road: "board" },
  drowsy_road: { road: "straight", car: true, yawn: true, night: true },
  night_road: { road: "curve", car: true, night: true },
  rain_road: { road: "straight", car: true, rain: true },
  fog_road: { road: "curve", car: true, fog: true },
  phone_invite: { road: "cabin", phone: "invite" },
  phone_video: { road: "cabin", phone: "video" },
  market_reverse: { road: "parking", car: true, resident: "penguin" },
  canteen_reverse: { road: "parking", car: true, resident: "rabbit" },
  snack_drop: { road: "cabin", drop: "snack" },
  frame_drop: { road: "cabin", drop: "frame" },
};

const CURVE = "M-10 150 C 90 150, 120 60, 330 60";

/* ---------- 背景：草地、远山、树、房子（只是背景，画在题目元素下面） ---------- */

function Tree({ x, y, s = 1 }: { x: number; y: number; s?: number }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <rect x="-2" y="-2" width="4" height="12" rx="1.5" className="sc-trunk" />
      <circle cy="-12" r="10" className="sc-canopy" />
      <circle cx="-7" cy="-5" r="7" className="sc-canopy" />
      <circle cx="7" cy="-5" r="7" className="sc-canopy" />
      <circle cx="-3" cy="-15" r="3.5" className="sc-canopy-hi" />
    </g>
  );
}

function House({ x, y, w, h, lit }: { x: number; y: number; w: number; h: number; lit?: boolean }) {
  const win = lit ? "sc-win sc-win--lit" : "sc-win";
  return (
    <g>
      <path d={`M${x - 4} ${y + 1} L${x + w / 2} ${y - Math.min(20, h * 0.55)} L${x + w + 4} ${y + 1} Z`} className="sc-roof" />
      <rect x={x} y={y} width={w} height={h} className="sc-house" />
      <rect x={x + w * 0.14} y={y + h * 0.2} width={w * 0.22} height={h * 0.3} rx="1.5" className={win} />
      <rect x={x + w * 0.64} y={y + h * 0.2} width={w * 0.22} height={h * 0.3} rx="1.5" className={win} />
      <rect x={x + w * 0.42} y={y + h * 0.56} width={w * 0.16} height={h * 0.44} rx="1.5" className="sc-door" />
    </g>
  );
}

const TUFTS = "M14 152 l2 -6 l2 6 M58 147 l2 -5 l2 5 M104 155 l2 -6 l2 6 M150 150 l2 -5 l2 5 M254 151 l2 -5 l2 5 M300 155 l2 -6 l2 6";

function Backdrop({ spec }: { spec: Spec }): ReactNode {
  if (spec.road === "cabin") return null;
  const lit = !!spec.night;
  const hills = <path d="M0 74 C 36 60, 70 62, 104 70 C 140 79, 176 60, 214 64 C 252 68, 290 58, 320 62 L320 96 L0 96 Z" className="sc-hill" />;
  const grass = <rect x="0" y="84" width="320" height="76" className="sc-grass" />;
  const tufts = <path d={TUFTS} className="sc-tuft" />;
  switch (spec.road) {
    case "straight":
      return (
        <>
          {hills}
          {grass}
          {spec.school ? null : <House x={22} y={62} w={40} h={24} lit={lit} />}
          <Tree x={150} y={76} />
          <Tree x={196} y={78} s={0.8} />
          {tufts}
        </>
      );
    case "junction":
    case "zebra":
      return (
        <>
          {hills}
          {grass}
          <Tree x={36} y={76} />
          <Tree x={84} y={78} s={0.8} />
          <House x={118} y={62} w={40} h={24} lit={lit} />
          {tufts}
        </>
      );
    case "lanes":
      return (
        <>
          {hills}
          {grass}
          <Tree x={36} y={66} />
          <Tree x={84} y={68} s={0.8} />
          <House x={118} y={54} w={40} h={24} lit={lit} />
        </>
      );
    case "curve":
      return (
        <>
          {hills}
          {grass}
          <Tree x={24} y={62} s={0.9} />
          <Tree x={70} y={64} s={0.75} />
          <House x={198} y={118} w={38} h={22} lit={lit} />
          <Tree x={292} y={128} s={0.8} />
        </>
      );
    case "parking":
      return (
        <>
          {hills}
          {grass}
          {/* 路边的小店：带条纹遮阳棚 */}
          <rect x="20" y="40" width="104" height="30" className="sc-house" />
          <path d="M16 40 H128 L122 50 H22 Z" className="sc-roof" />
          <path d="M34 41 V49 M50 41 V49 M66 41 V49 M82 41 V49 M98 41 V49 M114 41 V49" className="sc-awning" />
          <rect x="30" y="54" width="22" height="16" rx="1.5" className={lit ? "sc-win sc-win--lit" : "sc-win"} />
          <rect x="92" y="54" width="22" height="16" rx="1.5" className={lit ? "sc-win sc-win--lit" : "sc-win"} />
          <rect x="62" y="54" width="18" height="16" rx="1.5" className="sc-door" />
          <Tree x={160} y={56} s={0.8} />
          <Tree x={204} y={58} s={0.7} />
        </>
      );
    case "narrow":
      return (
        <>
          {hills}
          {grass}
          <Tree x={150} y={86} s={0.75} />
          {tufts}
        </>
      );
    case "yard":
      return (
        <>
          {hills}
          {grass}
          <Tree x={36} y={80} />
          <Tree x={84} y={84} s={0.75} />
        </>
      );
    default:
      return (
        <>
          {hills}
          {grass}
          {tufts}
        </>
      );
  }
}

/* ---------- 路面（带颗粒质感）与标线 ---------- */

function Asphalt({ x, y, w, h, grain }: { x: number; y: number; w: number; h: number; grain: string }) {
  return (
    <>
      <rect x={x} y={y} width={w} height={h} className="sc-road" />
      <rect x={x} y={y} width={w} height={h} fill={`url(#${grain})`} />
    </>
  );
}

function RoadLayer({ spec, ids }: { spec: Spec; ids: Ids }): ReactNode {
  const g = ids.grain;
  switch (spec.road) {
    case "junction":
      return (
        <g data-part="road-junction">
          <Asphalt x={0} y={92} w={320} h={44} grain={g} />
          {/* 横穿的路从远处草地开始（原来从半空 y=40 起，加了远山后像一根柱子）；路口、停止线的位置不变 */}
          <Asphalt x={190} y={70} w={44} h={90} grain={g} />
          <path d="M0 94.5 H190 M234 94.5 H320 M0 133.5 H190 M234 133.5 H320" className="sc-edge" />
          <path d="M184 92 V136" className="sc-stopline" data-part="stopline" />
          <path d="M0 114 H180 M244 114 H320" className="sc-dash" />
        </g>
      );
    case "lanes":
      // 路口前的三条车道：上面一条对向；小车这一侧两条——内侧画直行箭头（小车在这里）、外侧画右转箭头；前面是路口和停止线
      return (
        <g data-part="road-lanes">
          <Asphalt x={0} y={80} w={320} h={72} grain={g} />
          <Asphalt x={214} y={70} w={44} h={90} grain={g} />
          <path d="M0 82.5 H214 M258 82.5 H320 M0 150.5 H214 M258 150.5 H320" className="sc-edge" />
          <path d="M0 102 H206" className="sc-dash sc-dash--solid" />
          <path d="M0 127 H206" className="sc-lane-line" />
          <path d="M206 102 V152" className="sc-stopline" data-part="stopline" />
          <path d="M152 114.5 H182 M175 108.5 L183 114.5 L175 120.5" className="sc-lane-arrow" data-part="lane-arrow-straight" />
          <path d="M152 137 H170 Q178 137 178 144 M173 141 L178 148 L183 141" className="sc-lane-arrow" data-part="lane-arrow-right" />
        </g>
      );
    case "zebra":
      return (
        <g data-part="road-zebra">
          <Asphalt x={0} y={90} w={320} h={48} grain={g} />
          <path d="M0 92.5 H320 M0 135.5 H320" className="sc-edge" />
          <g data-part="zebra">
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <rect key={i} x={186} y={92 + i * 8} width="34" height="4" rx="1" className="sc-zebra" />
            ))}
          </g>
          <path d="M178 90 V138" className="sc-stopline" data-part="stopline" />
        </g>
      );
    case "curve":
      return (
        <g data-part="road-curve">
          <path d={CURVE} className="sc-road-curve" />
          <path d={CURVE} className="sc-road-curve-grain" stroke={`url(#${g})`} />
          <path d={CURVE} className="sc-dash sc-dash--curve" />
        </g>
      );
    case "parking":
      return (
        <g data-part="road-parking">
          <Asphalt x={0} y={70} w={320} h={90} grain={g} />
          <g data-part="bays">
            {[40, 100, 160, 220, 280].map((x) => (
              <path key={x} d={`M${x} 70 V120`} className="sc-paint" />
            ))}
          </g>
        </g>
      );
    case "narrow":
      return (
        <g data-part="road-narrow">
          <Asphalt x={0} y={100} w={320} h={30} grain={g} />
          <g data-part="houses-narrow">
            <House x={20} y={60} w={80} h={40} lit={spec.night} />
            <House x={200} y={56} w={90} h={44} lit={spec.night} />
          </g>
        </g>
      );
    case "cabin":
      return <Cabin ids={ids} />;
    case "board":
      // 教练的标志板：挂着几块常见标志（只是示意，和题目的正确位置无关）
      return (
        <g data-part="board">
          <path d="M60 136 V156 M260 136 V156" className="sc-post" />
          <rect x="30" y="24" width="260" height="112" rx="12" className="sc-board" />
          <g transform="translate(90 80)">
            <path d="M-9 -22 H9 L22 -9 V9 L9 22 H-9 L-22 9 V-9 Z" className="sc-sign-red" />
            <text y="6" className="sc-sign-text">停</text>
          </g>
          <g transform="translate(160 80)">
            <rect x="-20" y="-20" width="40" height="40" rx="5" className="sc-sign-blue" />
            <path d="M-8 13 L0 -3 L8 13 M0 -3 V-12" className="sc-sign-arrow" />
          </g>
          <g transform="translate(230 80)">
            <rect x="-20" y="-20" width="40" height="40" rx="5" className="sc-sign-blue" />
            <text y="7" className="sc-sign-text">P</text>
          </g>
        </g>
      );
    case "yard":
      return (
        <g data-part="road-yard">
          <Asphalt x={0} y={100} w={320} h={60} grain={g} />
          <g data-part="house-yard">
            <House x={220} y={30} w={80} h={70} lit={spec.night} />
          </g>
        </g>
      );
    default:
      return (
        <g data-part="road-straight">
          <Asphalt x={0} y={92} w={320} h={44} grain={g} />
          <path d="M0 94.5 H320 M0 133.5 H320" className="sc-edge" />
          <path d="M0 114 H320" className="sc-dash" />
        </g>
      );
  }
}

/* ---------- 车内：前挡风玻璃外是路，中间有后视镜，方向盘、仪表台 ---------- */

function Cabin({ ids }: { ids: Ids }) {
  return (
    <g data-part="cabin">
      <rect x="0" y="0" width="320" height="160" className="sc-cabin" />
      <clipPath id={ids.windshield}>
        <path d="M20 30 Q160 0 300 30 L300 90 L20 90 Z" />
      </clipPath>
      <g clipPath={`url(#${ids.windshield})`}>
        <rect x="0" y="0" width="320" height="90" fill={`url(#${ids.sky})`} />
        <rect x="0" y="62" width="320" height="30" className="sc-grass" />
        <path d="M130 90 L154 62 H166 L190 90 Z" className="sc-road" />
        <path d="M160 66 V70 M160 75 V80 M160 85 V90" className="sc-dash sc-dash--thin" />
        <Tree x={70} y={52} s={0.7} />
        <Tree x={250} y={54} s={0.6} />
      </g>
      <path d="M20 30 Q160 0 300 30 L300 90 L20 90 Z" className="sc-window" />
      <rect x="146" y="18" width="28" height="9" rx="4" className="sc-mirror" />
      <path d="M160 14 V18" className="sc-mirror-stem" />
      <rect x="0" y="96" width="320" height="64" className="sc-dash-panel" />
      <circle cx="110" cy="130" r="30" className="sc-wheel" />
      <path d="M86 132 H134 M110 132 V158" className="sc-wheel-spoke" />
      <circle cx="110" cy="132" r="6" className="sc-wheel-hub" />
      <rect x="200" y="104" width="80" height="18" rx="6" className="sc-dash-board" />
      <circle cx="222" cy="113" r="4" className="sc-gauge" />
      <circle cx="258" cy="113" r="4" className="sc-gauge" />
    </g>
  );
}

/* ---------- 标志、信号灯 ---------- */

function SignGlyph({ sign }: { sign: Sign }): ReactNode {
  const at = (child: ReactNode) => (
    <g data-part={`sign-${sign}`}>
      <rect x="260" y="58" width="4" height="42" rx="2" className="sc-pole" />
      <ellipse cx="262" cy="100" rx="6" ry="2" className="sc-pole-base" />
      <g transform="translate(262 44)">{child}</g>
    </g>
  );
  switch (sign) {
    case "stop":
      return at(
        <>
          <path d="M-7 -17 H7 L17 -7 V7 L7 17 H-7 L-17 7 V-7 Z" className="sc-sign-red" />
          <text y="5" className="sc-sign-text">停</text>
        </>,
      );
    case "speed":
      return at(
        <>
          <circle r="16" className="sc-sign-ring" />
          <text y="5" className="sc-sign-text sc-sign-text--ink">30</text>
        </>,
      );
    case "no_parking":
      return at(
        <>
          <circle r="16" className="sc-sign-blue" />
          <circle r="14" className="sc-sign-ring-only" />
          <path d="M-10 -10 L10 10" className="sc-sign-slash" />
        </>,
      );
    case "parking":
    case "accessible":
      return at(
        <>
          <rect x="-15" y="-15" width="30" height="30" rx="4" className="sc-sign-blue" />
          <text y="6" className="sc-sign-text">{sign === "parking" ? "P" : "♿"}</text>
        </>,
      );
    case "arrow_right":
      return at(
        <>
          <circle r="16" className="sc-sign-blue" />
          <path d="M-10 0 H9 M2 -7 L10 0 L2 7" className="sc-sign-arrow" />
        </>,
      );
    case "crossing":
      return at(
        <>
          <rect x="-15" y="-15" width="30" height="30" rx="4" className="sc-sign-blue" />
          <path d="M-6 10 L0 -2 L6 10 M0 -2 V-9" className="sc-sign-arrow" />
        </>,
      );
    default:
      return at(
        <>
          <path d="M0 -17 L17 13 H-17 Z" className="sc-sign-warn" />
          <text y="9" className="sc-sign-text sc-sign-text--ink">{sign === "deer" ? "鹿" : sign === "children" ? "童" : "弯"}</text>
        </>,
      );
  }
}

function TrafficLight({ light }: { light: NonNullable<Spec["light"]> }) {
  const lit = { red: 9, flash: 23, green: 37 }[light];
  const tone = { red: "red", flash: "yellow", green: "green" }[light];
  return (
    <g transform="translate(236 20)" data-part="light" data-lit={light}>
      <rect x="-2" y="44" width="4" height="30" rx="1.5" className="sc-pole" />
      <rect x="-10" y="-1" width="20" height="48" rx="6" className="sc-light-box" />
      <circle cy={lit} r="8.5" className={`sc-glow sc-glow--${tone}`} />
      <circle cy="9" r="5" className={light === "red" ? "sc-lamp sc-lamp--red" : "sc-lamp"} />
      <circle cy="23" r="5" className={light === "flash" ? "sc-lamp sc-lamp--yellow sc-flash" : "sc-lamp"} />
      <circle cy="37" r="5" className={light === "green" ? "sc-lamp sc-lamp--green" : "sc-lamp"} />
      {/* “一直在闪”：除了闪烁动画，还有静止的闪光线（减少动态效果时动画停住，意思不丢） */}
      {light === "flash" ? <path d="M-14 23 H-19 M14 23 H19 M-12 15 L-16 11 M12 15 L16 11 M-12 31 L-16 35 M12 31 L16 35" className="sc-rays" data-part="flash-rays" /> : null}
    </g>
  );
}

/* ---------- 车、居民、救援车 ---------- */

/** 俯视的小车，车头朝右；车里的 TA 只是一个圆点。 */
function SmallCar({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`} data-part="car">
      <rect x="-22" y="-15" width="9" height="5" rx="2" className="sc-tire" />
      <rect x="12" y="-15" width="9" height="5" rx="2" className="sc-tire" />
      <rect x="-22" y="10" width="9" height="5" rx="2" className="sc-tire" />
      <rect x="12" y="10" width="9" height="5" rx="2" className="sc-tire" />
      <rect x="-27" y="-13" width="54" height="26" rx="12" className="sc-car" />
      <rect x="-14" y="-9.5" width="30" height="19" rx="8" className="sc-car-roof" />
      <rect x="6" y="-8" width="9" height="16" rx="4" className="sc-car-glass" />
      <rect x="-13" y="-7" width="5" height="14" rx="2.5" className="sc-car-glass" />
      <circle cx="-3" cy="-2.5" r="4.5" className="sc-pet" />
      <circle cx="24" cy="-7.5" r="2" className="sc-headlight" />
      <circle cx="24" cy="7.5" r="2" className="sc-headlight" />
    </g>
  );
}

/** 过街的居民：简单可爱的小动物（原创居民，不是玩家的宠物）。 */
function Resident({ kind, x, y }: { kind: NonNullable<Spec["resident"]>; x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`} className={`sc-resident sc-resident--${kind}`} data-part={`resident-${kind}`}>
      {kind === "rabbit" ? (
        <>
          <ellipse cx="-4.5" cy="-16" rx="3.2" ry="8" className="sc-body" />
          <ellipse cx="4.5" cy="-16" rx="3.2" ry="8" className="sc-body" />
          <ellipse cx="-4.5" cy="-16" rx="1.4" ry="5" className="sc-ear-in" />
          <ellipse cx="4.5" cy="-16" rx="1.4" ry="5" className="sc-ear-in" />
        </>
      ) : null}
      {kind === "deer" ? <path d="M-5 -9 L-9 -19 M-9 -19 L-13 -21 M-9 -19 L-8 -24 M5 -9 L9 -19 M9 -19 L13 -21 M9 -19 L8 -24" className="sc-antler" /> : null}
      {kind === "puppy" ? (
        <>
          <ellipse cx="-10" cy="-3" rx="4" ry="7.5" transform="rotate(18 -10 -3)" className="sc-ear-flop" />
          <ellipse cx="10" cy="-3" rx="4" ry="7.5" transform="rotate(-18 10 -3)" className="sc-ear-flop" />
        </>
      ) : null}
      <circle r="11" className="sc-body" />
      {kind === "penguin" ? <ellipse cy="1.5" rx="7.5" ry="8" className="sc-belly" /> : null}
      {kind === "deer" ? (
        <>
          <circle cx="-6" cy="5" r="1.2" className="sc-spot" />
          <circle cx="6" cy="6" r="1.2" className="sc-spot" />
        </>
      ) : null}
      <circle cx="-4" cy="-2" r="1.7" className="sc-eye" />
      <circle cx="4" cy="-2" r="1.7" className="sc-eye" />
      {kind === "penguin" ? <path d="M-2.6 1.5 H2.6 L0 4.6 Z" className="sc-beak" /> : <ellipse cy="2.6" rx="1.8" ry="1.3" className="sc-nose" />}
      <circle cx="-7" cy="3.5" r="1.8" className="sc-blush" />
      <circle cx="7" cy="3.5" r="1.8" className="sc-blush" />
      {kind === "penguin" ? <path d="M-6 10.5 h4 M2 10.5 h4" className="sc-feet" /> : null}
    </g>
  );
}

function Rescue({ kind }: { kind: NonNullable<Spec["vehicle"]> }) {
  const ambulance = kind === "ambulance";
  return (
    <g transform="translate(34 114)" data-part={`vehicle-${kind}`}>
      <circle cx="-12" cy="13" r="5" className="sc-tire" />
      <circle cx="20" cy="13" r="5" className="sc-tire" />
      <rect x="-24" y="-13" width="56" height="26" rx="5" className={ambulance ? "sc-ambulance" : "sc-firetruck"} />
      <rect x="20" y="-9" width="9" height="9" rx="2" className="sc-van-window" />
      {ambulance ? <rect x="-24" y="4" width="56" height="3" className="sc-ambulance-stripe" /> : <path d="M-20 -17 H14 M-20 -21 H14 M-16 -21 V-17 M-8 -21 V-17 M0 -21 V-17 M8 -21 V-17" className="sc-ladder" />}
      <path d="M0 -7 V7 M-7 0 H7" className="sc-cross" />
      <circle cx="24" cy="-15" r="4" className="sc-siren" />
    </g>
  );
}

/* ---------- 天气与夜晚 ---------- */

function Sky({ spec, ids }: { spec: Spec; ids: Ids }) {
  if (spec.night) {
    return (
      <g data-part="night">
        <rect width="320" height="160" className="sc-sky sc-sky--night" />
        <path d="M52 16 a10 10 0 1 0 8 16 a8 8 0 1 1 -8 -16 Z" className="sc-moon" />
        {[
          [96, 14],
          [140, 28],
          [178, 12],
          [300, 20],
          [22, 40],
        ].map(([x, y]) => (
          <circle key={`${x}-${y}`} cx={x} cy={y} r="1.3" className="sc-star" />
        ))}
      </g>
    );
  }
  return <rect width="320" height="160" className="sc-sky" fill={`url(#${ids.sky})`} />;
}

type Ids = { grain: string; sky: string; windshield: string; grid: string };

export function Scene({ scene }: { scene: string }) {
  const spec = SCENES[scene] ?? { road: "straight", car: true };
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const ids: Ids = { grain: `sc-grain-${uid}`, sky: `sc-sky-${uid}`, windshield: `sc-ws-${uid}`, grid: `sc-grid-${uid}` };
  return (
    <svg className="ds-scene" viewBox="0 0 320 160" role="img" aria-label="题目场景示意图" data-scene={scene}>
      <defs>
        <pattern id={ids.grain} width="18" height="14" patternUnits="userSpaceOnUse">
          <circle cx="3" cy="4" r="0.9" className="sc-grain-dot" />
          <circle cx="11" cy="9" r="0.7" className="sc-grain-dot" />
          <circle cx="15" cy="2" r="0.6" className="sc-grain-dot" />
        </pattern>
        <linearGradient id={ids.sky} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" className="sc-sky-top" />
          <stop offset="1" className="sc-sky-bottom" />
        </linearGradient>
      </defs>
      <Sky spec={spec} ids={ids} />
      <Backdrop spec={spec} />
      <RoadLayer spec={spec} ids={ids} />
      {spec.grid ? (
        // 路边的黄色网格：禁止停车区，画在标志牌下方的路边
        <g data-part="yellow-grid">
          <clipPath id={ids.grid}>
            <rect x="196" y="96" width="104" height="15" />
          </clipPath>
          <path
            d={Array.from({ length: 13 }, (_, i) => `M${186 + i * 10} 96 l15 15 M${201 + i * 10} 96 l-15 15`).join(" ")}
            className="sc-grid-yellow"
            clipPath={`url(#${ids.grid})`}
          />
          <rect x="196" y="96" width="104" height="15" className="sc-grid-box" />
        </g>
      ) : null}
      {spec.school ? (
        <g data-part="school">
          <path d="M10 31 L62 14 L114 31 Z" className="sc-roof" />
          <rect x="14" y="30" width="96" height="56" className="sc-house" />
          <rect x="22" y="38" width="16" height="11" rx="1.5" className="sc-win" />
          <rect x="86" y="38" width="16" height="11" rx="1.5" className="sc-win" />
          <rect x="54" y="70" width="16" height="16" rx="1.5" className="sc-door" />
          <path d="M62 14 V4" className="sc-flagpole" />
          <path d="M62 4 H72 L69 7 L72 10 H62 Z" className="sc-flag" />
          <text x="62" y="64" className="sc-label">小学</text>
        </g>
      ) : null}
      {spec.rain ? (
        <g className="sc-clouds">
          <ellipse cx="70" cy="12" rx="34" ry="11" className="sc-cloud" />
          <ellipse cx="96" cy="8" rx="20" ry="9" className="sc-cloud" />
          <ellipse cx="226" cy="10" rx="36" ry="11" className="sc-cloud" />
        </g>
      ) : null}
      {spec.sign ? <SignGlyph sign={spec.sign} /> : null}
      {spec.light ? <TrafficLight light={spec.light} /> : null}
      {spec.car && spec.road !== "cabin" ? (
        <SmallCar x={spec.road === "curve" ? 110 : 120} y={spec.road === "parking" ? 142 : spec.road === "curve" ? 118 : spec.road === "narrow" ? 115 : spec.road === "lanes" ? 114.5 : 124} />
      ) : null}
      {spec.resident ? <Resident kind={spec.resident} x={spec.road === "zebra" ? 203 : spec.road === "parking" ? 72 : 60} y={spec.road === "zebra" ? 104 : spec.road === "parking" ? 150 : 100} /> : null}
      {spec.vehicle ? <Rescue kind={spec.vehicle} /> : null}
      {spec.phone ? (
        <g transform="translate(236 26)" data-part={`phone-${spec.phone}`}>
          <rect x="-26" y="0" width="52" height="84" rx="8" className="sc-phone" />
          <rect x="-9" y="4" width="18" height="3" rx="1.5" className="sc-phone-speaker" />
          <rect x="-20" y="12" width="40" height={spec.phone === "invite" ? 22 : 40} rx="4" className="sc-phone-note" />
          {spec.phone === "video" ? (
            <path d="M-4 22 L8 32 L-4 42 Z" className="sc-play" />
          ) : (
            <>
              <circle cx="-14" cy="23" r="3.5" className="sc-phone-avatar" />
              <text x="5" y="27" className="sc-note-text">邀请</text>
            </>
          )}
        </g>
      ) : null}
      {spec.drop ? (
        <g transform="translate(250 130)" className="sc-drop" data-part={`drop-${spec.drop}`}>
          {spec.drop === "snack" ? (
            <>
              <rect x="-12" y="-9" width="24" height="18" rx="4" className="sc-snack" />
              <rect x="-12" y="-3" width="24" height="5" className="sc-snack-band" />
            </>
          ) : (
            <>
              <rect x="-14" y="-11" width="28" height="22" rx="2" className="sc-frame" />
              <path d="M-9 6 L-3 -1 L2 4 L5 1 L9 6 Z" className="sc-frame-hill" />
            </>
          )}
        </g>
      ) : null}
      {spec.yawn ? (
        <text x="132" y="96" className="sc-yawn" data-part="yawn">
          哈——欠
        </text>
      ) : null}
      {spec.rain ? (
        <path
          d="M20 10 l-8 20 M70 4 l-8 20 M120 12 l-8 20 M170 6 l-8 20 M220 14 l-8 20 M270 8 l-8 20 M40 50 l-8 20 M150 48 l-8 20 M250 54 l-8 20 M96 30 l-6 15 M196 34 l-6 15 M300 36 l-6 15"
          className="sc-rain"
          data-part="rain"
        />
      ) : null}
      {spec.fog ? (
        <g data-part="fog">
          <rect width="320" height="160" className="sc-fog" />
          <path d="M-10 70 C 60 60, 140 80, 330 66 L330 84 C 140 98, 60 78, -10 88 Z M-10 112 C 80 102, 180 124, 330 108 L330 124 C 180 138, 80 118, -10 128 Z" className="sc-fog-band" />
        </g>
      ) : null}
    </svg>
  );
}
