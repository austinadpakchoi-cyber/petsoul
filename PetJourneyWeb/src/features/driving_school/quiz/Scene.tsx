/**
 * 题目场景插画：按题目的 scene 键组合几种简单元素（道路、标志、信号灯、居民、车辆、车内、手机、天气）。
 * 只做示意，不包含任何答案信息；颜色取主题变量。未知的键退回一段普通道路。
 */
import type { ReactNode } from "react";

type Road = "straight" | "junction" | "zebra" | "curve" | "parking" | "narrow" | "cabin" | "board" | "yard";
type Sign = "stop" | "arrow_up" | "arrow_left" | "deer" | "curve" | "children" | "no_parking" | "parking" | "accessible" | "speed" | "crossing";

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
}

const SCENES: Record<string, Spec> = {
  stop_junction: { road: "junction", sign: "stop", car: true },
  stop_junction_night: { road: "junction", sign: "stop", car: true, night: true },
  blue_arrow: { road: "straight", sign: "arrow_up", car: true },
  lane_arrows: { road: "junction", sign: "arrow_left", car: true },
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
  no_parking: { road: "straight", sign: "no_parking", car: true },
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

function RoadLayer({ road }: { road: Road }): ReactNode {
  switch (road) {
    case "junction":
      return (
        <>
          <rect x="0" y="92" width="320" height="44" className="sc-road" />
          <rect x="190" y="40" width="44" height="120" className="sc-road" />
          <path d="M184 92 V136" className="sc-stopline" />
          <path d="M0 114 H180 M244 114 H320" className="sc-dash" />
        </>
      );
    case "zebra":
      return (
        <>
          <rect x="0" y="90" width="320" height="48" className="sc-road" />
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <rect key={i} x={186} y={92 + i * 8} width="34" height="4" className="sc-zebra" />
          ))}
          <path d="M178 90 V138" className="sc-stopline" />
        </>
      );
    case "curve":
      return <path d="M-10 150 C 90 150, 120 60, 330 60" className="sc-road-curve" />;
    case "parking":
      return (
        <>
          <rect x="0" y="70" width="320" height="90" className="sc-road" />
          {[40, 100, 160, 220, 280].map((x) => (
            <path key={x} d={`M${x} 70 V120`} className="sc-paint" />
          ))}
        </>
      );
    case "narrow":
      return (
        <>
          <rect x="0" y="100" width="320" height="30" className="sc-road" />
          <rect x="20" y="60" width="80" height="40" className="sc-house" />
          <rect x="200" y="56" width="90" height="44" className="sc-house" />
        </>
      );
    case "cabin":
      return (
        <>
          <rect x="0" y="0" width="320" height="160" className="sc-cabin" />
          <path d="M20 30 Q160 0 300 30 L300 90 L20 90 Z" className="sc-window" />
          <circle cx="110" cy="130" r="30" className="sc-wheel" />
          <rect x="200" y="104" width="80" height="18" rx="6" className="sc-dash-board" />
        </>
      );
    case "board":
      // 教练的标志板：挂着几块常见标志（只是示意，和题目的正确位置无关）
      return (
        <>
          <rect x="30" y="24" width="260" height="112" rx="12" className="sc-board" />
          <path d="M60 136 V156 M260 136 V156" className="sc-post" />
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
        </>
      );
    case "yard":
      return (
        <>
          <rect x="0" y="100" width="320" height="60" className="sc-road" />
          <rect x="220" y="30" width="80" height="70" className="sc-house" />
        </>
      );
    default:
      return (
        <>
          <rect x="0" y="92" width="320" height="44" className="sc-road" />
          <path d="M0 114 H320" className="sc-dash" />
        </>
      );
  }
}

function SignGlyph({ sign }: { sign: Sign }): ReactNode {
  const post = <path d="M262 100 V60" className="sc-post" />;
  const at = (child: ReactNode) => (
    <>
      {post}
      <g transform="translate(262 44)">{child}</g>
    </>
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
          <circle r="16" className="sc-sign-ring-only" />
          <path d="M-11 -11 L11 11" className="sc-sign-slash" />
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
    case "arrow_up":
    case "arrow_left":
      return at(
        <>
          <circle r="16" className="sc-sign-blue" />
          <path d={sign === "arrow_up" ? "M0 10 V-9 M-7 -2 L0 -10 L7 -2" : "M10 0 H-9 M-2 -7 L-10 0 L-2 7"} className="sc-sign-arrow" />
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

function Resident({ kind, x, y }: { kind: NonNullable<Spec["resident"]>; x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`} className={`sc-resident sc-resident--${kind}`}>
      {kind === "rabbit" ? <path d="M-5 -14 L-4 -26 L-1 -14 M5 -14 L4 -26 L1 -14" className="sc-ear" /> : null}
      {kind === "deer" ? <path d="M-6 -14 L-10 -24 M6 -14 L10 -24" className="sc-antler" /> : null}
      <circle r="11" className="sc-body" />
      <circle cx="-4" cy="-2" r="1.6" className="sc-eye" />
      <circle cx="4" cy="-2" r="1.6" className="sc-eye" />
    </g>
  );
}

function SmallCar({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x="-26" y="-12" width="52" height="24" rx="8" className="sc-car" />
      <rect x="4" y="-9" width="12" height="18" rx="3" className="sc-car-glass" />
      <circle cx="-6" cy="-3" r="5" className="sc-pet" />
    </g>
  );
}

export function Scene({ scene }: { scene: string }) {
  const spec = SCENES[scene] ?? { road: "straight", car: true };
  return (
    <svg className="ds-scene" viewBox="0 0 320 160" role="img" aria-label="题目场景示意图">
      <rect width="320" height="160" className={spec.night ? "sc-sky sc-sky--night" : "sc-sky"} />
      <RoadLayer road={spec.road} />
      {spec.school ? (
        <g>
          <rect x="14" y="30" width="96" height="56" className="sc-house" />
          <text x="62" y="64" className="sc-label">小学</text>
        </g>
      ) : null}
      {spec.sign ? <SignGlyph sign={spec.sign} /> : null}
      {spec.light ? (
        <g transform="translate(236 20)">
          <rect x="-9" y="0" width="18" height="46" rx="5" className="sc-light-box" />
          <circle cy="9" r="5" className={spec.light === "red" ? "sc-lamp sc-lamp--red" : "sc-lamp"} />
          <circle cy="23" r="5" className={spec.light === "flash" ? "sc-lamp sc-lamp--yellow sc-flash" : "sc-lamp"} />
          <circle cy="37" r="5" className={spec.light === "green" ? "sc-lamp sc-lamp--green" : "sc-lamp"} />
        </g>
      ) : null}
      {spec.car && spec.road !== "cabin" ? <SmallCar x={spec.road === "curve" ? 110 : 120} y={spec.road === "parking" ? 142 : spec.road === "curve" ? 118 : spec.road === "narrow" ? 115 : 124} /> : null}
      {spec.resident ? <Resident kind={spec.resident} x={spec.road === "zebra" ? 203 : spec.road === "parking" ? 72 : 60} y={spec.road === "zebra" ? 104 : spec.road === "parking" ? 150 : 100} /> : null}
      {spec.vehicle ? (
        <g transform="translate(34 114)">
          <rect x="-24" y="-13" width="56" height="26" rx="5" className={spec.vehicle === "ambulance" ? "sc-ambulance" : "sc-firetruck"} />
          <path d="M0 -7 V7 M-7 0 H7" className="sc-cross" />
          <circle cx="24" cy="-15" r="4" className="sc-siren" />
        </g>
      ) : null}
      {spec.phone ? (
        <g transform="translate(236 26)">
          <rect x="-26" y="0" width="52" height="84" rx="8" className="sc-phone" />
          <rect x="-20" y="12" width="40" height={spec.phone === "invite" ? 22 : 40} rx="4" className="sc-phone-note" />
          {spec.phone === "video" ? <path d="M-4 22 L8 32 L-4 42 Z" className="sc-play" /> : <text y="27" className="sc-label sc-label--small">邀请</text>}
        </g>
      ) : null}
      {spec.drop ? (
        <g transform="translate(250 130)" className="sc-drop">
          {spec.drop === "snack" ? <rect x="-12" y="-9" width="24" height="18" rx="4" className="sc-snack" /> : <rect x="-14" y="-11" width="28" height="22" rx="2" className="sc-frame" />}
        </g>
      ) : null}
      {spec.yawn ? <text x="132" y="96" className="sc-label">哈——欠</text> : null}
      {spec.rain ? <path d="M20 10 l-8 20 M70 4 l-8 20 M120 12 l-8 20 M170 6 l-8 20 M220 14 l-8 20 M270 8 l-8 20 M40 50 l-8 20 M150 48 l-8 20 M250 54 l-8 20" className="sc-rain" /> : null}
      {spec.fog ? <rect width="320" height="160" className="sc-fog" /> : null}
    </svg>
  );
}
